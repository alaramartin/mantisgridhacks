"""Synthetic windows for Person 1's engine tests (no dataset needed). Component names are made up."""
from __future__ import annotations

import numpy as np
import pandas as pd

from origin.contract import Case, Window

LO = 1_700_000_040.0          # window start (epoch s, a whole minute)
HI = LO + 1800
BASE_LO = LO - 3600


def series(cmdb_id, kpi, level, component, source, fault_at=None, jump=50.0, base=1.0, noise=0.05,
           stop_at=None, seed=0):
    rng = np.random.default_rng(seed)
    ts = np.arange(BASE_LO, HI, 60.0)
    v = base + rng.normal(0, noise, len(ts))
    if fault_at is not None:
        v[ts >= fault_at] += jump
    keep = ts < stop_at if stop_at is not None else np.ones(len(ts), bool)
    return pd.DataFrame({"ts": ts[keep], "source": source, "cmdb_id": cmdb_id, "component": component,
                         "level": level, "kpi": kpi, "value": v[keep]})


def window(frames, edges=None, pod_node=None, n=1):
    m = pd.concat(frames, ignore_index=True)
    case = Case(instruction="synthetic", n_failures=n, asks={"datetime": True, "component": True, "reason": True},
                lo_ts=LO, hi_ts=HI, days=["2023_11_14"])
    edges = edges if edges is not None else pd.DataFrame(
        columns=["ts", "trace_id", "caller", "callee", "parent_ms", "child_ms", "gap_ms", "error"])
    pod_node = pod_node or {}
    pods = set(m.loc[m.level == "pod", "component"]) | set(edges["caller"]) | set(edges["callee"])
    pod_service = {p: p.rsplit("-", 1)[0] for p in pods}
    return Window(case=case, base_lo_ts=BASE_LO, base_hi_ts=LO, metrics=m, edges=edges,
                  pod_spans=pd.DataFrame(columns=["ts", "pod", "count", "errors", "p50_ms"]), logs=None,
                  pod_node=pod_node, pod_service=pod_service, nodes=set(m.loc[m.level == "node", "component"]),
                  pods=pods, services=set(pod_service.values()), stats={"files": {}, "load_s": 0.0})
