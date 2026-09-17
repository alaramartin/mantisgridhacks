"""A baseline with no model in it at all.

Deliberately simple, deliberately explainable, and free to run. It exists so
"good" has a floor: if your LLM agent cannot beat plain z-scores, the model is
not the thing adding value and you should find out on day one rather than day two.

The method, in full:

  1. parse the time window out of the instruction
  2. for every (component, kpi) series, compare in-window values to the rest of
     the day -- robust z-score, median and MAD, so one spike does not set the scale
  3. rank components by their strongest anomalous KPI
  4. map the winning KPI name to a failure reason with keyword rules
  5. put the peak timestamp of that KPI forward as the occurrence time

Everything it looks at is a metric. It never opens a log or a trace, which is
roughly half the available signal. That is the most obvious thing to improve.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from run import Solution, format_prediction   # noqa: E402

_CACHE: dict = {}

MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july",
     "august", "september", "october", "november", "december"], 1)}


def parse_window(instruction: str) -> tuple[datetime, datetime] | None:
    """Pull 'March 20, 2022, from 09:00 to 09:30' out of the prose."""
    # The second bound may name its own date -- "from 23:30 to March 22, 2022, at
    # 00:00" -- so allow arbitrary text between the two clock times.
    m = re.search(r"(\w+)\s+(\d{1,2}),?\s+(\d{4}).{0,40}?(\d{1,2}):(\d{2})"
                  r"\s*(?:to|-|and|until)\s*.{0,40}?(\d{1,2}):(\d{2})",
                  instruction, re.I | re.S)
    if not m:
        return None
    mon, day, year, h1, m1, h2, m2 = m.groups()
    if mon.lower() not in MONTHS:
        return None
    base = datetime(int(year), MONTHS[mon.lower()], int(day), tzinfo=timezone.utc)
    lo = base + timedelta(hours=int(h1), minutes=int(m1))
    hi = base + timedelta(hours=int(h2), minutes=int(m2))
    if hi <= lo:
        hi += timedelta(days=1)
    return lo, hi


def failure_count(instruction: str) -> int:
    """The instruction states how many failures are in the window. Getting this
    wrong scores zero for the whole case however good the answer is."""
    t = instruction.lower()
    for word, n in (("one failure", 1), ("a single failure", 1), ("two failures", 2),
                    ("three failures", 3), ("four failures", 4)):
        if word in t:
            return n
    return 1


def _load_day(dataset: Path, date: str) -> pd.DataFrame:
    key = (str(dataset), date)
    if key in _CACHE:
        return _CACHE[key]
    frames = []
    for name in ("metric_container", "metric_node"):
        f = dataset / "telemetry" / date / "metric" / f"{name}.csv"
        if not f.exists():
            continue
        df = pd.read_csv(f, usecols=["timestamp", "cmdb_id", "kpi_name", "value"])
        df["source"] = name
        frames.append(df)
    out = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(
        columns=["timestamp", "cmdb_id", "kpi_name", "value", "source"])
    _CACHE[key] = out
    return out


def component_of(cmdb_id: str) -> str:
    """metric_container is '<node>.<pod>'; metric_node is just the node."""
    return cmdb_id.split(".", 1)[1] if "." in cmdb_id else cmdb_id


# The two levels have DIFFERENT vocabularies, and the asymmetry matters: there is
# no node-level network reason at all. A node topping the ranking on a TCP metric
# cannot be explained by any legal node reason -- so we fall through to its next
# best KPI rather than emit something the evaluator will never match.
NODE_REASONS = {"cpu": "node CPU load", "spike": "node CPU spike",
                "memory": "node memory consumption",
                "read": "node disk read I/O consumption",
                "write": "node disk write I/O consumption",
                "space": "node disk space consumption"}
POD_REASONS = {"cpu": "container CPU load", "memory": "container memory load",
               "read": "container read I/O load", "write": "container write I/O load",
               "latency": "container network latency",
               "loss": "container packet loss",
               "retrans": "container network packet retransmission",
               "corrupt": "container network packet corruption",
               "kill": "container process termination"}


def reason_for(kpi: str, component: str) -> str | None:
    """None means: this KPI has no legal reason at this component's level."""
    k = kpi.lower()
    is_node = component.startswith("node-")
    table = NODE_REASONS if is_node else POD_REASONS
    if any(f in k for f in ("disk_read", "read_bytes", "diskio_read", "read_io")):
        return table.get("read")
    if any(f in k for f in ("disk_write", "write_bytes", "diskio_write", "write_io")):
        return table.get("write")
    if any(f in k for f in ("disk_space", "fs_usage", "disk_usage", "filesystem")):
        return table.get("space")
    if any(f in k for f in ("memory", "mem_", "pgfault")):
        return table.get("memory")
    if "cpu" in k:
        return table.get("cpu")
    if any(f in k for f in ("packet_loss", "drop")):
        return table.get("loss")
    if "retrans" in k:
        return table.get("retrans")
    if "corrupt" in k:
        return table.get("corrupt")
    if any(f in k for f in ("latency", "rtt", "delay", "network", "net_", "tcp",
                            "rx", "tx", "receive", "transmit")):
        return table.get("latency")
    return None


