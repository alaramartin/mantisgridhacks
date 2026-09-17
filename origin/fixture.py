"""PLACEHOLDER: hand-built Analysis objects until CP3.

Person 2's router, validator, confidence and evidence all take an `Analysis` and
never touch the dataset. Person 1's `origin.engine.analyze` lands at CP3. Until
then these fixtures stand in for it, so the whole Person-2 half can be written,
tested and run end to end (`ORIGIN_FIXTURE=1`) before the engine exists.

The numbers are plausible, not real: shapes, magnitudes and relationships copied
from the CP1 findings (`docs/data-notes.md`) -- a read-I/O failure on a pod, its
node above it, a caller demoted because its callee broke first, an `edge_gap`
signal from traces, and a quiet second node.

Delete this file, and `ORIGIN_FIXTURE`, once `analyze()` is real.
"""
from __future__ import annotations

from origin.contract import Analysis, Candidate, Case, Signal, fmt_ts

# 2022-03-20 09:00:00 UTC+8, the window in the first dev case.
WIN_LO = 1647738000.0
WIN_HI = WIN_LO + 1800          # 09:30
BASE_LO = WIN_LO - 3600         # 08:00
ONSET = WIN_LO + 540            # 09:09:00

INSTRUCTION = (
    "The cloud service system, cloudbed-1, experienced one failure within the time "
    "range of March 20, 2022, from 09:00 to 09:30. The specific component responsible "
    "for this failure and the underlying reason are currently unknown. You are tasked "
    "with identifying the root cause component and the root cause reason."
)


def _case(n_failures: int = 1, asks: dict[str, bool] | None = None) -> Case:
    return Case(
        instruction=INSTRUCTION,
        n_failures=n_failures,
        asks=asks or {"datetime": True, "component": True, "reason": True},
        lo_ts=WIN_LO, hi_ts=WIN_HI,
        days=["2022_03_20"],
        notes=["PLACEHOLDER fixture case, not parsed from the instruction"],
    )


def _sig(id, kind, component, level, source, cmdb_id, kpi, score, onset, direction,
         base_median, first_value, peak_value, breach, votes, base_n=60, peak_off=780):
    return Signal(id=id, kind=kind, component=component, level=level, source=source,
                  cmdb_id=cmdb_id, kpi=kpi, score=score, onset_ts=onset,
                  direction=direction, base_median=base_median, base_n=base_n,
                  first_value=first_value, peak_ts=WIN_LO + peak_off,
                  peak_value=peak_value, breach_samples=breach, reason_votes=votes)


def _signals() -> dict[str, Signal]:
    """Twelve signals across five components, three sources and four kinds."""
    s = [
        # --- shippingservice-1: the real root cause, read I/O ---
        _sig("F1", "metric", "shippingservice-1", "pod", "metric_container.csv",
             "node-5.shippingservice-1", "container_disk_read_bytes", 41.3, ONSET, "up",
             base_median=1.2e5, first_value=9.4e6, peak_value=2.7e7, breach=19,
             votes={"container read I/O load": 1.0}),
        _sig("F2", "metric", "shippingservice-1", "pod", "metric_container.csv",
             "node-5.shippingservice-1", "container_cpu_usage_seconds", 7.8, ONSET + 60, "up",
             base_median=0.08, first_value=0.31, peak_value=0.44, breach=16,
             votes={"container CPU load": 0.4}),
        _sig("F3", "metric", "shippingservice-1", "pod", "metric_container.csv",
             "node-5.shippingservice-1", "container_threads", 4.1, ONSET + 120, "up",
             base_median=38.0, first_value=52.0, peak_value=61.0, breach=11,
             votes={"container CPU load": 0.2}),
        # --- node-5: the pod's node, follows it (so it must NOT be promoted) ---
        _sig("F4", "metric", "node-5", "node", "metric_node.csv",
             "node-5", "node_disk_read_time_ms", 12.6, ONSET + 60, "up",
             base_median=2.0, first_value=88.0, peak_value=310.0, breach=17,
             votes={"node disk read I/O consumption": 1.0}),
        _sig("F5", "metric", "node-5", "node", "metric_node.csv",
             "node-5", "node_cpu_iowait", 6.2, ONSET + 120, "up",
             base_median=0.4, first_value=3.1, peak_value=5.8, breach=14,
             votes={"node CPU load": 0.3}),
        # --- checkoutservice-2: a CALLER of shippingservice-1, demoted ---
        _sig("F6", "edge_gap", "checkoutservice-2", "pod", "trace_span.csv",
             "checkoutservice-2 -> shippingservice-1", "call gap ms", 22.4, ONSET + 30, "up",
             base_median=14.0, first_value=910.0, peak_value=3120.0, breach=18,
             votes={"container network latency": 0.6}),
        _sig("F7", "pod_errors", "checkoutservice-2", "pod", "trace_span.csv",
             "checkoutservice-2", "call errors", 9.1, ONSET + 60, "up",
             base_median=0.0, first_value=3.0, peak_value=27.0, breach=15,
             votes={"container network latency": 0.2}),
        _sig("F8", "log_errors", "checkoutservice-2", "pod", "log_service.csv",
             "checkoutservice-2", "error lines", 5.4, ONSET + 90, "up",
             base_median=0.0, first_value=2.0, peak_value=11.0, breach=12,
             votes={}),
        # --- frontend-0: an edge_gap only, one hop further out ---
        _sig("F9", "edge_gap", "frontend-0", "pod", "trace_span.csv",
             "frontend-0 -> checkoutservice-2", "call gap ms", 15.7, ONSET + 90, "up",
             base_median=31.0, first_value=1240.0, peak_value=3480.0, breach=13,
             votes={"container network latency": 0.6}),
        _sig("F10", "metric", "frontend-0", "pod", "metric_container.csv",
             "node-3.frontend-0", "container_network_receive_bytes", 3.6, ONSET + 150, "down",
             base_median=4.4e5, first_value=1.1e5, peak_value=6.2e4, breach=9,
             votes={"container network latency": 0.2}),
        # --- node-3: quiet, barely over tau; the tail of the ranking ---
        _sig("F11", "metric", "node-3", "node", "metric_node.csv",
             "node-3", "node_memory_usage", 3.4, ONSET + 300, "up",
             base_median=6.1e9, first_value=6.9e9, peak_value=7.1e9, breach=8,
             votes={"node memory consumption": 1.0}),
        _sig("F12", "metric", "node-3", "node", "metric_node.csv",
             "node-3", "node_load5", 3.1, None, "up",
             base_median=1.8, first_value=None, peak_value=2.9, breach=3,
             votes={"node CPU load": 0.3}),
    ]
    return {x.id: x for x in s}


