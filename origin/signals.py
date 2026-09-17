"""Stage 2: turn a Window into anomalous Signals (metric series, trace edges, disappearances). No LLM.

Every Signal keeps the raw source file, cmdb_id, KPI and the raw values/timestamps behind its
numbers, so origin/facts.py can render a line a judge can grep.
"""
from __future__ import annotations

import re
import time
from functools import lru_cache

import numpy as np
import pandas as pd

from origin.config import (BASE_RANGE_GUARD, DISAPPEAR_MIN_BASE, DOWN_IS_LOAD, DISAPPEAR_VOTES, EDGE_BUCKET_S,
                           EDGE_ERROR_VOTES, EDGE_GAP_VOTES, EDGE_MIN_BASE_CALLS, K, MAGNITUDE_RULES, PERIODIC_LAGS_S,
                           PERIODIC_TOL_S, REASON_RULES,
                           SPIKE_MAX_SAMPLES, TAU, Z_CAP)
from origin.contract import Signal, Window, legal_reasons

try:
    from origin.anomaly import score_series
except ImportError:   # PLACEHOLDER: Person 2's origin.anomaly isn't merged yet; delete this fallback after it is
    from tests._p1_score_stub import score_series

EDGE_MIN_LEFT_S = 10          # stop adding trace signals when the deadline is this close


@lru_cache(maxsize=4096)
def reason_votes(level: str, kpi: str) -> tuple[tuple[str, float], ...]:
    """The first REASON_RULES entry for this level (services fall back to pod rules) matching the kpi."""
    levels = (level, "pod") if level == "service" else (level,)
    for lv in levels:
        for rl, pattern, reason, weight in REASON_RULES:
            if rl == lv and re.search(pattern, kpi, re.I):
                return ((reason, weight),) if reason and reason in legal_reasons(level) else ()
    return ()


def _guarded_onset(ts: np.ndarray, vals: np.ndarray, s: dict, base_lo: float, base_hi: float,
                   win_lo: float, win_hi: float) -> tuple[float | None, int]:
    """First sample of k consecutive samples that breach tau AND lie outside the baseline's own
    [min, max] in the anomaly's direction. Returns (onset_ts, samples outside), (None, 0) if none.
    Periodic spikes that already happen in the baseline don't count as a fault."""
    b = vals[(ts >= base_lo) & (ts < base_hi)]
    m = (ts >= win_lo) & (ts < win_hi)
    wt, wv = ts[m], vals[m]
    if not len(b) or not len(wv):
        return None, 0
    z = np.abs(wv - s["base_median"]) / max(s["iqr_floor"], 1e-12)
    out = (wv > b.max()) if s["direction"] == "up" else (wv < b.min())
    breach = out & ((z >= TAU) | bool(s.get("zero_baseline")))
    if len(breach) < K:
        return None, 0
    run = np.convolve(breach.astype(int), np.ones(K, int), mode="valid") == K
    for i in np.flatnonzero(run):
        if not _periodic(ts, vals, float(wt[i]), float(wv[i]), s["base_median"]):
            return float(wt[i]), int(breach[i:].sum())
    return None, 0


def _periodic(ts: np.ndarray, vals: np.ndarray, onset: float, value: float, median: float) -> bool:
    """True if the series already reached at least half of this departure at the same clock offset
    PERIODIC_LAGS_S earlier (hourly / half-hourly jobs), so the breach is routine, not a fault."""
    half = median + 0.5 * (value - median)
    for lag in PERIODIC_LAGS_S:
        m = np.abs(ts - (onset - lag)) <= PERIODIC_TOL_S
        if m.any():
            v = vals[m]
            if (value >= median and v.max() >= half) or (value < median and v.min() <= half):
                return True
    return False


def _signal(kind, component, level, source, cmdb_id, kpi, s, onset, votes, breach=None) -> Signal:
    return Signal(id="", kind=kind, component=component, level=level, source=source, cmdb_id=cmdb_id,
                  kpi=kpi, score=float(min(s["score"], Z_CAP)), onset_ts=onset, direction=s["direction"],
                  base_median=float(s["base_median"]), base_n=int(s["base_n"]),
                  first_value=s.get("first_value"), peak_ts=float(s["peak_ts"]),
                  peak_value=float(s["peak_value"]),
                  breach_samples=int(breach if breach is not None else s["breach_samples"]),
                  reason_votes=dict(votes))