@dataclass
class Analysis:
    """Steps 1-3 for one case: the window, a z-score per series, the ranking."""
    lo: datetime
    hi: datetime
    n: int                 # failures the instruction asks for
    ev: list[str]          # evidence written so far
    j: pd.DataFrame        # one row per (cmdb_id, kpi_name): z, component, ...; z desc
    inw: pd.DataFrame      # the samples inside the window
    ranked: pd.Series      # component -> strongest z, desc


def analyse(instruction: str, dataset_dir: Path) -> Analysis | Solution:
    """Steps 1-3. Returns a Solution instead when there is nothing to rank."""
    win = parse_window(instruction)
    if win is None:
        return Solution(prediction=format_prediction([{}]),
                        evidence="Could not parse a time window from the instruction.\n")
    lo, hi = win
    date = lo.strftime("%Y_%m_%d")
    day = _load_day(Path(dataset_dir), date)
    ev = [f"# Case\n\n**Window:** {lo:%Y-%m-%d %H:%M} to {hi:%H:%M} UTC  ",
          f"**Telemetry day:** `{date}`  ",
          f"**Rows loaded:** {len(day):,} (metric only -- no logs, no traces)\n"]

    if day.empty:
        return Solution(prediction=format_prediction([{}]),
                        evidence="\n".join(ev) + "\nNo metric data for that day.\n")

    lo_s, hi_s = lo.timestamp(), hi.timestamp()
    inw = day[(day.timestamp >= lo_s) & (day.timestamp < hi_s)]
    out = day[(day.timestamp < lo_s) | (day.timestamp >= hi_s)]
    if inw.empty:
        return Solution(prediction=format_prediction([{}]),
                        evidence="\n".join(ev) + "\nNo samples inside the window.\n")

    base = out.groupby(["cmdb_id", "kpi_name"]).value.agg(
        med="median", mad=lambda s: (s - s.median()).abs().median())
    peak = inw.groupby(["cmdb_id", "kpi_name"]).value.agg(["max", "min", "mean"])
    j = peak.join(base, how="inner").reset_index()
    j = j[j.mad > 0]
    if j.empty:
        return Solution(prediction=format_prediction([{}]),
                        evidence="\n".join(ev) + "\nNo series with non-zero variation.\n")

    # robust z, both directions -- a failure can be a spike or a collapse
    j["z"] = np.maximum((j["max"] - j.med).abs(), (j["min"] - j.med).abs()) / (1.4826 * j.mad)
    j["component"] = j.cmdb_id.map(component_of)
    j = j.sort_values("z", ascending=False)

    ranked = (j.groupby("component").z.max().sort_values(ascending=False))
    return Analysis(lo=lo, hi=hi, n=failure_count(instruction), ev=ev, j=j, inw=inw,
                    ranked=ranked)


def answer_for(a: Analysis, comp: str) -> dict:
    """Steps 4-5 for one component: its strongest KPI with a legal reason, and
    that KPI's peak time."""
    sub = a.j[a.j.component == comp]
    top, chosen = sub.iloc[0], None
    for _, row in sub.iterrows():          # first KPI with a legal reason
        r = reason_for(row.kpi_name, comp)
        if r:
            top, chosen = row, r
            break
    if chosen is None:
        chosen = "node CPU load" if comp.startswith("node-") else "container CPU load"
    series = a.inw[(a.inw.cmdb_id == top.cmdb_id) & (a.inw.kpi_name == top.kpi_name)]
    when = a.lo
    if not series.empty:
        when = datetime.fromtimestamp(
            float(series.loc[(series.value - top.med).abs().idxmax(), "timestamp"]),
            tz=timezone.utc)
    return {"datetime": when.strftime("%Y-%m-%d %H:%M:%S"), "component": comp,
            "reason": chosen}


def solve(instruction: str, dataset_dir: Path, ctx: dict) -> Solution:
    a = analyse(instruction, dataset_dir)
    if isinstance(a, Solution):
        return a
    ev, j, n = a.ev, a.j, a.n
    ev.append(f"**Failures asked for:** {n}\n")
    ev.append("## Top components by strongest anomalous KPI\n")
    ev.append("| rank | component | peak z | KPI |")
    ev.append("|---|---|---|---|")
    for i, (comp, z) in enumerate(a.ranked.head(max(8, n)).items(), 1):
        kpi = j[j.component == comp].iloc[0].kpi_name
        ev.append(f"| {i} | `{comp}` | {z:.1f} | `{kpi}` |")
    answers = [answer_for(a, comp) for comp in a.ranked.head(n).index]

    ev.append("\n## Answer\n")
    for i, x in enumerate(answers, 1):
        ev.append(f"{i}. `{x['component']}` — {x['reason']} — {x['datetime']}")
    ev.append("\n## How much to trust this\n")
    ev.append("Not much. The reason is a keyword match on the KPI name, not an "
              "inference. The time is the peak sample of one series, which is when "
              "the symptom was largest, not necessarily when the fault began. "
              "Logs and traces were never opened.")
    return Solution(prediction=format_prediction(answers), evidence="\n".join(ev) + "\n")
