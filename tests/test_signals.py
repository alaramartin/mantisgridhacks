import numpy as np
import pandas as pd

from origin.contract import legal_reasons
from origin.signals import build_signals, reason_votes
from tests._p1_synth import BASE_LO, HI, LO, series, window


def test_reason_votes_are_legal_for_level():
    assert reason_votes("pod", "container_fs_reads./dev/vda") == (("container read I/O load", 1.0),)
    assert reason_votes("pod", "container_fs_writes_MB./dev/vda")[0][0] == "container write I/O load"
    assert reason_votes("pod", "container_spec_memory_limit_MB") == ()
    assert reason_votes("node", "system.io.rkb_s")[0][0] == "node disk read I/O consumption"
    assert reason_votes("node", "system.disk.pct_usage")[0][0] == "node disk space consumption"
    assert reason_votes("service", "container_cpu_usage_seconds")[0][0] == "container CPU load"
    for lv, kpi in [("node", "system.cpu.user"), ("pod", "container_memory_rss"), ("service", "mrt")]:
        for r, _ in reason_votes(lv, kpi):
            assert r in legal_reasons(lv)


def test_metric_step_gives_signal_with_onset():
    fault = LO + 600
    w = window([series("n-1.api-0", "container_cpu_usage_seconds", "pod", "api-0", "metric_container", fault_at=fault,
                       jump=5.0),
                series("n-1.web-0", "container_cpu_usage_seconds", "pod", "web-0", "metric_container", seed=1)])
    sigs = build_signals(w)
    assert [s.component for s in sigs.values()] == ["api-0"]
    s = sigs["F1"]
    assert s.onset_ts == fault and s.direction == "up" and s.source == "metric_container.csv"
    assert s.reason_votes == {"container CPU load": 1.0}
    assert s.first_value > 5 and s.base_n == 60


def test_magnitude_rule_and_direction():
    up = series("n-1.api-0", "container_fs_reads_MB./dev/vda", "pod", "api-0", "metric_container",
                fault_at=LO + 600, jump=5000.0)
    down = series("n-1.web-0", "container_cpu_usage_seconds", "pod", "web-0", "metric_container",
                  fault_at=LO + 600, jump=-0.9, seed=2)
    sigs = {s.component: s for s in build_signals(window([up, down])).values()}
    r = sigs["api-0"]
    assert list(r.reason_votes) == ["container read I/O load"] and r.score * r.reason_votes["container read I/O load"] >= 50
    assert sigs["web-0"].direction == "down" and sigs["web-0"].reason_votes == {}   # a CPU drop is not CPU load


def test_baseline_range_guard_drops_spikes_seen_in_baseline():
    df = series("n-1.api-0", "container_network_receive_MB.eth0", "pod", "api-0", "metric_container")
    spikes = np.isin(((df.ts - BASE_LO) // 60).astype(int) % 15, [0, 1])   # a 2-sample burst every 15 min
    df.loc[spikes, "value"] += 5.0
    assert not build_signals(window([df]))


def test_node_cpu_short_breach_is_spike():
    df = series("node-9", "system.cpu.user", "node", "node-9", "metric_node")
    t = df.ts.to_numpy()
    df.loc[(t >= LO + 300) & (t < LO + 420), "value"] += 40
    (s,) = build_signals(window([df])).values()
    assert s.reason_votes == {"node CPU spike": 1.0}


def test_disappearance_signal():
    frames = [series("n-1.api-0", k, "pod", "api-0", "metric_container", stop_at=LO + 900, seed=i)
              for i, k in enumerate(["container_threads", "container_memory_rss"])]
    frames.append(series("n-1.web-0", "container_threads", "pod", "web-0", "metric_container", seed=7))
    sigs = build_signals(window(frames))
    d = [s for s in sigs.values() if s.kind == "disappear"]
    assert len(d) == 1 and d[0].component == "api-0"
    assert d[0].onset_ts == LO + 900 and d[0].reason_votes == {"container process termination": 1.5}
    assert "2 series" in d[0].kpi


def test_edge_gap_signal_on_callee():
    rng = np.random.default_rng(3)
    ts = np.sort(rng.uniform(BASE_LO, HI, 20000))
    gap = 2 + rng.normal(0, 0.2, len(ts))
    gap[ts >= LO + 900] += 40
    edges = pd.DataFrame({"ts": ts, "trace_id": "t", "caller": "web-0", "callee": "api-0",
                          "parent_ms": gap + 5, "child_ms": 5.0, "gap_ms": gap, "error": False})
    w = window([series("n-1.web-0", "container_cpu_usage_seconds", "pod", "web-0", "metric_container")], edges=edges)
    sigs = [s for s in build_signals(w).values() if s.kind == "edge_gap"]
    assert len(sigs) == 1
    s = sigs[0]
    assert s.component == "api-0" and s.cmdb_id == "web-0 → api-0" and s.onset_ts == LO + 900
    assert s.reason_votes["container network latency"] == 1.0
