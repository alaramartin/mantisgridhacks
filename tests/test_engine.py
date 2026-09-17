import re
from datetime import datetime
from pathlib import Path

import pandas as pd
import pytest

from origin.contract import TIME_FMT, UTC8, legal_reasons
from origin.engine import analyze, describe
from origin.facts import render_fact

DATA = Path(__file__).resolve().parent.parent / "data" / "Market-cloudbed-1"
needs_data = pytest.mark.skipif(not (DATA / "dev" / "query_dev.csv").exists(), reason="dataset not downloaded")


def test_unparseable_instruction_still_answers(tmp_path):
    a = analyze("no window in here", tmp_path)
    assert len(a.engine_answers) == 1 and a.engine_answers[0]["component"]
    assert any("parse failed" in n for n in a.notes)


@pytest.fixture(scope="module")
def dev_case():
    q = pd.read_csv(DATA / "dev" / "query_dev.csv")
    r = q[q.row_id == 7].iloc[0]                      # a dev_tune row with two failures
    return analyze(r.instruction, DATA)


@needs_data
def test_analysis_shape(dev_case):
    a = dev_case
    assert len(a.engine_answers) == a.case.n_failures == 2
    by = {c.component: c for c in a.candidates}
    times = [a_["datetime"] for a_ in a.engine_answers]
    assert times == sorted(times)
    for ans in a.engine_answers:
        assert list(ans) == ["datetime", "component", "reason", "cid", "signal_ids"]
        assert ans["reason"] in legal_reasons(by[ans["component"]].level)
        ts = datetime.strptime(ans["datetime"], TIME_FMT).replace(tzinfo=UTC8).timestamp()
        assert a.case.lo_ts <= ts < a.case.hi_ts
        assert all(i in a.signals for i in ans["signal_ids"])
    assert [c.cid for c in a.candidates] == [f"C{i}" for i in range(1, len(a.candidates) + 1)]
    assert set(a.timings) == {"load_s", "signals_s", "candidates_s", "total_s"}
    assert "ENGINE ANSWERS" in describe(a)


@needs_data
def test_grep_metric_facts_against_raw_csv(dev_case):
    """The CP3 grep test, automated: every metric fact's onset and peak values are in the raw file row."""
    a = dev_case
    checked = 0
    for sid in [i for ans in a.engine_answers for i in ans["signal_ids"]]:
        s = a.signals[sid]
        if s.kind != "metric" or s.source == "metric_service.csv":
            continue
        line = render_fact(s)
        day = datetime.fromtimestamp(s.peak_ts, tz=UTC8).strftime("%Y_%m_%d")
        raw = pd.read_csv(DATA / "telemetry" / day / "metric" / s.source, dtype={"value": str, "cmdb_id": "category",
                          "kpi_name": "category"})
        for ts, printed in ((s.peak_ts, re.search(r"(?:peak|lowest) ([-\d.e+]+)", line).group(1)),
                            (s.onset_ts, re.search(r"value ([-\d.e+]+)", line).group(1))):
            rows = raw[(raw.timestamp == int(ts)) & (raw.cmdb_id == s.cmdb_id) & (raw.kpi_name == s.kpi)]
            assert len(rows) == 1, (sid, ts)
            assert rows.value.iloc[0].startswith(printed.rstrip("…")) or float(rows.value.iloc[0]) == float(printed), \
                (line, rows.value.iloc[0])
            checked += 1
    assert checked >= 2
