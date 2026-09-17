"""Shared contract (PLAN.md §1–§3). Both people build against this; change it only
after telling the other person and logging it in PLAN.md's CHECKPOINT LOG."""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
import pandas as pd

UTC8 = timezone(timedelta(hours=8))
TIME_FMT = "%Y-%m-%d %H:%M:%S"
LEVELS = ("node", "pod", "service")

NODE_REASONS = (
    "node CPU load", "node CPU spike", "node disk read I/O consumption",
    "node disk space consumption", "node disk write I/O consumption", "node memory consumption",
)
POD_REASONS = (
    "container CPU load", "container memory load", "container network latency",
    "container network packet corruption", "container network packet retransmission",
    "container packet loss", "container process termination",
    "container read I/O load", "container write I/O load",
)
NETWORK_REASONS = (
    "container network latency", "container network packet corruption",
    "container network packet retransmission", "container packet loss",
)


def legal_reasons(level: str) -> tuple[str, ...]:
    return NODE_REASONS if level == "node" else POD_REASONS   # services take container reasons


def fmt_ts(ts: float) -> str:          # epoch seconds -> "YYYY-mm-dd HH:MM:SS" in UTC+8
    return datetime.fromtimestamp(ts, tz=UTC8).strftime(TIME_FMT)


@dataclass
class Case:
    instruction: str
    n_failures: int                     # from the instruction; getting this wrong zeroes the case
    asks: dict[str, bool]               # {"datetime": bool, "component": bool, "reason": bool}
    lo_ts: float                        # window start, epoch seconds (instruction time read as UTC+8)
    hi_ts: float                        # window end
    days: list[str]                     # telemetry folders needed incl. baseline, e.g. ["2022_03_20"]
    notes: list[str] = field(default_factory=list)


@dataclass
class Window:
    case: Case
    base_lo_ts: float                   # baseline actually used
    base_hi_ts: float
    metrics: pd.DataFrame               # ts(float s), source(str file stem), cmdb_id(str), component(str),
                                        #   level(str), kpi(str), value(float)
    edges: pd.DataFrame                 # ts(float s), trace_id, caller(pod), callee(pod),
                                        #   parent_ms, child_ms, gap_ms, error(bool)
    pod_spans: pd.DataFrame             # ts(float s, 30 s bucket start), pod, count, errors, p50_ms
    logs: pd.DataFrame | None           # ts(float s), pod, is_error(bool), text(str, ≤ 200 chars)
    pod_node: dict[str, str]            # "adservice-2" -> "node-5"
    pod_service: dict[str, str]         # "adservice-2" -> "adservice"
    nodes: set[str]
    pods: set[str]
    services: set[str]
    stats: dict                         # {"files": {name: {"rows","bytes","seconds","method"}}, "load_s": float}


@dataclass
class Signal:
    id: str                             # "F1", "F2", ... (the fact ID shown to models and in evidence)
    kind: str                           # "metric" | "edge_gap" | "edge_errors" | "disappear" | "pod_errors" | "log_errors"
    component: str                      # the component this signal is evidence about
    level: str                          # "node" | "pod" | "service"
    source: str                         # "metric_container.csv", "trace_span.csv", ...
    cmdb_id: str                        # raw cmdb_id (edges: "caller → callee")
    kpi: str                            # raw kpi_name, or "call gap ms" / "call errors" / "series missing"
    score: float                        # sustained robust z (capped)
    onset_ts: float | None              # epoch s of the first sustained breach
    direction: str                      # "up" | "down"
    base_median: float
    base_n: int
    first_value: float | None           # raw value at onset_ts
    peak_ts: float
    peak_value: float                   # raw value at peak_ts
    breach_samples: int
    reason_votes: dict[str, float]      # legal reason -> weight


@dataclass
class Candidate:
    cid: str                            # "C1", "C2", ... in rank order
    component: str
    level: str
    score: float                        # after the causal filter
    raw_score: float                    # before
    onset_ts: float | None              # earliest onset among its signals
    support: int                        # distinct anomalous signals
    reasons: list[tuple[str, float]]    # legal reasons, best first
    signal_ids: list[str]               # best first
    demoted_by: str | None              # sentence, e.g. "node-5 went wrong 3 min earlier (F4)"
    promoted_over: list[str]            # pods this node was promoted over


@dataclass
class Analysis:
    case: Case
    signals: dict[str, Signal]
    candidates: list[Candidate]         # ≤ 15, rank order
    margin: float                       # (s1 - s2) / s1, 1.0 if one candidate, 0.0 if none
    engine_answers: list[dict]          # exactly n dicts: {"datetime","component","reason","cid","signal_ids"} (chronological)
    window_stats: dict
    timings: dict                       # {"load_s","signals_s","candidates_s","total_s"}
    notes: list[str]
