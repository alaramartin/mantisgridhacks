import types

from origin.contract import Case, Signal, legal_reasons
from origin.candidates import engine_answers, rank

T0 = 1_700_000_040.0


def sig(i, comp, level, kpi="container_cpu_usage_seconds", score=20.0, onset=0.0, votes=None, kind="metric",
        cmdb=None):
    return Signal(id=f"F{i}", kind=kind, component=comp, level=level, source="metric_container.csv",
                  cmdb_id=cmdb or comp, kpi=kpi, score=score, onset_ts=T0 + onset, direction="up",
                  base_median=1.0, base_n=60, first_value=9.0, peak_ts=T0 + onset + 60, peak_value=10.0,
                  breach_samples=5, reason_votes=votes if votes is not None else {"container CPU load": 1.0})


def topo(pod_node=None, pod_service=None):
    return types.SimpleNamespace(pod_node=pod_node or {}, pod_service=pod_service or {})


def case(n=1):
    return Case(instruction="x", n_failures=n, asks={"datetime": True, "component": True, "reason": True},
                lo_ts=T0, hi_ts=T0 + 1800, days=[])


def as_dict(sigs):
    return {s.id: s for s in sigs}


def test_rank_orders_by_score_and_margin():
    s = as_dict([sig(1, "api-0", "pod", score=40), sig(2, "web-0", "pod", score=10)])
    cands, margin = rank(topo({"api-0": "node-1", "web-0": "node-2"}), s)
    assert [c.component for c in cands] == ["api-0", "web-0"] and cands[0].cid == "C1"
    assert 0 < margin < 1
    assert cands[0].reasons[0][0] == "container CPU load"


def test_pod_on_earlier_promoted_node_is_demoted():
    """Two pods of the node went wrong with it, so the node is the cause and its pods are victims."""
    s = as_dict([sig(1, "api-0", "pod", score=40, onset=60), sig(2, "web-0", "pod", score=38, onset=60),
                 sig(3, "node-1", "node", kpi="system.mem.used", score=30, onset=0,
                     votes={"node memory consumption": 1.0})])
    cands, _ = rank(topo({"api-0": "node-1", "web-0": "node-1"}), s)
    api = next(c for c in cands if c.component == "api-0")
    assert cands[0].component == "node-1" and cands[0].promoted_over == ["api-0", "web-0"]
    assert api.demoted_by and "2 pods on node-1" in api.demoted_by


def test_pod_reacting_long_after_its_node_is_demoted():
    s = as_dict([sig(1, "api-0", "pod", score=40, onset=600),
                 sig(2, "node-1", "node", kpi="system.disk.used", score=12, onset=0,
                     votes={"node disk space consumption": 1.0})])
    cands, _ = rank(topo({"api-0": "node-1"}), s)
    api = next(c for c in cands if c.component == "api-0")
    assert api.demoted_by and "its node" in api.demoted_by and "10 min earlier" in api.demoted_by


def test_node_with_one_anomalous_pod_is_that_pod_symptom():
    """One pod's own I/O storm shows up in its node's metrics; the pod stays the suspect."""
    s = as_dict([sig(1, "api-0", "pod", kpi="container_fs_reads_MB./dev/vda", score=40, onset=60,
                     votes={"container read I/O load": 1.0}),
                 sig(2, "node-1", "node", kpi="system.io.r_s", score=38, onset=0,
                     votes={"node disk read I/O consumption": 1.0})])
    cands, _ = rank(topo({"api-0": "node-1"}), s)
    assert cands[0].component == "api-0" and not cands[0].demoted_by
    node = next(c for c in cands if c.component == "node-1")
    assert node.demoted_by and "only one pod" in node.demoted_by and "api-0" in node.demoted_by


def test_most_pods_of_a_service_together_promote_the_service():
    pods = ["cart-0", "cart-1", "cart-2", "cart2-0"]
    s = as_dict([sig(i + 1, p, "pod", score=30 + i, onset=i * 10) for i, p in enumerate(pods)]
                + [sig(9, "web-0", "pod", score=33, onset=600)])
    cands, _ = rank(topo({p: f"node-{i}" for i, p in enumerate(pods)}, {**{p: "cart" for p in pods}, "web-0": "web"}), s)
    assert cands[0].component == "cart" and cands[0].level == "service"
    assert cands[0].promoted_over == sorted(pods)
    assert all(c.demoted_by for c in cands if c.component in pods)


def test_one_strong_pod_does_not_promote_its_service():
    pods = ["cart-0", "cart-1", "cart-2", "cart2-0"]
    s = as_dict([sig(1, "cart-0", "pod", score=50)] + [sig(i + 2, p, "pod", score=3.5) for i, p in enumerate(pods[1:])])
    cands, _ = rank(topo({}, {p: "cart" for p in pods}), s)
    assert cands[0].component == "cart-0" and not any(c.level == "service" for c in cands)


def test_node_with_several_pods_is_promoted():
    s = as_dict([sig(1, "api-0", "pod", score=45, onset=30), sig(2, "web-0", "pod", score=44, onset=60),
                 sig(3, "node-1", "node", kpi="system.cpu.user", score=12, onset=0, votes={"node CPU load": 1.0})])
    cands, _ = rank(topo({"api-0": "node-1", "web-0": "node-1"}, {"api-0": "api", "web-0": "web"}), s)
    assert cands[0].component == "node-1" and cands[0].promoted_over == ["api-0", "web-0"]


def test_reasons_are_legal_for_level():
    s = as_dict([sig(1, "node-1", "node", votes={"container CPU load": 1.0, "node CPU load": 0.5})])
    cands, _ = rank(topo(), s)
    assert all(r in legal_reasons("node") for r, _ in cands[0].reasons)


def test_engine_answers_exact_count_separated_and_chronological():
    s = as_dict([sig(1, "api-0", "pod", score=40, onset=900), sig(2, "web-0", "pod", score=39, onset=920),
                 sig(3, "db-0", "pod", score=30, onset=60, votes={"container memory load": 1.0})])
    cands, _ = rank(topo(), s)
    ans = engine_answers(case(2), cands, s)
    assert len(ans) == 2
    assert [a["component"] for a in ans] == ["db-0", "api-0"]          # web-0 is too close to api-0
    assert ans[0]["datetime"] < ans[1]["datetime"] and ans[0]["reason"] == "container memory load"
    assert list(ans[0]) == ["datetime", "component", "reason", "cid", "signal_ids"]


def test_engine_answers_pad_when_short():
    s = as_dict([sig(1, "api-0", "pod")])
    cands, _ = rank(topo(), s)
    ans = engine_answers(case(3), cands, s)
    assert len(ans) == 3 and all(a["component"] == "api-0" for a in ans)
    assert len(engine_answers(case(2), [], {})) == 2
