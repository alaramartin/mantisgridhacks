"""Stage 1: load one case's window plus its baseline, normalized. No LLM.

- Every `ts` is epoch **seconds** (trace timestamps are ms in the file; divided once, here).
- Trace `duration` is **µs** in the file (docs/data-notes.md); `*_ms` columns are milliseconds.
- `log_service.csv`: only error-looking lines, one chunked pass per day, cached (config LOAD_LOGS).
- Metric files are grouped by series, not time, so each day is read once and cached
  in-process (metric_container: 1.4 s, 67 MB per day). `trace_span.csv` is sliced by
  byte offset (origin/timeslice.py). `log_proxy.csv` is never read.
- Topology comes from names only: `node-5.adservice-2` -> pod `adservice-2` on `node-5`.
"""
from __future__ import annotations

import re
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from origin.config import BASELINE_S, EDGE_BUCKET_S, LOAD_LOGS, READ_PAD_S
from origin.contract import UTC8, Case, Window
from origin.timeslice import read_slice

TRACE_OK = {"0", "Ok", "OK", "ok", "200", ""}     # status_code values that are not errors (data-notes)
TRACE_MIN_LEFT_S = 20                            # skip traces if the deadline is closer than this
LOG_MIN_LEFT_S = 35                              # skip an uncached log day if the deadline is closer than this
LOG_ERROR = r"error|exception|fail|fatal"
LOG_TEXT_MAX = 200
_SERVICE_SUFFIX = re.compile(r"-(grpc|http)$")
_POD_INDEX = re.compile(r"-\d+$")

_day_cache: dict = {}   # (path, mtime) -> DataFrame


def _day_folder(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=UTC8).strftime("%Y_%m_%d")


def _folders(lo: float, hi: float) -> list[str]:
    out, t = [], lo
    while True:
        d = _day_folder(t)
        if d not in out:
            out.append(d)
        if t >= hi:
            break
        t = min(hi, t + 86400)
    if _day_folder(hi) not in out:
        out.append(_day_folder(hi))
    return out


def _read_day(path: Path, kind: str) -> tuple[pd.DataFrame, dict]:
    key = (str(path), path.stat().st_mtime)
    t0 = time.time()
    if key in _day_cache:
        return _day_cache[key], {"rows": len(_day_cache[key]), "bytes": 0, "seconds": 0.0, "method": "day-cache"}
    if kind == "service":
        df = pd.read_csv(path, dtype={"service": "category"})
    else:
        df = pd.read_csv(path, usecols=["timestamp", "cmdb_id", "kpi_name", "value"],
                         dtype={"cmdb_id": "category", "kpi_name": "category", "value": "float64"})
    _day_cache[key] = df
    return df, {"rows": len(df), "bytes": path.stat().st_size, "seconds": round(time.time() - t0, 3),
                "method": "day-read"}


def _slice(df: pd.DataFrame, lo: float, hi: float) -> pd.DataFrame:
    t = df["timestamp"]
    return df[(t >= lo) & (t < hi)]


def _metric_frame(sub: pd.DataFrame, source: str) -> pd.DataFrame:
    return pd.DataFrame({
        "ts": sub["timestamp"].astype("float64").to_numpy(),
        "source": source,
        "cmdb_id": sub["cmdb_id"].astype(str).to_numpy(),
        "kpi": sub["kpi_name"].astype(str).to_numpy(),
        "value": sub["value"].to_numpy(),
    })


def _load_metrics(tele: Path, days: list[str], lo: float, hi: float, stats: dict, notes: list[str]) -> pd.DataFrame:
    frames = []
    for day in days:
        for source in ("metric_container", "metric_node", "metric_service"):
            path = tele / day / "metric" / f"{source}.csv"
            if not path.exists():
                notes.append(f"missing {day}/metric/{source}.csv")
                continue
            kind = "service" if source == "metric_service" else "metric"
            df, st = _read_day(path, kind)
            sub = _slice(df, lo, hi)
            stats["files"][f"{day}/{source}.csv"] = {**st, "rows": len(sub)}
            if sub.empty:
                continue
            if kind == "service":
                long = sub.melt(id_vars=["service", "timestamp"], value_vars=["rr", "sr", "mrt", "count"],
                                var_name="kpi_name", value_name="value").rename(columns={"service": "cmdb_id"})
                frames.append(_metric_frame(long, source))
            else:
                frames.append(_metric_frame(sub, source))
    if not frames:
        return pd.DataFrame(columns=["ts", "source", "cmdb_id", "component", "level", "kpi", "value"])
    m = pd.concat(frames, ignore_index=True)
    m = m[np.isfinite(m["value"].to_numpy())].reset_index(drop=True)
    level = np.select([m.source == "metric_container", m.source == "metric_node"], ["pod", "node"], "service")
    comp = np.where(level == "pod", m.cmdb_id.str.split(".", n=1).str[1],
                    np.where(level == "service", m.cmdb_id.str.replace(_SERVICE_SUFFIX, "", regex=True), m.cmdb_id))
    m.insert(3, "component", comp)
    m.insert(4, "level", level)
    return m


