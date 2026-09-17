"""origin.anomaly.score_series -- the cases PLAN Phase 2 names, plus the edges
that would silently poison every downstream candidate score."""
from __future__ import annotations

import numpy as np
import pytest

from origin.anomaly import score_series
from origin.config import IQR_FLOOR_FRAC, MIN_BASE_SAMPLES, TAU, Z_CAP

STEP = 60.0                       # one sample a minute
BASE_LO, BASE_HI = 0.0, 3600.0    # 60 baseline samples
WIN_LO, WIN_HI = 3600.0, 5400.0   # 30 window samples


def series(base_vals, win_vals):
    """Build (ts, values) with `base_vals` in the baseline and `win_vals` in the window."""
    b = np.asarray(base_vals, dtype=float)
    w = np.asarray(win_vals, dtype=float)
    bt = BASE_LO + STEP * np.arange(len(b))
    wt = WIN_LO + STEP * np.arange(len(w))
    return np.concatenate([bt, wt]), np.concatenate([b, w])


def score(base_vals, win_vals, **kw):
    ts, v = series(base_vals, win_vals)
    return score_series(ts, v, BASE_LO, BASE_HI, WIN_LO, WIN_HI, **kw)


# --- not enough data is not the same as "nothing happened" -------------------

def test_too_few_baseline_samples_returns_none():
    assert score([5.0] * (MIN_BASE_SAMPLES - 1), [5.0] * 10) is None


def test_too_few_window_samples_returns_none():
    assert score([5.0] * 30, [99.0], k=2) is None


# --- the flat-baseline floor -------------------------------------------------

def test_constant_baseline_uses_the_median_fraction_floor():
    r = score([5.0] * 60, [5.0] * 30)
    assert r["iqr_floor"] == pytest.approx(IQR_FLOOR_FRAC * 5.0)   # 0.25
    assert r["base_median"] == 5.0
    assert np.isfinite(r["score"]) and r["score"] == pytest.approx(0.0)
    assert not r["zero_baseline"]


def test_quantised_baseline_floors_on_its_own_step():
    # median 0.5 -> 5 % floor is 0.025, but the series only ever moves in 1.0s
    r = score([0.0, 1.0] * 30, [1.0] * 30)
    assert r["iqr_floor"] == pytest.approx(1.0)


# --- zero baselines ----------------------------------------------------------

def test_all_zero_baseline_with_three_nonzero_window_points():
    r = score([0.0] * 60, [0.0] * 27 + [4.0, 4.0, 4.0])
    assert r["zero_baseline"]
    assert r["score"] >= TAU
    assert r["onset_ts"] == WIN_LO + 27 * STEP
    assert r["first_value"] == 4.0
    assert r["breach_samples"] == 3


def test_all_zero_baseline_that_stays_zero_has_no_onset():
    r = score([0.0] * 60, [0.0] * 30)
    assert r["zero_baseline"] and r["onset_ts"] is None and r["score"] == 0.0


# --- sustained, not peak -----------------------------------------------------

def test_single_spike_does_not_reach_tau_at_k_two():
    r = score([5.0] * 60, [5.0] * 14 + [500.0] + [5.0] * 15, k=2)
    assert r["score"] < TAU
    assert r["onset_ts"] is None            # never two in a row
    assert r["peak_value"] == 500.0         # the spike is still reported


def test_step_up_reports_the_onset_sample_and_its_raw_value():
    win = [5.0] * 10 + [42.0] * 20
    r = score([5.0] * 60, win)
    assert r["onset_ts"] == WIN_LO + 10 * STEP
    assert r["first_value"] == 42.0
    assert r["direction"] == "up"
    assert r["score"] >= TAU


def test_drop_is_direction_down():
    r = score([100.0] * 60, [100.0] * 10 + [1.0] * 20)
    assert r["direction"] == "down"
    assert r["score"] >= TAU
    assert r["onset_ts"] == WIN_LO + 10 * STEP


# --- housekeeping ------------------------------------------------------------

def test_scores_are_capped():
    r = score([5.0] * 60, [1e12] * 30)
    assert r["score"] == pytest.approx(Z_CAP)


def test_unsorted_input_is_sorted_and_nans_dropped():
    ts, v = series([5.0] * 60, [5.0] * 10 + [42.0] * 20)
    v = v.copy()
    v[65] = np.nan                       # a hole in the quiet part of the window
    order = np.argsort(-ts)              # hand it back to front
    r = score_series(ts[order], v[order], BASE_LO, BASE_HI, WIN_LO, WIN_HI)
    assert r["onset_ts"] == WIN_LO + 10 * STEP
    assert r["base_n"] == 60


def test_baseline_outliers_do_not_set_the_scale():
    # one huge baseline sample would wreck a mean/std z; the median/IQR ignores it
    base = [4.9, 5.1] * 29 + [5.0, 10_000.0]
    r = score(base, [5.0] * 10 + [42.0] * 20)
    assert 4.9 <= r["base_median"] <= 5.1
    assert r["iqr_floor"] < 1.0          # the outlier is not the scale
    assert r["score"] >= TAU


def test_two_valued_baseline_lets_an_outlier_become_the_step_floor():
    """KNOWN CONTRACT BEHAVIOUR, raised with Person 1 at CP2.

    `step` is the smallest positive gap between DISTINCT baseline values (PLAN
    Phase 2). When the baseline hour is perfectly flat apart from a single
    outlier there are only two distinct values, so that outlier's distance
    becomes the "resolution" and floors the scale -- masking the window. Real
    telemetry almost always carries jitter (the test above), so this is a
    degenerate case rather than a live bug, but it is deliberate, not accidental:
    do not "fix" it without agreeing a contract change.
    """
    r = score([5.0] * 59 + [10_000.0], [5.0] * 10 + [42.0] * 20)
    assert r["iqr_floor"] == pytest.approx(9995.0)
    assert r["score"] < TAU
