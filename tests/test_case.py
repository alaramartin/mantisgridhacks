from datetime import datetime
from pathlib import Path

import pandas as pd
import pytest

from origin.case import parse_instruction
from origin.contract import UTC8

DATA = Path(__file__).resolve().parent.parent / "data" / "Market-cloudbed-1"
QUERY_DEV = DATA / "dev" / "query_dev.csv"

# docs/data.md task table: which fields each task type asks for (datetime, component, reason)
TASKS = {
    "task_1": (True, False, False), "task_2": (False, False, True),
    "task_3": (False, True, False), "task_4": (True, False, True),
    "task_5": (True, True, False), "task_6": (False, True, True),
    "task_7": (True, True, True),
}

DOC_EXAMPLE = ("The cloud service system, cloudbed-1, experienced one failure within the "
               "time range of March 20, 2022, from 09:00 to 09:30. The specific component "
               "responsible for this failure and the underlying reason are currently "
               "unknown. You are tasked with identifying the root cause component and the "
               "root cause reason.")


def test_doc_example():
    c = parse_instruction(DOC_EXAMPLE)
    assert c.lo_ts == datetime(2022, 3, 20, 9, 0, tzinfo=UTC8).timestamp() == 1647738000
    assert c.hi_ts - c.lo_ts == 1800
    assert c.n_failures == 1
    assert c.days == ["2022_03_20"]
    assert c.notes == []


def test_counts():
    for word, n in (("two failures", 2), ("three failures", 3), ("2 failures", 2)):
        assert parse_instruction(DOC_EXAMPLE.replace("one failure", word)).n_failures == n
    c = parse_instruction(DOC_EXAMPLE.replace("one failure", "a problem"))
    assert c.n_failures == 1 and c.notes


def test_window_crossing_midnight():
    c = parse_instruction(DOC_EXAMPLE.replace("from 09:00 to 09:30", "from 23:45 to 00:15"))
    assert c.lo_ts == datetime(2022, 3, 20, 23, 45, tzinfo=UTC8).timestamp()
    assert c.hi_ts == datetime(2022, 3, 21, 0, 15, tzinfo=UTC8).timestamp()
    assert c.days == ["2022_03_20", "2022_03_21"]


def test_window_with_second_date():
    c = parse_instruction(DOC_EXAMPLE.replace("from 09:00 to 09:30",
                                              "from 23:30 to March 21, 2022, at 00:00"))
    assert c.hi_ts == datetime(2022, 3, 21, 0, 0, tzinfo=UTC8).timestamp()
    assert c.hi_ts - c.lo_ts == 1800


def test_baseline_reaches_previous_day():
    c = parse_instruction(DOC_EXAMPLE.replace("from 09:00 to 09:30", "from 00:30 to 01:00"))
    assert c.days == ["2022_03_19", "2022_03_20"]


@pytest.mark.skipif(not QUERY_DEV.exists(), reason="dataset not downloaded")
def test_all_dev_instructions():
    q = pd.read_csv(QUERY_DEV)
    assert len(q) == 70
    seen: dict[str, set] = {}
    for task, instr in zip(q.task_index, q.instruction):
        c = parse_instruction(instr)
        assert c.hi_ts - c.lo_ts == 1800, instr
        assert not c.notes, (instr, c.notes)
        a = (c.asks["datetime"], c.asks["component"], c.asks["reason"])
        seen.setdefault(task, set()).add(a)
    for task, s in seen.items():
        assert s == {TASKS[task]}, (task, s)


@pytest.mark.skipif(not QUERY_DEV.exists(), reason="dataset not downloaded")
def test_counts_match_answers():
    q = pd.read_csv(QUERY_DEV)
    for instr, sp in zip(q.instruction, q.scoring_points):
        n = max(sp.count("-th predicted root cause component"),
                sp.count("-th predicted root cause reason"),
                sp.count("-th root cause occurrence time"), 1)
        assert parse_instruction(instr).n_failures == n, instr
