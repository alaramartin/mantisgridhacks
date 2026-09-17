"""How ORIGIN decides a single time series went wrong (PLAN §3, Person 2).

One function, `score_series`, used by every signal the engine builds. The shape of
the decision matters more than the arithmetic:

  * **Robust, not Gaussian.** Baseline centre is the median and the scale is the
    IQR, so the failure itself -- which is often the largest thing in the day --
    cannot inflate the scale it is measured against.
  * **A floor under the scale.** Container metrics are frequently flat to the
    sampling resolution, and a zero IQR would turn every quantisation step into an
    infinite z. The floor is the largest of the IQR, a fraction of |median|, and
    the series' own smallest positive step.
  * **Sustained, not peak.** A one-sample blip is noise; a fault holds. The score
    is the best rolling minimum over `k` consecutive samples, so a spike of length
    one can never reach tau at k >= 2.
  * **Zero baselines are a different question.** A counter that was flat zero all
    hour has no scale at all, so "how many sigma" is meaningless -- what matters is
    that it moved at all, and how much of the window it stayed moved.

Returns None when there is not enough data to say anything, which is a real answer
and must not be confused with "nothing happened".
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from origin.config import IQR_FLOOR_FRAC, K, MIN_BASE_SAMPLES, TAU, Z_CAP


def score_series(ts: np.ndarray, values: np.ndarray, base_lo: float, base_hi: float,
                 win_lo: float, win_hi: float, tau: float = TAU, k: int = K) -> dict | None:
    """Score one (component, kpi) series inside [win_lo, win_hi) against [base_lo, base_hi).

    None if the baseline has fewer than MIN_BASE_SAMPLES points or the window has
    fewer than k. Otherwise the dict documented in PLAN §3.
    """
    ts = np.asarray(ts, dtype=float)
    values = np.asarray(values, dtype=float)
    if ts.shape != values.shape:
        raise ValueError(f"ts {ts.shape} and values {values.shape} differ")

    order = np.argsort(ts, kind="stable")
    ts, values = ts[order], values[order]
    ok = np.isfinite(ts) & np.isfinite(values)
    ts, values = ts[ok], values[ok]

    base = values[(ts >= base_lo) & (ts < base_hi)]
    win_mask = (ts >= win_lo) & (ts < win_hi)
    if len(base) < MIN_BASE_SAMPLES or int(win_mask.sum()) < k:
        return None

    med = float(np.median(base))
    q75, q25 = np.percentile(base, [75, 25])
    iqr = float(q75 - q25)

    # the series' own resolution: the smallest gap between two distinct baseline
    # values. A metric that only ever moves in steps of 1 cannot be surprised by 0.5.
    uniq = np.unique(base)
    step = float(np.diff(uniq).min()) if len(uniq) >= 2 else 0.0

    zero_baseline = (med == 0.0 and iqr == 0.0)
    wt, wx = ts[win_mask], values[win_mask]

    if zero_baseline:
        # Nothing to normalise against: any movement is the whole story.
        breach = wx != 0.0
        floor = step if step > 0 else 1.0
        z = np.where(breach, Z_CAP, 0.0)
    else:
        floor = max(iqr, IQR_FLOOR_FRAC * abs(med), step, 1e-9)
        z = np.minimum(np.abs(wx - med) / floor, Z_CAP)
        breach = z >= tau

    # sustained[p] = the weakest z across samples p..p+k-1, i.e. what this series
    # held for k in a row starting at p.
    sustained = pd.Series(z).rolling(k).min().shift(-(k - 1)).to_numpy()

    first = None
    for p in range(len(wx) - k + 1):
        if breach[p:p + k].all():
            first = p
            break

    score = float(np.nanmax(sustained)) if np.isfinite(sustained).any() else 0.0
    if zero_baseline and first is not None:
        # Rank by how much of the window stayed off zero, not by a fake z.
        score = float(min(Z_CAP, tau + 10.0 * breach.mean()))

    peak = int(np.argmax(z))
    return {
        "score": score,
        "onset_ts": float(wt[first]) if first is not None else None,
        "direction": "up" if wx[peak] >= med else "down",
        "base_median": med,
        "iqr_floor": float(floor),
        "base_n": int(len(base)),
        "first_value": float(wx[first]) if first is not None else None,
        "peak_ts": float(wt[peak]),
        "peak_value": float(wx[peak]),
        "breach_samples": int(breach.sum()),
        "zero_baseline": bool(zero_baseline),
    }
