"""PLACEHOLDER: Person 1's stand-in for Person 2's origin.anomaly.score_series (PLAN §3).
Same signature and keys; robust z vs baseline median / IQR floor, sustained over k samples.
Delete after Checkpoint 2 and import origin.anomaly.score_series instead."""
from __future__ import annotations

import numpy as np

from origin.config import IQR_FLOOR_FRAC, K, MIN_BASE_SAMPLES, TAU, Z_CAP


def score_series(ts: np.ndarray, values: np.ndarray, base_lo: float, base_hi: float,
                 win_lo: float, win_hi: float, tau: float = TAU, k: int = K) -> dict | None:
    ts, values = np.asarray(ts, float), np.asarray(values, float)
    order = np.argsort(ts, kind="stable")
    ts, values = ts[order], values[order]
    b = values[(ts >= base_lo) & (ts < base_hi)]
    wm = (ts >= win_lo) & (ts < win_hi)
    w, wt = values[wm], ts[wm]
    if len(b) < MIN_BASE_SAMPLES or len(w) < k:
        return None
    med = float(np.median(b))
    iqr = float(np.subtract(*np.percentile(b, [75, 25])))
    steps = np.abs(np.diff(np.unique(b)))
    step = float(steps[steps > 0].min()) if (steps > 0).any() else 0.0
    zero = med == 0 and iqr == 0
    floor = max(iqr, IQR_FLOOR_FRAC * abs(med), step, 1e-9)
    z = np.minimum(np.abs(w - med) / floor, Z_CAP)
    if zero:
        breach = w != 0
    else:
        breach = z >= tau
    # sustained: k consecutive breaches; score = highest min-z over any k-run
    best, onset, n_breach = 0.0, None, int(breach.sum())
    for i in range(len(w) - k + 1):
        if breach[i:i + k].all():
            s = float(z[i:i + k].min())
            if onset is None:
                onset = float(wt[i])
            best = max(best, s)
    if zero and onset is not None:
        best = min(Z_CAP, tau + 10 * n_breach / len(w))
    pk = int(np.argmax(np.abs(w - med)))
    oi = int(np.searchsorted(wt, onset)) if onset is not None else None
    return {"score": best, "onset_ts": onset, "direction": "up" if w[pk] >= med else "down",
            "base_median": med, "iqr_floor": floor, "base_n": int(len(b)),
            "first_value": float(w[oi]) if oi is not None else None,
            "peak_ts": float(wt[pk]), "peak_value": float(w[pk]), "breach_samples": n_breach,
            "zero_baseline": zero}