def _candidates(margin: float) -> list[Candidate]:
    """Five candidates. C1's score and C2's are set to produce `margin`."""
    top = 41.3
    second = top * (1.0 - margin)
    return [
        Candidate(cid="C1", component="shippingservice-1", level="pod",
                  score=top, raw_score=top, onset_ts=ONSET, support=3,
                  reasons=[("container read I/O load", 1.0), ("container CPU load", 0.6)],
                  signal_ids=["F1", "F2", "F3"], demoted_by=None, promoted_over=[]),
        Candidate(cid="C2", component="node-5", level="node",
                  score=second, raw_score=12.6 + 6.2, onset_ts=ONSET + 60, support=2,
                  reasons=[("node disk read I/O consumption", 1.0), ("node CPU load", 0.3)],
                  signal_ids=["F4", "F5"], demoted_by=None, promoted_over=[]),
        Candidate(cid="C3", component="checkoutservice-2", level="pod",
                  score=9.7, raw_score=32.3, onset_ts=ONSET + 30, support=3,
                  reasons=[("container network latency", 0.8)],
                  signal_ids=["F6", "F7", "F8"],
                  demoted_by="its callee shippingservice-1 went wrong 30 s earlier (F1)",
                  promoted_over=[]),
        Candidate(cid="C4", component="frontend-0", level="pod",
                  score=5.8, raw_score=19.3, onset_ts=ONSET + 90, support=2,
                  reasons=[("container network latency", 0.8)],
                  signal_ids=["F9", "F10"],
                  demoted_by="its callee checkoutservice-2 went wrong 60 s earlier (F6)",
                  promoted_over=[]),
        Candidate(cid="C5", component="node-3", level="node",
                  score=3.4, raw_score=3.4, onset_ts=ONSET + 300, support=2,
                  reasons=[("node memory consumption", 1.0), ("node CPU load", 0.3)],
                  signal_ids=["F11", "F12"], demoted_by=None, promoted_over=[]),
    ]


def _analysis(case: Case, candidates: list[Candidate], margin: float,
              answers: list[dict], notes: list[str]) -> Analysis:
    return Analysis(
        case=case, signals=_signals(), candidates=candidates, margin=margin,
        engine_answers=answers,
        window_stats={"metric_rows": 812_440, "edge_rows": 96_120, "log_rows": 1_842,
                      "pods": 40, "nodes": 6, "services": 10,
                      "base_lo": BASE_LO, "base_hi": WIN_LO},
        timings={"load_s": 2.7, "signals_s": 1.1, "candidates_s": 0.3, "total_s": 4.1},
        notes=["PLACEHOLDER fixture Analysis -- no dataset was read"] + notes,
    )


def _answer(c: Candidate, ts: float | None = None) -> dict:
    return {"datetime": fmt_ts(ts if ts is not None else (c.onset_ts or WIN_LO)),
            "component": c.component,
            "reason": c.reasons[0][0] if c.reasons else "container CPU load",
            "cid": c.cid, "signal_ids": c.signal_ids}


def make_analysis(n_failures: int = 1, asks: dict[str, bool] | None = None) -> Analysis:
    """The ambiguous case: margin 0.22, so the router should call a model."""
    case = _case(n_failures, asks)
    cands = _candidates(margin=0.22)
    if n_failures >= 2:
        # two failures far enough apart that MULTI_FAILURE_SEP_S is satisfied
        cands[4].onset_ts = ONSET + 900
        answers = [_answer(cands[0]), _answer(cands[4])]
    else:
        answers = [_answer(cands[0])]
    return _analysis(case, cands, 0.22, answers,
                     ["C3 and C4 demoted by the causal filter"])


def make_clear_analysis(n_failures: int = 1, asks: dict[str, bool] | None = None) -> Analysis:
    """The obvious case: margin 0.60, support 3 -- the router should gate (no model)."""
    case = _case(n_failures, asks)
    cands = _candidates(margin=0.60)
    return _analysis(case, cands, 0.60, [_answer(cands[0])],
                     ["C1 is 60 % clear of C2; no model call needed"])


def make_empty_analysis(n_failures: int = 1) -> Analysis:
    """Nothing crossed tau: the engine has no candidates and must still answer."""
    case = _case(n_failures)
    return _analysis(case, [], 0.0, [], ["no candidate crossed tau"])
