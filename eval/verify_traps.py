#!/usr/bin/env python3
"""Verify the data traps from docs/data.md on the real files, and print the evidence.

    python eval/verify_traps.py [--dataset data/Market-cloudbed-1] [--day 2022_03_20]

Never reads a whole trace_span.csv / log_proxy.csv / log_service.csv: those are
sampled by byte offset. Output is copied into docs/data-notes.md.
"""
from __future__ import annotations

import argparse
import csv
import io
import re
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from origin.case import parse_instruction  # noqa: E402
from origin.contract import UTC8, fmt_ts  # noqa: E402

MS_FILES = ("trace_span.csv",)


def h(title: str) -> None:
    print(f"\n## {title}\n")


def files_of(day_dir: Path) -> list[Path]:
    return sorted(p for sub in ("metric", "log", "trace") for p in (day_dir / sub).glob("*.csv"))


def ts_index(path: Path) -> tuple[list[str], int]:
    with open(path, "rb") as fh:
        header = next(csv.reader([fh.readline().decode("utf-8", "replace")]))
    return header, header.index("timestamp")


def ts_at(fh, offset: int, i: int) -> float | None:
    """Timestamp of the first full line at or after `offset`."""
    fh.seek(offset)
    if offset > 0:
        fh.readline()
    for _ in range(50):
        line = fh.readline()
        if not line:
            return None
        try:
            row = next(csv.reader([line.decode("utf-8", "replace")]))
            return float(row[i])
        except (StopIteration, ValueError, IndexError):
            continue   # a quoted field with a newline, or a partial line
    return None


# 1 ---------------------------------------------------------------------------
def headers(day_dir: Path) -> None:
    h("1. Headers and first rows (head -c 2000, first 3 lines)")
    for p in files_of(day_dir):
        with open(p, "rb") as fh:
            head = fh.read(2000).decode("utf-8", "replace").splitlines()[:4]
        _, i = ts_index(p)
        first = next(csv.reader([head[1]]))[i]
        kind = ("float" if "." in first else "integer") + (
            ", milliseconds" if float(first) > 1e11 else ", seconds")
        print(f"### {p.parent.name}/{p.name}  ({p.stat().st_size / 1e6:,.0f} MB) — timestamp: `{first}` ({kind})")
        print("```")
        for line in head:
            print(line[:220])
        print("```")


# 2 ---------------------------------------------------------------------------
def sortedness(day_dir: Path, n: int = 1024) -> None:
    h(f"2. Sortedness by timestamp ({n} evenly spaced byte offsets; a new run starts at a backward jump > 120 s)")
    print("A file with few runs, each sorted, can be binary-searched run by run; a file with")
    print("many runs (grouped by series) cannot.\n")
    print("| file | size MB | sampled time range | backward jumps | sorted runs (byte fraction: time range) |")
    print("|---|---|---|---|---|")
    for p in files_of(day_dir):
        _, i = ts_index(p)
        scale = 1000.0 if p.name in MS_FILES else 1.0
        size = p.stat().st_size
        with open(p, "rb") as fh:
            ts = [ts_at(fh, int(size * k / n), i) for k in range(n)]
        ts = [(k, t / scale) for k, t in enumerate(ts) if t is not None]
        starts = [0] + [j for j in range(1, len(ts)) if ts[j - 1][1] - ts[j][1] > 120] + [len(ts)]
        runs = list(zip(starts, starts[1:]))
        if len(runs) <= 12:
            desc = "<br>".join(f"{ts[a][0] / n:.3f}–{ts[b - 1][0] / n:.3f}: "
                               f"{fmt_ts(ts[a][1])[11:16]}–{fmt_ts(ts[b - 1][1])[11:16]}" for a, b in runs)
        else:
            desc = f"{len(runs)} runs (not time-sorted)"
        lo, hi = min(t for _, t in ts), max(t for _, t in ts)
        print(f"| {p.name} | {size / 1e6:,.0f} | {fmt_ts(lo)[11:16]}–{fmt_ts(hi)[11:16]} | {len(runs) - 1} | {desc} |")


