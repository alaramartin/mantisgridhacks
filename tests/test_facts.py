from origin.contract import Signal
from origin.facts import raw, render_fact


def _sig(**kw):
    base = dict(id="F3", kind="metric", component="api-1", level="pod", source="metric_container.csv",
                cmdb_id="node-9.api-1", kpi="container_fs_reads./dev/vda", score=18.25, onset_ts=1647738540.0,
                direction="up", base_median=2.1, base_n=60, first_value=47.02, peak_ts=1647738720.0,
                peak_value=51.3, breach_samples=4, reason_votes={})
    base.update(kw)
    return Signal(**base)


def test_raw_is_a_prefix_of_the_file_text():
    for v in (9.502213654499997, 0.014365767000015201, 4233.53515625, 224790528.0, 0.0, 47.02, -3.25, 1e-07):
        r = raw(v)
        assert repr(v).startswith(r.rstrip("…")), (v, r)
    assert raw(9.502213654499997) == "9.50221…"
    assert raw(224790528.0) == "224790528.0"


def test_metric_fact_has_file_id_kpi_epoch_and_raw_values():
    line = render_fact(_sig())
    for part in ("F3", "metric_container.csv", "node-9.api-1", "container_fs_reads./dev/vda",
                 "2022-03-20 09:09:00", "ts 1647738540", "value 47.02", "peak 51.3", "ts 1647738720", "score 18.2"):
        assert part in line, part


def test_edge_fact_prints_ms_epoch():
    line = render_fact(_sig(kind="edge_gap", source="trace_span.csv", cmdb_id="web-0 → api-1", kpi="call gap ms",
                            base_median=3.1, first_value=41.0, peak_value=44.0))
    assert "1647738540000 ms" in line and "median 41 ms" in line and "web-0 → api-1" in line


def test_disappear_fact():
    line = render_fact(_sig(kind="disappear", kpi="series missing (3 series; longest: container_threads)",
                            peak_ts=1647738480.0, onset_ts=1647738540.0, peak_value=42.0, breach_samples=6))
    assert "last sample at 2022-03-20 09:08:00 (ts 1647738480), value 42.0" in line
    assert "6 expected 60 s intervals" in line
