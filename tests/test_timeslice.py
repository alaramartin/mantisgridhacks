import random
import time
from pathlib import Path

import pandas as pd
import pytest

from origin import timeslice
from origin.timeslice import read_slice, sorted_runs

DATA = Path(__file__).resolve().parent.parent / "data" / "Market-cloudbed-1"
T0 = 1647705600


def _write(path: Path, ts: list[int], scale: int = 1) -> Path:
    rows = [f"{t * scale},pod-{t % 7},kpi_{t % 3},{(t % 101) / 10}" for t in ts]
    path.write_text("timestamp,cmdb_id,kpi_name,value\n" + "\n".join(rows) + "\n")
    return path


def _truth(ts: list[int], lo: float, hi: float) -> list[int]:
    return sorted(t for t in ts if lo <= t < hi)


@pytest.fixture(params=[64, 1 << 16])
def small_gap(request, monkeypatch):
    """Exercise the binary search on small files as well as the real byte gap."""
    monkeypatch.setattr(timeslice, "MIN_GAP_BYTES", request.param)
    timeslice._cache.clear()
    timeslice._runs_cache.clear()


def _day(step=1, jitter=0, seed=0):
    rnd = random.Random(seed)
    return [T0 + s + rnd.randint(0, jitter) for s in range(0, 86400, step)]


@pytest.mark.parametrize("layout", ["sorted", "shards", "unsorted"])
def test_seek_and_chunked_agree(tmp_path, small_gap, layout):
    ts = _day(step=4, jitter=30)
    if layout == "shards":        # like trace_span.csv: sorted pieces, 00-08 pieces after 08-24 pieces
        cut = [t for t in ts if t < T0 + 8 * 3600]
        late = [t for t in ts if t >= T0 + 8 * 3600]
        ts = late[0::3] + late[1::3] + late[2::3] + cut[0::2] + cut[1::2]
    elif layout == "unsorted":    # like metric_container.csv: grouped by series
        ts = sorted(ts, key=lambda t: (t % 97, t))   # 97 series > MAX_SEEK_RUNS
    p = _write(tmp_path / f"{layout}.csv", ts)
    for lo, hi in [(T0 + 9 * 3600, T0 + 10.5 * 3600), (T0 + 7.5 * 3600, T0 + 8.5 * 3600),
                   (T0 - 100, T0 + 600), (T0 + 86000, T0 + 90000), (T0 + 200000, T0 + 200100)]:
        want = _truth(ts, lo, hi)
        # forcing seek on a file that isn't run-sorted is misuse; auto picks chunked for it
        for method in (("chunked",) if layout == "unsorted" else ("seek", "chunked")):
            df, st = read_slice(p, lo, hi, "timestamp", method=method)
            assert sorted(df.timestamp.tolist()) == want, (layout, method, lo, hi)
            assert st["rows"] == len(want)
        auto, st = read_slice(p, lo, hi, "timestamp")
        assert sorted(auto.timestamp.tolist()) == want
    runs, _ = sorted_runs(p, "timestamp")
    if layout == "sorted":
        assert len(runs) == 1
    if layout == "shards":
        assert 2 <= len(runs) <= 5
    if layout == "unsorted":
        assert st["method"] == "chunked"
    else:
        assert st["method"] == "seek"


def test_milliseconds_and_usecols(tmp_path, small_gap):
    ts = _day(step=10)
    p = _write(tmp_path / "ms.csv", ts, scale=1000)
    lo, hi = T0 + 3600, T0 + 3700
    df, st = read_slice(p, lo, hi, "timestamp", ts_scale=1000, usecols=["cmdb_id"], method="seek")
    assert sorted(df.timestamp.tolist()) == [t * 1000 for t in _truth(ts, lo, hi)]
    assert set(df.columns) == {"timestamp", "cmdb_id"}


def test_lru_returns_cached(tmp_path, small_gap):
    p = _write(tmp_path / "c.csv", _day(step=60))
    a, s1 = read_slice(p, T0, T0 + 600, "timestamp")
    b, s2 = read_slice(p, T0, T0 + 600, "timestamp")
    assert s2.get("cached") and a.equals(b)


@pytest.mark.skipif(not (DATA / "telemetry/2022_03_20/trace/trace_span.csv").exists(), reason="no data")
def test_real_trace_90_min_matches_scan():
    """90-min slice of trace_span.csv by seek vs an exact scan of the whole file (slow, ~30 s)."""
    p = DATA / "telemetry/2022_03_20/trace/trace_span.csv"
    lo, hi = 1647738000 - 3600, 1647739800     # 08:00-09:30 UTC+8: crosses the 08:00 shard edge
    timeslice._cache.clear()
    t = time.time()
    df, st = read_slice(p, lo, hi, "timestamp", 1000, usecols=["timestamp", "span_id"],
                        dtype={"span_id": str})
    print(f"\n90-min trace slice: {st} in {time.time() - t:.1f} s")
    assert st["method"] == "seek"
    full, _ = read_slice(p, lo, hi, "timestamp", 1000, usecols=["timestamp", "span_id"],
                         dtype={"span_id": str}, method="chunked")
    assert len(df) == len(full)
    assert set(df.span_id) == set(full.span_id)
    assert df.timestamp.min() >= lo * 1000 and df.timestamp.max() < hi * 1000