def _score(ts, vals, w: Window, kind="metric") -> tuple[dict, float, int] | None:
    c = w.case
    s = score_series(ts, vals, w.base_lo_ts, w.base_hi_ts, c.lo_ts, c.hi_ts)
    if not s or s["score"] < TAU or s["onset_ts"] is None:
        return None
    onset, breach = s["onset_ts"], s["breach_samples"]
    if BASE_RANGE_GUARD:
        onset, breach = _guarded_onset(ts, vals, s, w.base_lo_ts, w.base_hi_ts, c.lo_ts, c.hi_ts)
        if onset is None:
            return None
        oi = int(np.searchsorted(ts, onset))
        s = {**s, "first_value": float(vals[oi])}
    return s, onset, breach


def metric_signals(w: Window) -> list[Signal]:
    m = w.metrics
    if m.empty:
        return []
    m = m.sort_values("ts", kind="stable")
    ts_all, val_all = m["ts"].to_numpy(float), m["value"].to_numpy(float)
    out = []
    for (source, cmdb_id, comp, level, kpi), idx in m.groupby(
            ["source", "cmdb_id", "component", "level", "kpi"], sort=False, observed=True).indices.items():
        r = _score(ts_all[idx], val_all[idx], w)
        if r is None:
            continue
        s, onset, breach = r
        votes = reason_votes(level, kpi)
        if s["direction"] != ("down" if re.search(DOWN_IS_LOAD, kpi, re.I) else "up"):
            votes = ()          # e.g. load falling: evidence of change, not of this load reason
        for lv, pattern, floor, reason, rank_ in MAGNITUDE_RULES:
            if votes and lv == level and abs(s["peak_value"]) >= floor and re.search(pattern, kpi, re.I):
                votes = ((reason, rank_ * Z_CAP / max(s["score"], 1e-9)),)
                break
        if level == "node" and votes and votes[0][0] == "node CPU load" and breach <= SPIKE_MAX_SAMPLES:
            votes = (("node CPU spike", votes[0][1]),)
        out.append(_signal("metric", comp, level, f"{source}.csv", cmdb_id, kpi, s, onset, votes, breach))
    return out


def disappear_signals(w: Window) -> list[Signal]:
    """A pod whose metric series stop (or pause for >= 2 expected intervals) inside the window.
    One signal per pod: the series with the longest gap, with the count of series that went missing."""
    c = w.case
    m = w.metrics[w.metrics.level == "pod"]
    if m.empty:
        return []
    m = m.sort_values("ts", kind="stable")
    data_end = min(c.hi_ts, float(m["ts"].max()) + 1)
    best: dict[str, tuple] = {}
    missing: dict[str, int] = {}
    ts_all, val_all = m["ts"].to_numpy(float), m["value"].to_numpy(float)
    for (cmdb_id, comp, kpi), idx in m.groupby(["cmdb_id", "component", "kpi"], sort=False,
                                               observed=True).indices.items():
        ts, vals = ts_all[idx], val_all[idx]
        base = ts[(ts >= w.base_lo_ts) & (ts < w.base_hi_ts)]
        if len(base) < DISAPPEAR_MIN_BASE:
            continue
        step = float(np.median(np.diff(base)))
        if step <= 0:
            continue
        seen = ts[(ts >= w.base_lo_ts) & (ts < data_end)]
        edges = np.concatenate([seen, [data_end + step]])   # "stops before the end" is a gap too
        gaps = np.diff(edges)
        i = int(np.argmax(gaps))
        n_missing = int(round(gaps[i] / step)) - 1
        if n_missing < 2 or edges[i] + step >= data_end or edges[i] + step < c.lo_ts:
            continue
        missing[comp] = missing.get(comp, 0) + 1
        if comp not in best or n_missing > best[comp][0]:
            best[comp] = (n_missing, cmdb_id, kpi, float(edges[i]), float(vals[np.searchsorted(ts, edges[i])]),
                          step, len(base), float(np.median(vals[(ts >= w.base_lo_ts) & (ts < w.base_hi_ts)])))
    out = []
    for comp, (n_missing, cmdb_id, kpi, last_ts, last_val, step, base_n, base_med) in best.items():
        s = {"score": min(Z_CAP, TAU + n_missing), "direction": "down", "base_median": base_med,
             "base_n": base_n, "first_value": None, "peak_ts": last_ts, "peak_value": last_val,
             "breach_samples": n_missing}
        sig = _signal("disappear", comp, "pod", "metric_container.csv", cmdb_id,
                      f"series missing ({missing[comp]} series; longest: {kpi})", s, last_ts + step,
                      DISAPPEAR_VOTES.items())
        out.append(sig)
    return out


