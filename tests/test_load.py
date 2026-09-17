from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from origin.case import parse_instruction
from origin.config import BASELINE_S, READ_PAD_S
from origin.contract import UTC8, Case
from origin.load import load_window, service_of
from origin.timeslice import read_slice

DATA = Path(__file__).resolve().parent.parent / "data" / "Market-cloudbed-1"
needs_data = pytest.mark.skipif(not (DATA / "dev" / "query_dev.csv").exists(), reason="dataset not downloaded")


def test_service_of_second_deployment():
    pods = {"cart-0", "cart-1", "cart2-0", "redis-db-0", "redis-db2-0", "s3-0", "oauth2-0"}
    m = service_of(pods)
    assert m["cart-0"] == m["cart2-0"] == "cart"
    assert m["redis-db2-0"] == "redis-db"
    assert m["s3-0"] == "s3"
    assert m["oauth2-0"] == "oauth2"            # no `oauth` service exists, so the digit stays
    assert service_of({"api2-0"}, {"api"})["api2-0"] == "api"


@pytest.fixture(scope="module")
def first_case():
    q = pd.read_csv(DATA / "dev" / "query_dev.csv")
    c = parse_instruction(q.instruction[0])
    return c, load_window(c, DATA)


@needs_data
def test_first_dev_case(first_case):
    c, w = first_case
    m = w.metrics
    assert {"pod", "node", "service"} <= set(m.level)
    assert list(m.columns) == ["ts", "source", "cmdb_id", "component", "level", "kpi", "value"]
    assert w.base_lo_ts == c.lo_ts - BASELINE_S and w.base_hi_ts == c.lo_ts
    for df in (m, w.edges, w.pod_spans):
        assert len(df)
        assert df.ts.min() >= w.base_lo_ts - READ_PAD_S and df.ts.max() <= c.hi_ts + READ_PAD_S
        assert df.ts.max() < 1e11                 # no milliseconds leaking in
    assert np.isfinite(m.value).all()
    assert all(p in w.pod_node for p in w.pods), [p for p in w.pods if p not in w.pod_node]
    assert w.nodes == set(m.loc[m.level == "node", "component"]) and all(n.startswith("node-") for n in w.nodes)
    # container cmdb_id is <node>.<pod>
    pods = m[m.level == "pod"]
    assert (pods.cmdb_id == pods.cmdb_id.str.split(".", n=1).str[0] + "." + pods.component).all()
    # service components have no -grpc/-http suffix, and every service a pod maps to is known
    assert not m.loc[m.level == "service", "component"].str.contains(r"-(?:grpc|http)$").any()
    assert set(w.pod_service.values()) <= w.services
    assert all(w.pod_service[p] in w.services for p in w.pods)
    assert set(w.edges.caller) | set(w.edges.callee) <= w.pods
    assert (w.edges.caller != w.edges.callee).all()
    assert w.stats["load_s"] < 15


@needs_data
def test_edge_numbers_come_from_raw_rows(first_case):
    """The grep test for edges: parent_ms / child_ms are the raw duration (µs) / 1000."""
    c, w = first_case
    e = w.edges.dropna(subset=["gap_ms"]).iloc[len(w.edges) // 2]
    raw, _ = read_slice(DATA / "telemetry" / "2022_03_20" / "trace" / "trace_span.csv",
                        e.ts - 1, e.ts + 1, "timestamp", 1000, dtype={"trace_id": str, "span_id": str,
                                                                      "parent_span": str})
    trace = raw[raw.trace_id == e.trace_id]
    child = trace[(trace.cmdb_id == e.callee) & (trace.timestamp == round(e.ts * 1000))]
    assert len(child) >= 1
    child = child.iloc[0]
    assert child.duration / 1000 == pytest.approx(e.child_ms)
    parent = trace[trace.span_id == child.parent_span]
    if len(parent):   # the parent can start > 1 s earlier than the child
        assert parent.iloc[0].cmdb_id == e.caller
        assert parent.iloc[0].duration / 1000 == pytest.approx(e.parent_ms)
    assert e.gap_ms == pytest.approx(e.parent_ms - e.child_ms)


@needs_data
def test_all_dev_windows_in_their_folder():
    q = pd.read_csv(DATA / "dev" / "query_dev.csv")
    for instr in q.instruction:
        c = parse_instruction(instr)
        assert all((DATA / "telemetry" / d).exists() for d in c.days), c.days


def _case(y, mo, d, h, mi) -> Case:
    lo = datetime(y, mo, d, h, mi, tzinfo=UTC8).timestamp()
    return Case(instruction="", n_failures=1, asks={}, lo_ts=lo, hi_ts=lo + 1800, days=[])


@needs_data
def test_baseline_falls_back_after_window_when_day_missing():
    c = _case(2022, 3, 20, 0, 30)                 # baseline would need 2022_03_19
    w = load_window(c, DATA)
    assert w.base_lo_ts == c.hi_ts and w.base_hi_ts == c.hi_ts + BASELINE_S
    assert any("baseline" in n for n in w.stats["notes"])
    assert w.metrics.ts.max() >= c.hi_ts + BASELINE_S - 120


@needs_data
def test_window_across_midnight_reads_both_days():
    c = _case(2022, 3, 21, 0, 15)                 # baseline starts on 2022_03_20
    w = load_window(c, DATA)
    assert w.base_lo_ts == c.lo_ts - BASELINE_S
    assert any(k.startswith("2022_03_20/") for k in w.stats["files"])
    assert any(k.startswith("2022_03_21/") for k in w.stats["files"])
    assert w.metrics.ts.min() <= c.lo_ts - BASELINE_S + 120
    assert len(w.edges) and w.edges.ts.min() <= c.lo_ts - BASELINE_S + 120


@needs_data
def test_deadline_skips_traces():
    q = pd.read_csv(DATA / "dev" / "query_dev.csv")
    w = load_window(parse_instruction(q.instruction[1]), DATA, deadline_ts=0.0)
    assert w.edges.empty and any("traces skipped" in n for n in w.stats["notes"])
    assert len(w.metrics)
