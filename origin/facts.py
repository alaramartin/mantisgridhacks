"""Stage 3b: render Signals as grep-able fact lines, and ruled-out sentences. No LLM.

Raw numbers are printed as the file holds them (Python's shortest float repr). Long ones are cut, never
rounded, and end in "…", so the printed digits are still a prefix of the raw text in the CSV.
Derived numbers (medians, scores) say what they are.
"""
from __future__ import annotations

from origin.contract import Analysis, Signal, fmt_ts

RAW_SIG_DIGITS = 6


def raw(v: float | None) -> str:
    """A raw value as it appears in the CSV, cut (not rounded) to RAW_SIG_DIGITS significant digits."""
    if v is None:
        return "n/a"
    s = repr(float(v))
    if "e" in s or "inf" in s or "nan" in s:
        return s
    if s.endswith(".0"):
        return s
    head, _, frac = s.partition(".")
    sig = len(head.lstrip("-0"))
    if sig >= RAW_SIG_DIGITS:
        keep = 1 if frac else 0
    else:
        lead0 = len(frac) - len(frac.lstrip("0")) if sig == 0 else 0
        keep = lead0 + RAW_SIG_DIGITS - sig
    if len(frac) <= keep:
        return s
    return f"{head}.{frac[:keep]}…"


def derived(v: float) -> str:
    return f"{v:.4g}"


def _when(ts: float) -> str:
    return f"{fmt_ts(ts)} (ts {int(ts)})"


def _when_ms(ts: float) -> str:
    return f"{fmt_ts(ts)} (ts {int(ts)}, {int(ts * 1000)} ms in the file)"


def render_fact(sig: Signal) -> str:
    """One markdown bullet: fact ID · file · cmdb_id · KPI — the numbers behind the anomaly."""
    head = f"- {sig.id} · {sig.source} · {sig.cmdb_id} · {sig.kpi} — "
    score = f"score {sig.score:.1f} (how many normal ranges away; derived)"
    if sig.kind == "disappear":
        step = (sig.onset_ts - sig.peak_ts) if sig.onset_ts is not None else 0
        return (head + f"last sample at {_when(sig.peak_ts)}, value {raw(sig.peak_value)}; then no samples for "
                f"{sig.breach_samples} expected {int(step)} s intervals ({sig.base_n} samples in the baseline); "
                f"{score}")
    if sig.kind in ("edge_gap", "edge_errors", "pod_errors"):
        unit = " ms" if sig.kind == "edge_gap" else ""
        what = "median" if sig.kind == "edge_gap" else "error fraction"
        onset = (f"first outside normal in the 30 s bucket starting {_when_ms(sig.onset_ts)}, bucket {what} "
                 f"{derived(sig.first_value)}{unit}; " if sig.onset_ts is not None and sig.first_value is not None else "")
        return (head + f"baseline {what} {derived(sig.base_median)}{unit} per 30 s bucket ({sig.base_n} buckets); "
                f"{onset}peak bucket {what} {derived(sig.peak_value)}{unit} at {_when_ms(sig.peak_ts)}; {score}")
    onset = (f"first outside normal at {_when(sig.onset_ts)}, value {raw(sig.first_value)}; "
             if sig.onset_ts is not None else "")
    return (head + f"baseline median {derived(sig.base_median)} ({sig.base_n} samples); {onset}"
            f"{'peak' if sig.direction == 'up' else 'lowest'} {raw(sig.peak_value)} at {_when(sig.peak_ts)}; {score}")


def _minutes(a: float, b: float) -> str:
    m = abs(a - b) / 60
    return f"{m:.0f} min" if m >= 1 else f"{abs(a - b):.0f} s"


def render_ruled_out(a: Analysis, chosen: list[str], k: int = 3) -> list[str]:
    """Sentences for the top k candidates that were not chosen, built only from facts and candidates."""
    by_comp = {c.component: c for c in a.candidates}
    picked = [by_comp[c] for c in chosen if c in by_comp]
    lead = picked[0] if picked else (a.candidates[0] if a.candidates else None)
    out = []
    for c in a.candidates:
        if len(out) >= k:
            break
        if c.component in chosen:
            continue
        fid = c.signal_ids[0] if c.signal_ids else None
        if c.demoted_by:
            out.append(f"- {c.component} — {c.demoted_by}.")
        elif lead and c.onset_ts is not None and lead.onset_ts is not None and c.onset_ts > lead.onset_ts + 30:
            out.append(f"- {c.component} — first went wrong at {fmt_ts(c.onset_ts)} ({fid}), "
                       f"{_minutes(c.onset_ts, lead.onset_ts)} after {lead.component}.")
        elif lead:
            out.append(f"- {c.component} — weaker: score {c.score:.1f} vs {lead.score:.1f} for {lead.component} ({fid}).")
        else:
            out.append(f"- {c.component} — score {c.score:.1f} ({fid}).")
    # the node layer under a chosen pod
    nodes = {c.component for c in a.candidates if c.level == "node"}
    pod_node = a.window_stats.get("pod_node", {}) if isinstance(a.window_stats, dict) else {}
    for c in picked:
        node = pod_node.get(c.component)
        if c.level == "pod" and node and node not in nodes and node not in chosen:
            out.append(f"- {node} — no node-level metric on {node} left its normal range, so the node layer "
                       f"under {c.component} isn't the cause.")
    return out
