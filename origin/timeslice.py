"""Read only the rows of a big CSV that fall in a time range. No LLM.

docs/data-notes.md: `trace_span.csv` is ~10 concatenated shards, each sorted by time;
`metric_node.csv` is one sorted run; the other metric files are grouped by series.
So a file is first split into sorted runs (probing timestamps at evenly spaced byte
offsets), then each run is binary-searched for the range and only those bytes are read.
A file with too many runs is not seekable and is read in chunks instead.
"""
from __future__ import annotations

import csv
import io
import time
from collections import OrderedDict
from pathlib import Path

import pandas as pd

from origin.config import READ_PAD_S

N_PROBES = 1024           # timestamps sampled to find the sorted runs
MAX_SEEK_RUNS = 32        # more runs than this -> not seekable, read in chunks
JITTER_S = 120            # a backward step larger than this starts a new run
MIN_GAP_BYTES = 1 << 16   # stop binary search when the range is this small
CHUNK_ROWS = 1_000_000
_LRU_SIZE = 8

_cache: OrderedDict = OrderedDict()   # (path, lo, hi, scale, cols) -> (df, stats)
_runs_cache: dict = {}                # (path, size, mtime) -> list of (start, end) byte offsets


def _header(path: Path) -> tuple[bytes, list[str]]:
    with open(path, "rb") as fh:
        line = fh.readline()
    return line, next(csv.reader([line.decode("utf-8", "replace")]))


def _ts_at(fh, offset: int, i: int, scale: float) -> tuple[float, int] | None:
    """(ts in seconds, start offset of that line) for the first full line at or after `offset`."""
    fh.seek(offset)
    if offset > 0:
        fh.readline()   # drop the partial line
    for _ in range(50):
        start = fh.tell()
        line = fh.readline()
        if not line:
            return None
        try:
            return float(next(csv.reader([line.decode("utf-8", "replace")]))[i]) / scale, start
        except (StopIteration, ValueError, IndexError):
            continue
    return None


def sorted_runs(path: Path, ts_col: str, ts_scale: float = 1.0) -> tuple[list[tuple[int, int]], int]:
    """Byte ranges of the time-sorted runs, and the probe spacing in bytes. Run edges are
    only known to within one probe spacing; callers pad by that much."""
    st = path.stat()
    key = (str(path), st.st_size, st.st_mtime, ts_scale)
    header, cols = _header(path)
    i = cols.index(ts_col)
    body = len(header)
    n = max(2, min(N_PROBES, (st.st_size - body) // 256))
    spacing = max(1, (st.st_size - body) // n)
    if key in _runs_cache:
        return _runs_cache[key], spacing
    with open(path, "rb") as fh:
        probes = [p for p in (_ts_at(fh, body + k * spacing, i, ts_scale) for k in range(n)) if p]
    starts = [0] + [k for k in range(1, len(probes)) if probes[k - 1][0] - probes[k][0] > JITTER_S]
    offs = [body] + [probes[k][1] for k in starts[1:]] + [st.st_size]
    runs = list(zip(offs, offs[1:]))
    _runs_cache[key] = runs
    return runs, spacing


def _lower_bound(fh, a: int, b: int, target: float, i: int, scale: float) -> int:
    """An offset <= the first line in [a, b) with ts >= target (within MIN_GAP_BYTES)."""
    lo, hi = a, b
    while hi - lo > MIN_GAP_BYTES:
        mid = (lo + hi) // 2
        p = _ts_at(fh, mid, i, scale)
        if p is None or p[1] >= hi:
            hi = mid
        elif p[0] < target:
            lo = mid
        else:
            hi = mid
    return lo


def _byte_ranges(path: Path, lo: float, hi: float, ts_col: str, ts_scale: float) -> list[tuple[int, int]]:
    runs, spacing = sorted_runs(path, ts_col, ts_scale)
    _, cols = _header(path)
    i = cols.index(ts_col)
    size = path.stat().st_size
    out = []
    with open(path, "rb") as fh:
        for a, b in runs:
            s = _lower_bound(fh, a, b, lo - READ_PAD_S, i, ts_scale)
            e = _lower_bound(fh, a, b, hi + READ_PAD_S, i, ts_scale) + MIN_GAP_BYTES
            # run edges are only known to one probe spacing: pad into the neighbours
            s = max(0, (s if s > a else a - spacing))
            e = min(size, (e if e < b else b + spacing))
            if s < e:
                out.append((s, e))
    out.sort()
    merged: list[list[int]] = []
    for s, e in out:
        if merged and s <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    return [(s, e) for s, e in merged]


def _read_ranges(path: Path, ranges: list[tuple[int, int]], usecols, dtype) -> tuple[pd.DataFrame, int]:
    header, _ = _header(path)
    frames, nbytes = [], 0
    with open(path, "rb") as fh:
        for s, e in ranges:
            fh.seek(s)
            if s > len(header):
                fh.readline()             # partial first line
            buf = fh.read(max(0, e - fh.tell()))
            buf += fh.readline()          # finish the last line
            nbytes += len(buf)
            if buf.startswith(header):
                buf = buf[len(header):]
            if buf:
                frames.append(pd.read_csv(io.BytesIO(header + buf), usecols=usecols, dtype=dtype))
    if not frames:
        return pd.read_csv(io.BytesIO(header), usecols=usecols, dtype=dtype), nbytes
    return pd.concat(frames, ignore_index=True), nbytes


def _chunked(path: Path, lo: float, hi: float, ts_col: str, ts_scale: float, usecols, dtype) -> pd.DataFrame:
    frames = []
    for chunk in pd.read_csv(path, usecols=usecols, dtype=dtype, chunksize=CHUNK_ROWS):
        t = chunk[ts_col] / ts_scale
        frames.append(chunk[(t >= lo) & (t < hi)])
    return pd.concat(frames, ignore_index=True)


def read_slice(path: Path, lo: float, hi: float, ts_col: str, ts_scale: float = 1.0,
               usecols: list[str] | None = None, dtype: dict | None = None,
               method: str | None = None) -> tuple[pd.DataFrame, dict]:
    """Rows with lo <= ts / ts_scale < hi (lo, hi in epoch seconds), and
    {"rows", "bytes", "seconds", "method"}. `method` forces "seek" or "chunked"."""
    path = Path(path)
    key = (str(path), lo, hi, ts_scale, tuple(usecols or ()), method)
    if key in _cache:
        _cache.move_to_end(key)
        df, stats = _cache[key]
        return df, {**stats, "seconds": 0.0, "cached": True}
    t0 = time.time()
    if usecols is not None and ts_col not in usecols:
        usecols = [ts_col, *usecols]
    if method is None:
        runs, _ = sorted_runs(path, ts_col, ts_scale)
        method = "seek" if len(runs) <= MAX_SEEK_RUNS else "chunked"
    if method == "seek":
        df, nbytes = _read_ranges(path, _byte_ranges(path, lo, hi, ts_col, ts_scale), usecols, dtype)
        t = df[ts_col] / ts_scale
        df = df[(t >= lo) & (t < hi)].reset_index(drop=True)
    else:
        df = _chunked(path, lo, hi, ts_col, ts_scale, usecols, dtype).reset_index(drop=True)
        nbytes = path.stat().st_size
    stats = {"rows": len(df), "bytes": nbytes, "seconds": round(time.time() - t0, 3), "method": method}
    _cache[key] = (df, stats)
    while len(_cache) > _LRU_SIZE:
        _cache.popitem(last=False)
    return df, stats
