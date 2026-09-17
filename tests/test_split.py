"""The holdout split must be reproducible, disjoint and complete -- if it drifts,
every eval number we report becomes incomparable with the ones before it."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from eval.split import split, _key, PER_TASK

ROOT = Path(__file__).resolve().parents[1]
SPLITS = ROOT / "eval" / "splits"
QUERIES = ROOT / "data" / "Market-cloudbed-1" / "dev" / "query_dev.csv"


def _fake(n_per_task: dict[str, int]) -> pd.DataFrame:
    rows, rid = [], 0
    for task, n in n_per_task.items():
        for _ in range(n):
            rows.append({"row_id": rid, "task_index": task, "instruction": "x"})
            rid += 1
    return pd.DataFrame(rows)


def test_three_per_task_and_disjoint():
    q = _fake({"task_1": 12, "task_2": 10, "task_3": 8})
    hold, tune = split(q)
    assert len(hold) == 9                       # 3 per task
    assert not set(hold) & set(tune)            # disjoint
    assert sorted(hold + tune) == sorted(q.row_id.tolist())   # complete
    for task, grp in q.groupby("task_index"):
        assert len(set(grp.row_id) & set(hold)) == PER_TASK


def test_small_task_gives_all_it_has():
    """A task with fewer than PER_TASK cases must not be over-drawn or crash."""
    q = _fake({"task_1": 2, "task_2": 5})
    hold, tune = split(q)
    assert len(set(q[q.task_index == "task_1"].row_id) & set(hold)) == 2
    assert len(set(q[q.task_index == "task_2"].row_id) & set(hold)) == PER_TASK
    assert not set(hold) & set(tune)


def test_deterministic_and_order_independent():
    """Same rows in a different CSV order must give the same split -- otherwise a
    re-download or a re-sort silently moves cases across the holdout line."""
    q = _fake({"task_1": 9, "task_2": 9})
    a, _ = split(q)
    b, _ = split(q.sample(frac=1, random_state=7).reset_index(drop=True))
    assert a == b


def test_key_is_md5_of_the_string_form():
    import hashlib
    assert _key(12) == hashlib.md5(b"12").hexdigest()


@pytest.mark.skipif(not QUERIES.exists(), reason="dataset not downloaded")
def test_committed_split_still_matches_the_dataset():
    """The committed split is the one every eval run is joined on. If regenerating
    it from query_dev.csv disagrees, an eval number is being compared across two
    different holdouts."""
    q = pd.read_csv(QUERIES)
    hold, tune = split(q)
    committed = json.loads((SPLITS / "split.json").read_text())
    assert committed["holdout"] == hold
    assert committed["dev_tune"] == tune
    assert len(hold) == 21 and len(tune) == 49
    assert set(pd.read_csv(SPLITS / "holdout.csv").row_id) == set(hold)
    assert set(pd.read_csv(SPLITS / "dev_tune.csv").row_id) == set(tune)
    # the split files must keep query_dev.csv's columns, since run.py reads them
    assert list(pd.read_csv(SPLITS / "holdout.csv").columns) == list(q.columns)


def test_split_files_have_no_carriage_returns():
    """core.autocrlf=true rewrote these on checkout, putting a \r inside every
    multi-line `scoring_points` field. score.py extracts scoring points with
    `([^\n]+)`, so it captured the \r too and "node-6" never matched
    "node-6\r" -- every case scored 0.000 on a correct answer, silently.
    .gitattributes now pins *.csv to -text; this test is the tripwire."""
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    for name in ("dev_tune", "holdout"):
        raw = (root / "eval" / "splits" / f"{name}.csv").read_bytes()
        assert b"\r" not in raw, f"{name}.csv has carriage returns; scoring will silently return 0"


def test_a_correct_answer_actually_scores_against_the_real_split():
    """End-to-end tripwire: feed the split's own expected answer back in and
    require a perfect score. Catches any future mangling of the query files."""
    import sys
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(root))
    import pandas as pd
    from score import evaluate
    from run import format_prediction
    q = pd.read_csv(root / "eval" / "splits" / "dev_tune.csv")
    import re
    row = next(r for r in q.itertuples(index=False)
               if len(re.findall(r"root cause component is ([^\n]+)", str(r.scoring_points))) == 1
               and len(re.findall(r"root cause reason is ([^\n]+)", str(r.scoring_points))) == 1
               and "occurrence time is within" in str(r.scoring_points))
    sp = str(row.scoring_points)
    comp = re.findall(r"root cause component is ([^\n]+)", sp)[0]
    reason = re.findall(r"root cause reason is ([^\n]+)", sp)[0]
    when = re.findall(r"\(i\.e\., <=1min\) of ([^\n]+)", sp)[0]
    pred = format_prediction([{"datetime": when, "component": comp, "reason": reason}])
    _, failed, score = evaluate(pred, sp)
    assert score == 1.0, f"the split's own answer scores {score}, failed={failed}"