def edge_signals(w: Window, deadline_ts: float | None, notes: list[str]) -> list[Signal]:
    e = w.edges
    if e is None or e.empty:
        return []
    e = e.assign(bucket=np.floor(e["ts"].to_numpy(float) / EDGE_BUCKET_S) * EDGE_BUCKET_S)
    base = e[(e.ts >= w.base_lo_ts) & (e.ts < w.base_hi_ts)]
    calls = base.groupby(["caller", "callee"], observed=True).size()
    keep = set(calls[calls >= EDGE_MIN_BASE_CALLS].index)
    agg = (e.groupby(["caller", "callee", "bucket"], observed=True)
           .agg(gap=("gap_ms", "median"), err=("error", "mean")).reset_index())
    out = []
    for (caller, callee), g in agg.groupby(["caller", "callee"], sort=False, observed=True):
        if (caller, callee) not in keep:
            continue
        if deadline_ts is not None and time.time() > deadline_ts - EDGE_MIN_LEFT_S:
            notes.append("trace edge signals cut short: too close to the per-case deadline")
            break
        ts = g["bucket"].to_numpy(float)
        for col, kind, kpi, votes in (("gap", "edge_gap", "call gap ms", EDGE_GAP_VOTES),
                                      ("err", "edge_errors", "call error rate", EDGE_ERROR_VOTES)):
            v = g[col].to_numpy(float)
            ok = np.isfinite(v)
            if ok.sum() < K or (kind == "edge_errors" and not v[ok].any()):
                continue
            r = _score(ts[ok], v[ok], w, kind)
            if r is None or (kind == "edge_gap" and r[0]["direction"] != "up"):
                continue
            s, onset, breach = r
            out.append(_signal(kind, callee, "pod", "trace_span.csv", f"{caller} → {callee}", kpi,
                               s, onset, votes.items(), breach))
    return out


def pod_span_signals(w: Window) -> list[Signal]:
    """Per-pod span errors per 30 s bucket (trace status codes outside the OK set)."""
    p = w.pod_spans
    if p is None or p.empty or not p["errors"].any():
        return []
    out = []
    for pod, g in p.groupby("pod", observed=True):
        if not g["errors"].any():
            continue
        g = g.sort_values("ts")
        r = _score(g["ts"].to_numpy(float), (g["errors"] / g["count"]).to_numpy(float), w)
        if r is None or r[0]["direction"] != "up":
            continue
        s, onset, breach = r
        out.append(_signal("pod_errors", pod, "pod", "trace_span.csv", pod, "span error rate", s, onset,
                           EDGE_ERROR_VOTES.items(), breach))
    return out


def build_signals(w: Window, deadline_ts: float | None = None, notes: list[str] | None = None) -> dict[str, Signal]:
    """All anomalous signals for the window, IDs F1..Fn by descending score (ties: onset, cmdb_id)."""
    notes = notes if notes is not None else []
    sigs = metric_signals(w) + disappear_signals(w)
    sigs += edge_signals(w, deadline_ts, notes) + pod_span_signals(w)
    sigs.sort(key=lambda s: (-s.score, s.onset_ts if s.onset_ts is not None else float("inf"), s.cmdb_id, s.kpi))
    out = {}
    for i, s in enumerate(sigs, 1):
        s.id = f"F{i}"
        out[s.id] = s
    return out