# 3 ---------------------------------------------------------------------------
def utc8_check(dataset: Path) -> None:
    h("3. UTC+8 check")
    q = pd.read_csv(dataset / "dev" / "query_dev.csv")
    pat = re.compile(r"The (?:\d+-th|only) predicted root cause component is ([^\n]+)")
    tpat = re.compile(r"occurrence time is within 1 minutes \(i\.e\., <=1min\) of ([^\n]+)")
    checked = 0
    for _, row in q.iterrows():
        comps, times = pat.findall(row.scoring_points), tpat.findall(row.scoring_points)
        if len(comps) != 1 or len(times) != 1:
            continue
        comp, t = comps[0].strip(), times[0].strip()
        if not re.search(r"-\d+$", comp):
            continue   # services have no metric_container / metric_node series of their own
        case = parse_instruction(row.instruction)
        ans = datetime.strptime(t, "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC8).timestamp()
        day_folder = datetime.fromtimestamp(ans, tz=UTC8).strftime("%Y_%m_%d")
        in_window = case.lo_ts <= ans <= case.hi_ts
        # the answer component's strongest metric change, at UTC+8 epoch vs 8 h away
        near = best_shift(dataset / "telemetry" / day_folder, comp, ans)
        print(f"- row {row.row_id} · answer `{t}` UTC+8 → epoch {ans:.0f}; "
              f"inside the instruction window (parsed as UTC+8): **{in_window}**; "
              f"day folder `{day_folder}` exists: **{(dataset / 'telemetry' / day_folder).exists()}**")
        for label, r in near.items():
            print(f"    - {label}: {r}")
        checked += 1
        if checked == 3:
            break


def best_shift(day_dir: Path, comp: str, ans: float) -> dict:
    """For the answer component, the largest robust-z jump in its metrics within ±5 min of
    `ans` (UTC+8 reading) vs ±5 min of `ans ± 8 h` (what a UTC misreading would imply)."""
    frames = []
    for name in ("metric_container.csv", "metric_node.csv"):
        f = day_dir / "metric" / name
        if f.exists():
            df = pd.read_csv(f, usecols=["timestamp", "cmdb_id", "kpi_name", "value"])
            frames.append(df[(df.cmdb_id == comp) | df.cmdb_id.str.endswith("." + comp)])
    if not frames:
        return {"no metrics": comp}
    df = pd.concat(frames)
    out = {}
    for label, centre in (("UTC+8 reading", ans), ("8 h earlier", ans - 28800), ("8 h later", ans + 28800)):
        best = (0.0, "")
        for (cid, kpi), g in df.groupby(["cmdb_id", "kpi_name"]):
            base = g[(g.timestamp >= centre - 3600) & (g.timestamp < centre - 300)].value
            win = g[(g.timestamp >= centre - 300) & (g.timestamp <= centre + 300)]
            if len(base) < 5 or win.empty:
                continue
            med = base.median()
            iqr = max(base.quantile(0.75) - base.quantile(0.25), 0.05 * abs(med), 1e-9)
            z = min(50.0, float(((win.value - med).abs() / iqr).max()))   # capped like Z_CAP
            if z > best[0]:
                w = win.loc[(win.value - med).abs().idxmax()]
                best = (z, f"z {z:.1f} (capped at 50) on `{cid}` · `{kpi}`: value {w.value:g} at "
                           f"{fmt_ts(w.timestamp)} (ts {w.timestamp:.0f}) vs baseline median {med:g}")
        out[label] = best[1] or "no series with data"
    return out


# 4 ---------------------------------------------------------------------------
def sample_rows(path: Path, n_rows: int, usecols: list[str], n_offsets: int = 20) -> pd.DataFrame:
    """~n_rows rows read in n_offsets blocks spread through the file."""
    header = open(path, "rb").readline()
    size = path.stat().st_size
    per = n_rows // n_offsets
    frames = []
    with open(path, "rb") as fh:
        for k in range(n_offsets):
            fh.seek(int(size * k / n_offsets))
            if k:
                fh.readline()
            if not k:
                fh.readline()   # header, already prepended
            block = b"".join(fh.readline() for _ in range(per))
            frames.append(pd.read_csv(io.BytesIO(header + block), usecols=usecols, dtype=str,
                                      on_bad_lines="skip", engine="python" if "log" in path.name else "c"))
    return pd.concat(frames, ignore_index=True)


def units(day_dir: Path) -> None:
    h("4. Units (trace vs metric timestamps, trace duration)")
    tr = sample_rows(day_dir / "trace" / "trace_span.csv", 100_000,
                     ["timestamp", "cmdb_id", "duration", "type", "status_code", "parent_span"])
    ts = pd.to_numeric(tr.timestamp, errors="coerce")
    d = pd.to_numeric(tr.duration, errors="coerce")
    mc = pd.read_csv(day_dir / "metric" / "metric_container.csv", nrows=1000, usecols=["timestamp"])
    print(f"- trace_span.timestamp median {ts.median():.0f} (≈{ts.median():.2e}) → milliseconds; "
          f"as seconds/1000: {fmt_ts(ts.median() / 1000)} UTC+8")
    print(f"- metric_container.timestamp median {mc.timestamp.median():.0f} (≈{mc.timestamp.median():.2e}) → seconds")
    print(f"- trace_span.duration over {len(d):,} sampled rows: median {d.median():,.0f}, "
          f"p90 {d.quantile(.9):,.0f}, p99 {d.quantile(.99):,.0f}, max {d.max():,.0f}")
    # Unit proof: a child span starts inside its parent. If duration is µs, then
    # child_ts - parent_ts (ms) <= parent.duration / 1000 for nearly every pair.
    blk = contiguous_rows(day_dir / "trace" / "trace_span.csv", 300_000)
    j = blk.merge(blk[["trace_id", "span_id", "timestamp", "duration"]], left_on=["trace_id", "parent_span"],
                  right_on=["trace_id", "span_id"], suffixes=("", "_p"))
    start_ms = j.timestamp - j.timestamp_p
    print(f"- parent/child pairs in a contiguous 300 k-row block: {len(j):,}")
    print(f"  - child starts within parent if duration is **µs** (≤ duration/1000 ms after parent start): "
          f"{((start_ms >= -1) & (start_ms <= j.duration_p / 1000 + 1)).mean():.1%}")
    print(f"  - child duration ≤ parent duration: {(j.duration <= j.duration_p).mean():.1%}")
    print(f"  - median child start offset {start_ms.median():.0f} ms vs median parent duration "
          f"{j.duration_p.median():,.0f} (unit under test)")
    return tr


def contiguous_rows(path: Path, n: int) -> pd.DataFrame:
    """n rows from the middle of the file (a sorted run, so parents and children are together)."""
    with open(path, "rb") as fh:
        header = fh.readline()
        fh.seek(path.stat().st_size // 2)
        fh.readline()
        block = b"".join(fh.readline() for _ in range(n))
    return pd.read_csv(io.BytesIO(header + block), usecols=["timestamp", "span_id", "trace_id", "duration",
                                                             "parent_span"], dtype={"span_id": str, "trace_id": str,
                                                                                    "parent_span": str})


# 5 ---------------------------------------------------------------------------
def sampling(day_dir: Path) -> None:
    h("5. Sampling interval (median diff between consecutive timestamps of one series)")
    for name in ("metric_container.csv", "metric_node.csv", "metric_service.csv"):
        f = day_dir / "metric" / name
        if name == "metric_service.csv":
            df = pd.read_csv(f)
            keys = ["service"]
        else:
            df = pd.read_csv(f, usecols=["timestamp", "cmdb_id", "kpi_name"])
            keys = ["cmdb_id", "kpi_name"]
        df = df.sort_values(keys + ["timestamp"])
        diffs = df.groupby(keys, observed=True).timestamp.diff().dropna()
        per_series = df.groupby(keys, observed=True).timestamp.diff().groupby(
            [df[k] for k in keys], observed=True).median()
        print(f"- {name}: median diff {diffs.median():.0f} s over all series; "
              f"per-series medians: {per_series.value_counts().head(5).to_dict()}")


# 6 ---------------------------------------------------------------------------
def distinct(day_dir: Path, tr: pd.DataFrame) -> None:
    h("6. Distinct values")
    for name in ("metric_container.csv", "metric_node.csv"):
        f = day_dir / "metric" / name
        df = pd.read_csv(f, usecols=["cmdb_id", "kpi_name"], dtype="category")
        kpis = sorted(df.kpi_name.cat.categories)
        ids = sorted(df.cmdb_id.cat.categories)
        print(f"### {name}: {len(ids)} cmdb_id, {len(kpis)} kpi_name")
        print(f"cmdb_id examples: {', '.join('`'+i+'`' for i in ids[:8])}")
        if name == "metric_container.csv":
            no_dot = [i for i in ids if "." not in i]
            print(f"cmdb_id without a `.` (not `<node>.<pod>`): {no_dot or 'none'}")
            pods = sorted({i.split('.', 1)[1] for i in ids if '.' in i})
            print(f"pods ({len(pods)}): {', '.join(pods)}")
        print("\nkpi_name:\n```")
        for k in kpis:
            print(k)
        print("```")
    svc = pd.read_csv(day_dir / "metric" / "metric_service.csv", usecols=["service"])
    print(f"### metric_service.csv service values\n{sorted(svc.service.unique())}")
    print(f"\n### trace_span (100 k-row sample)\n- type: {tr.type.fillna('<empty>').value_counts().to_dict()}")
    print(f"- status_code: {tr.status_code.fillna('<empty>').value_counts().to_dict()}")
    print(f"- cmdb_id ({tr.cmdb_id.nunique()}): {sorted(tr.cmdb_id.dropna().unique())}")
    print(f"- parent_span empty/NaN: {tr.parent_span.isna().mean():.1%}")
    ls = sample_rows(day_dir / "log" / "log_service.csv", 50_000, ["cmdb_id", "log_name"])
    print(f"\n### log_service.csv (50 k-row sample)\n- log_name: {ls.log_name.value_counts().to_dict()}")
    print(f"- cmdb_id examples: {sorted(ls.cmdb_id.dropna().unique())[:10]}")


# 7 ---------------------------------------------------------------------------
def answer_forms(dataset: Path) -> None:
    h("7. Answer forms in dev/query_dev.csv (label shape only, no names copied into code)")
    q = pd.read_csv(dataset / "dev" / "query_dev.csv")
    comps, reasons = [], []
    for sp in q.scoring_points:
        comps += re.findall(r"The (?:\d+-th|only) predicted root cause component is ([^\n]+)", sp)
        reasons += re.findall(r"The (?:\d+-th|only) predicted root cause reason is ([^\n]+)", sp)

    def form(c: str) -> str:
        c = c.strip()
        if re.fullmatch(r"node-\d+", c):
            return "node (`node-N`)"
        if re.fullmatch(r"[a-z][a-z0-9-]*-\d+", c):
            return "pod (`name-N`)"
        if re.fullmatch(r"[a-z][a-z0-9-]*[a-z]", c):
            return "service (bare `name`, no trailing -N)"
        return "other"
    print(f"- component forms ({len(comps)} labels): {dict(Counter(map(form, comps)))}")
    svc = sorted({c.strip() for c in comps if form(c).startswith("service")})
    pods = {m.group(1) for m in (re.match(r"(.+)-\d+$", c.strip()) for c in comps) if m}
    print(f"  - bare-service labels that also exist as a pod prefix in the labels: "
          f"{sum(x in pods for x in svc)}/{len(svc)} distinct")
    other = sorted({c for c in comps if form(c) == 'other'})
    if other:
        print(f"  - 'other' shapes: {[re.sub(r'[a-z]', 'x', o) for o in other]}")
    print(f"- reasons ({len(reasons)} labels; component labels {len(comps)}: they differ because tasks ask different fields):")
    for r, n in Counter(x.strip() for x in reasons).most_common():
        print(f"  - {r}: {n}")
    n = [max(len(re.findall(p, sp)) for p in ("-th predicted root cause component", "-th predicted root cause reason",
                                               "-th root cause occurrence time")) or 1 for sp in q.scoring_points]
    print(f"- failures per case: {dict(sorted(Counter(n).items()))}")
    print(f"- task_index counts: {dict(sorted(Counter(q.task_index).items()))}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="data/Market-cloudbed-1", type=Path)
    ap.add_argument("--day", default="2022_03_20")
    args = ap.parse_args()
    day_dir = args.dataset / "telemetry" / args.day
    t0 = time.time()
    print(f"# Trap verification — {args.dataset} / {args.day}")
    headers(day_dir)
    sortedness(day_dir)
    utc8_check(args.dataset)
    tr = units(day_dir)
    sampling(day_dir)
    distinct(day_dir, tr)
    answer_forms(args.dataset)
    print(f"\n_verify_traps.py ran in {time.time() - t0:.0f} s_")


if __name__ == "__main__":
    main()
