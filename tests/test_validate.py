"""origin.validate -- code fills in everything the model did not choose.

The model picks a candidate and a reason. Component names and timestamps are
derived here, so the tests are about derivation and about the count: a wrong
number of answers scores the whole case zero however right each one is.
"""
from __future__ import annotations

from origin.config import ESCALATE_MARGIN, GATE_MARGIN
from origin.contract import fmt_ts
from origin.fixture import ONSET, WIN_LO, make_analysis, make_clear_analysis, make_empty_analysis
from origin.validate import validate


def decision(route="flash", picks=None, **kw):
    d = {"route": route, "picks": picks, "errors": [], "notes": [], "why": None}
    d.update(kw)
    return d


# --- the model's pick becomes the answer ---------------------------------------

def test_a_pick_sets_component_and_reason_and_code_sets_the_time():
    a = make_analysis()
    answers, _, _ = validate(a, decision(picks=[{"cid": "C3", "reason": "container network latency",
                                                 "fact_ids": ["F6"]}]))
    assert len(answers) == 1
    assert answers[0]["component"] == "checkoutservice-2"
    assert answers[0]["reason"] == "container network latency"
    # F6 is the signal that votes for network latency, so its onset is the time
    assert answers[0]["datetime"] == fmt_ts(ONSET + 30)


def test_the_time_comes_from_the_signal_that_votes_for_the_chosen_reason():
    """C1's loudest signal is F1 (read I/O). Choosing the CPU reason must take
    F2's onset, not F1's -- otherwise the answer and its evidence disagree."""
    a = make_analysis()
    answers, _, _ = validate(a, decision(picks=[{"cid": "C1", "reason": "container CPU load",
                                                 "fact_ids": []}]))
    assert answers[0]["datetime"] == fmt_ts(ONSET + 60)     # F2, not F1


def test_no_picks_keeps_the_engine_answer():
    a = make_analysis()
    answers, _, _ = validate(a, decision(route="gate"))
    assert answers[0]["component"] == a.engine_answers[0]["component"]


# --- illegal or impossible picks -------------------------------------------------

def test_an_illegal_reason_falls_back_to_the_engines():
    a = make_analysis()
    answers, _, notes = validate(a, decision(picks=[{"cid": "C1", "reason": "node CPU load",
                                                     "fact_ids": []}]))
    assert answers[0]["reason"] == "container read I/O load"
    assert any("not legal for a pod" in n for n in notes)


def test_an_unknown_candidate_is_dropped_and_the_engine_fills_in():
    a = make_analysis()
    answers, _, notes = validate(a, decision(picks=[{"cid": "C42", "reason": "container CPU load",
                                                     "fact_ids": []}]))
    assert len(answers) == 1
    assert answers[0]["component"] == a.engine_answers[0]["component"]
    assert any("unknown candidate" in n for n in notes)


def test_the_same_component_twice_is_replaced_not_duplicated():
    a = make_analysis(n_failures=2)
    picks = [{"cid": "C1", "reason": "container read I/O load", "fact_ids": []},
             {"cid": "C1", "reason": "container CPU load", "fact_ids": []}]
    answers, _, notes = validate(a, decision(picks=picks))
    assert len(answers) == 2
    assert len({x["component"] for x in answers}) == 2
    assert any("twice" in n for n in notes)


# --- the count always matches -----------------------------------------------------

def test_two_failures_give_exactly_two_answers_in_time_order():
    a = make_analysis(n_failures=2)
    answers, _, _ = validate(a, decision(route="gate"))
    assert len(answers) == 2
    assert answers[0]["datetime"] <= answers[1]["datetime"]


def test_more_failures_than_candidates_still_matches_the_count():
    a = make_empty_analysis(n_failures=3)
    answers, _, notes = validate(a, decision(route="engine_only"))
    assert len(answers) == 3
    assert any("padded so the count matches" in n for n in notes)