def service_of(pods: set[str], known_services: set[str] = frozenset()) -> dict[str, str]:
    """pod -> service by stripping the trailing `-<index>`. A second deployment of a service
    (`<name>2-0`) maps to `<name>` when `<name>` is a service in its own right (another pod's
    base, or a metric_service name). No component name is written here."""
    base = {p: _POD_INDEX.sub("", p) for p in pods}
    services = set(base.values()) | set(known_services)
    out = {}
    for p, b in base.items():
        alt = re.sub(r"\d+$", "", b)
        out[p] = alt if alt and alt != b and alt in (services - {b}) else b
    return out


def _load_traces(tele: Path, days: list[str], lo: float, hi: float, stats: dict,
                 notes: list[str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    frames = []
    for day in days:
        path = tele / day / "trace" / "trace_span.csv"
        if not path.exists():
            notes.append(f"missing {day}/trace/trace_span.csv")
            continue
        df, st = read_slice(path, lo, hi, "timestamp", 1000,
                            usecols=["timestamp", "cmdb_id", "span_id", "trace_id", "duration",
                                     "status_code", "parent_span"],
                            dtype={"cmdb_id": "category", "span_id": str, "trace_id": str,
                                   "status_code": str, "parent_span": str, "duration": "float64"})
        stats["files"][f"{day}/trace_span.csv"] = st
        frames.append(df)
    edge_cols = ["ts", "trace_id", "caller", "callee", "parent_ms", "child_ms", "gap_ms", "error"]
    span_cols = ["ts", "pod", "count", "errors", "p50_ms"]
    if not frames:
        return pd.DataFrame(columns=edge_cols), pd.DataFrame(columns=span_cols)
    s = pd.concat(frames, ignore_index=True)
    s = pd.DataFrame({
        "ts": s["timestamp"].to_numpy() / 1000.0,
        "pod": s["cmdb_id"].astype(str).to_numpy(),
        "span_id": s["span_id"].to_numpy(),
        "trace_id": s["trace_id"].to_numpy(),
        "parent_span": s["parent_span"].to_numpy(),
        "ms": s["duration"].to_numpy() / 1000.0,          # µs -> ms
        "error": ~s["status_code"].fillna("").isin(TRACE_OK).to_numpy(),
    })

    bucket = np.floor(s["ts"] / EDGE_BUCKET_S) * EDGE_BUCKET_S
    pod_spans = (s.assign(ts=bucket).groupby(["ts", "pod"], observed=True)
                 .agg(count=("ms", "size"), errors=("error", "sum"), p50_ms=("ms", "median"))
                 .reset_index())

    parents = s[["trace_id", "span_id", "pod", "ms"]].rename(
        columns={"span_id": "parent_span", "pod": "caller", "ms": "parent_ms"})
    j = s[s["parent_span"].notna()].merge(parents, on=["trace_id", "parent_span"], how="inner")
    j = j[j["pod"] != j["caller"]]
    n_children = j.groupby(["trace_id", "parent_span"])["span_id"].transform("size")
    edges = pd.DataFrame({
        "ts": j["ts"].to_numpy(),
        "trace_id": j["trace_id"].to_numpy(),
        "caller": j["caller"].to_numpy(),
        "callee": j["pod"].to_numpy(),
        "parent_ms": j["parent_ms"].to_numpy(),
        "child_ms": j["ms"].to_numpy(),
        "gap_ms": np.where(n_children.to_numpy() == 1, (j["parent_ms"] - j["ms"]).to_numpy(), np.nan),
        "error": j["error"].to_numpy(),
    }).sort_values("ts", kind="stable").reset_index(drop=True)
    return edges, pod_spans[span_cols]


def _log_day(path: Path) -> tuple[pd.DataFrame, dict]:
    """Error-looking lines of one log_service.csv day (the file isn't time-sorted: one chunked
    pass, then cached). Only error lines are kept, so `is_error` is always True."""
    key = (str(path), path.stat().st_mtime)
    if key in _day_cache:
        df = _day_cache[key]
        return df, {"rows": len(df), "bytes": 0, "seconds": 0.0, "method": "day-cache"}
    t0 = time.time()
    frames = []
    for ch in pd.read_csv(path, usecols=["timestamp", "cmdb_id", "value"],
                          dtype={"cmdb_id": "category", "value": str}, chunksize=1_000_000):
        e = ch[ch["value"].str.contains(LOG_ERROR, case=False, na=False)]
        frames.append(pd.DataFrame({"ts": e["timestamp"].astype("float64").to_numpy(),
                                    "pod": e["cmdb_id"].astype(str).to_numpy(), "is_error": True,
                                    "text": e["value"].str.slice(0, LOG_TEXT_MAX).to_numpy()}))
    df = pd.concat(frames, ignore_index=True)
    _day_cache[key] = df
    return df, {"rows": len(df), "bytes": path.stat().st_size, "seconds": round(time.time() - t0, 3),
                "method": "chunked-day"}


def _load_logs(tele: Path, days: list[str], lo: float, hi: float, stats: dict, notes: list[str],
               deadline_ts: float | None) -> pd.DataFrame | None:
    frames = []
    for day in days:
        path = tele / day / "log" / "log_service.csv"
        if not path.exists():
            notes.append(f"missing {day}/log/log_service.csv")
            continue
        cached = (str(path), path.stat().st_mtime) in _day_cache
        if not cached and deadline_ts is not None and time.time() > deadline_ts - LOG_MIN_LEFT_S:
            notes.append(f"logs for {day} skipped: too close to the per-case deadline")
            continue
        df, st = _log_day(path)
        sub = df[(df.ts >= lo) & (df.ts < hi)]
        stats["files"][f"{day}/log_service.csv"] = {**st, "rows": len(sub)}
        frames.append(sub)
    return pd.concat(frames, ignore_index=True) if frames else None


def load_window(case: Case, dataset_dir: Path, deadline_ts: float | None = None) -> Window:
    """Metrics, trace edges and per-pod span stats for [baseline start, window end], plus topology.
    `deadline_ts` (epoch s, optional) skips the trace read when too little time is left."""
    t0 = time.time()
    tele = Path(dataset_dir) / "telemetry"
    notes: list[str] = []
    stats: dict = {"files": {}}

    base_lo, base_hi = case.lo_ts - BASELINE_S, case.lo_ts
    read_lo, read_hi = base_lo, case.hi_ts
    if not (tele / _day_folder(base_lo)).exists():
        base_lo, base_hi = case.hi_ts, case.hi_ts + BASELINE_S
        read_lo, read_hi = case.lo_ts, base_hi
        notes.append(f"no telemetry folder {_day_folder(case.lo_ts - BASELINE_S)} for the baseline before "
                     f"the window; baseline is the {BASELINE_S // 60} min after the window instead")
    days = [d for d in _folders(read_lo - READ_PAD_S, read_hi + READ_PAD_S) if (tele / d).exists()]
    lo, hi = read_lo - READ_PAD_S, read_hi + READ_PAD_S

    metrics = _load_metrics(tele, days, lo, hi, stats, notes)

    if deadline_ts is not None and time.time() > deadline_ts - TRACE_MIN_LEFT_S:
        notes.append("traces skipped: too close to the per-case deadline (blind to network faults here)")
        edges, pod_spans = _load_traces(tele, [], lo, hi, stats, notes)
    else:
        edges, pod_spans = _load_traces(tele, days, lo, hi, stats, notes)

    logs = _load_logs(tele, days, lo, hi, stats, notes, deadline_ts) if LOAD_LOGS else None

    pod_rows = metrics[metrics.level == "pod"]
    pod_node = dict(zip(pod_rows.component, pod_rows.cmdb_id.str.split(".", n=1).str[0]))
    pods = set(pod_node) | set(edges["caller"]) | set(edges["callee"]) | set(pod_spans["pod"])
    svc_names = set(metrics.loc[metrics.level == "service", "component"])
    pod_service = service_of(pods, svc_names)
    nodes = set(metrics.loc[metrics.level == "node", "component"]) | set(pod_node.values())
    services = set(pod_service.values()) | svc_names

    stats["load_s"] = round(time.time() - t0, 3)
    stats["notes"] = notes
    return Window(case=case, base_lo_ts=base_lo, base_hi_ts=base_hi, metrics=metrics, edges=edges,
                  pod_spans=pod_spans, logs=logs, pod_node=pod_node, pod_service=pod_service,
                  nodes=nodes, pods=pods, services=services, stats=stats)
