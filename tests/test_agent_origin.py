"""agents.origin's contract with run.py and score.py.

score.py scores zero for the whole case unless the prediction parses into
exactly `n_failures` objects, so the guarantees worth pinning here are structural,
not about accuracy: never empty, always `n` objects, only the asked-for fields,
and a trace line per case.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import agents.origin as ag              # noqa: E402
from origin.fixture import INSTRUCTION  # noqa: E402
from run import Solution                # noqa: E402
from score import evaluate              # noqa: E402

# score.py's own parser: what the evaluator will actually see.
PREDICT_PATTERN = (
    r'{\s*'
    r'(?:"root cause occurrence datetime":\s*"(.*?)")?,?\s*'
    r'(?:"root cause component":\s*"(.*?)")?,?\s*'
    r'(?:"root cause reason":\s*"(.*?)")?\s*}'
)


def parsed(prediction: str) -> list[tuple[str, str, str]]:
    return re.findall(PREDICT_PATTERN, prediction)


@pytest.fixture(autouse=True)
def fixture_mode(monkeypatch, tmp_path):
    monkeypatch.setenv("ORIGIN_FIXTURE", "1")
    monkeypatch.setenv("ORIGIN_MODE", "engine")
    monkeypatch.delenv("FEATHERLESS_API_KEY", raising=False)
    ag._RUN.update({"start": None, "cases": 0, "seconds": 0.0})
    ag._LLM, ag._LLM_TRIED = None, False
    yield


def solve(tmp_path, instruction=INSTRUCTION):
    return ag.solve(instruction, Path("data/Market-cloudbed-1"),
                    {"out_dir": tmp_path, "dataset_dir": Path("data/Market-cloudbed-1")})


def test_one_failure_gives_one_parseable_object(tmp_path):
    sol = solve(tmp_path)
    objs = parsed(sol.prediction)
    assert len(objs) == 1
    assert objs[0] == ("2022-03-20 09:09:00", "shippingservice-1",
                       "container read I/O load")


def test_evidence_and_usage_are_populated(tmp_path):
    sol = solve(tmp_path)
    assert "shippingservice-1" in sol.evidence
    assert sol.usage == {}              # no key, so no model was called


def test_trace_line_written_per_case(tmp_path):
    solve(tmp_path)
    solve(tmp_path)
    lines = (tmp_path / "origin_trace.jsonl").read_text().splitlines()
    assert len(lines) == 2
    rec = json.loads(lines[0])
    assert set(rec) >= {"instruction_sha1", "route", "final", "confidence", "seconds"}
    assert rec["final"][0][1] == "shippingservice-1"


def test_asks_filter_drops_unasked_fields(tmp_path, monkeypatch):
    from origin import fixture
    monkeypatch.setattr(ag, "analyze", lambda i, d, dl: fixture.make_analysis(
        asks={"datetime": False, "component": True, "reason": True}))
    sol = solve(tmp_path)
    assert "occurrence datetime" not in sol.prediction
    assert "root cause component" in sol.prediction


def test_engine_crash_still_answers_with_the_right_count(tmp_path, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("engine exploded")
    monkeypatch.setattr(ag, "analyze", boom)
    sol = solve(tmp_path, INSTRUCTION.replace("one failure", "two failures"))
    objs = parsed(sol.prediction)
    assert len(objs) == 2               # count comes from the instruction, not the engine
    # The engine died before producing a window, so there is nothing honest to put
    # in the fields -- but the object count still has to match or the case scores 0.
    assert "engine exploded" in sol.evidence
    assert json.loads((tmp_path / "origin_trace.jsonl").read_text())["route"] == "fallback"


def test_no_candidates_still_answers(tmp_path, monkeypatch):
    from origin import fixture
    monkeypatch.setattr(ag, "analyze", lambda i, d, dl: fixture.make_empty_analysis())
    sol = solve(tmp_path)
    assert len(parsed(sol.prediction)) == 1


def test_prediction_is_never_unscoreable(tmp_path):
    """A correct prediction must actually score 1.0 through the real evaluator."""
    sol = solve(tmp_path)
    points = ("The only predicted root cause component is shippingservice-1\n"
              "The only predicted root cause reason is container read I/O load\n"
              "The only root cause occurrence time is within 1 minutes "
              "(i.e., <=1min) of 2022-03-20 09:09:00")
    _, failed, score = evaluate(sol.prediction, points)
    assert score == 1.0 and not failed


def test_running_average_over_the_limit_forces_engine_only(tmp_path, monkeypatch):
    monkeypatch.setenv("ORIGIN_MODE", "routed")
    ag._RUN.update({"cases": 1, "seconds": 9_999.0})
    sol = solve(tmp_path)
    assert "engine only for the rest of the run" in sol.evidence
    assert json.loads((tmp_path / "origin_trace.jsonl").read_text())["mode"] == "engine"


def test_heuristic_fallback_still_writes_a_trace_line(tmp_path, monkeypatch):
    """Until origin/engine.py lands the agent borrows the heuristic. It must
    still trace: the eval harness joins on this file, and a case with no line
    looks like a case that never ran."""
    def no_engine(*a, **k):
        raise ImportError("no module named origin.engine")

    stub = Solution(prediction='```json\n{"1": {}}\n```', evidence="baseline")
    monkeypatch.setattr(ag, "analyze", no_engine)
    monkeypatch.setattr("agents.heuristic.solve", lambda i, d, c: stub)

    sol = solve(tmp_path)
    assert "not ORIGIN" in sol.evidence          # never passed off as our work
    assert sol.prediction == stub.prediction
    rec = json.loads((tmp_path / "origin_trace.jsonl").read_text().splitlines()[0])
    assert rec["route"] == "heuristic_fallback"
    assert rec["errors"] == ["origin.engine not importable"]