def test_extra_picks_are_trimmed_to_the_count():
    a = make_analysis(n_failures=1)
    picks = [{"cid": "C1", "reason": "container read I/O load", "fact_ids": []},
             {"cid": "C3", "reason": "container network latency", "fact_ids": []}]
    answers, _, _ = validate(a, decision(picks=picks))
    assert len(answers) == 1


# --- confidence is computed, never the model's own claim ----------------------------

def test_a_gated_clear_case_is_high():
    a = make_clear_analysis()
    _, conf, _ = validate(a, decision(route="gate"))
    assert conf == "High"


def test_an_ambiguous_agreed_case_is_medium():
    a = make_analysis()
    _, conf, _ = validate(a, decision(picks=[{"cid": "C1", "reason": "container read I/O load",
                                              "fact_ids": []}]))
    assert conf == "Medium"


def test_the_model_overruling_the_engine_is_low():
    a = make_clear_analysis()
    _, conf, _ = validate(a, decision(picks=[{"cid": "C3", "reason": "container network latency",
                                              "fact_ids": []}]))
    assert conf == "Low"


def test_a_tiny_margin_is_low():
    a = make_clear_analysis()
    a.margin = ESCALATE_MARGIN / 2
    _, conf, _ = validate(a, decision(route="gate"))
    assert conf == "Low"


def test_a_fallback_is_low_and_says_no_model_confirmed_it():
    a = make_clear_analysis()
    d = decision(route="fallback")
    _, conf, _ = validate(a, d)
    assert conf == "Low" and "no model confirmed" in d["confidence_why"]


def test_an_error_anywhere_is_low():
    a = make_clear_analysis()
    _, conf, _ = validate(a, decision(route="gate", errors=["flash: busy"]))
    assert conf == "Low"


def test_a_model_claiming_high_does_not_make_it_high():
    """The CP1 spike had models answering "high" while getting the JSON shape
    wrong. Their own confidence is recorded, never used."""
    a = make_analysis()
    a.margin = ESCALATE_MARGIN / 2
    _, conf, _ = validate(a, decision(picks=[{"cid": "C1", "reason": "container read I/O load",
                                              "fact_ids": []}],
                                      confidence_model="high"))
    assert conf == "Low"


def test_confidence_why_is_set_for_the_evidence_file():
    a = make_clear_analysis()
    d = decision(route="gate")
    validate(a, d)
    assert d["confidence_why"] and d["confidence_why"][0].islower()


def test_reason_only_mode_keeps_the_engines_component(monkeypatch):
    """Measured on the holdout: models match the engine on reason (55.6%) and
    lose on component (44-48% vs 55.6%); the time collapse is downstream of the
    component. So take the model's reason and keep the engine's component."""
    monkeypatch.setenv("ORIGIN_REASON_ONLY", "1")
    a = make_analysis()
    answers, _, notes = validate(a, decision(picks=[
        {"cid": "C3", "reason": "container network latency", "fact_ids": []}]))
    assert answers[0]["component"] == "shippingservice-1"   # engine's C1, not C3
    assert answers[0]["reason"] == "container network latency"   # model's choice
    assert any("reason-only mode" in n for n in notes)


def test_reason_only_mode_is_off_by_default():
    a = make_analysis()
    answers, _, _ = validate(a, decision(picks=[
        {"cid": "C3", "reason": "container network latency", "fact_ids": []}]))
    assert answers[0]["component"] == "checkoutservice-2"


def test_reason_only_pins_every_answer_not_just_the_first(monkeypatch):
    """Two of the six holdout losses were multi-failure cases where the model
    kept answer 1 and wrecked answer 2, so pinning only the top would miss them."""
    monkeypatch.setenv("ORIGIN_REASON_ONLY", "1")
    a = make_analysis(n_failures=2)
    engine_components = [x["component"] for x in a.engine_answers]
    answers, _, notes = validate(a, decision(picks=[
        {"cid": "C3", "reason": "container network latency", "fact_ids": []},
        {"cid": "C4", "reason": "container network latency", "fact_ids": []}]))
    assert [x["component"] for x in answers] == engine_components
    assert sum("reason-only mode" in n for n in notes) == 2
