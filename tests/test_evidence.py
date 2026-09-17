"""origin.evidence -- the four sections, and the grounding check on model prose.

Evidence is worth 35% of the grade against accuracy's 20%, and a fluent wrong
sentence is worse than no sentence because it reads exactly like a right one.
So most of this file is about what gets thrown away.
"""
from __future__ import annotations

from origin.evidence import build_evidence, grounded
from origin.fixture import make_analysis, make_clear_analysis, make_empty_analysis
from origin.router import fact_sheet
from origin.validate import validate

SECTIONS = ("## Answer", "## Confidence", "## Evidence", "## Ruled out",
            "## How this was produced")


def built(a=None, d=None, answers=None):
    a = a or make_analysis()
    d = d or {"route": "gate", "picks": None, "errors": [], "notes": [],
              "why": None, "seconds": {"flash": 0.0, "strong": 0.0},
              "sheet": fact_sheet(a)}
    answers, confidence, notes = validate(a, d)
    return build_evidence(a, answers, d, confidence, notes, 4.2), d


# --- structure ------------------------------------------------------------------

def test_all_sections_present_and_in_order():
    md, _ = built()
    positions = [md.index(s) for s in SECTIONS]
    assert positions == sorted(positions)


def test_facts_carry_the_file_the_id_and_an_epoch_so_a_judge_can_grep():
    md, _ = built()
    assert "metric_container.csv" in md
    assert "cmdb_id=node-5.shippingservice-1" in md
    assert "epoch=" in md
    assert "median of 60 samples" in md          # derived numbers say what they are


def test_ruled_out_names_the_demotion_reason():
    md, _ = built()
    assert "## Ruled out" in md
    assert "its callee shippingservice-1 went wrong 30 s earlier" in md


def test_unasked_fields_are_labelled_not_hidden():
    a = make_analysis(asks={"datetime": False, "component": True, "reason": True})
    md, _ = built(a=a)
    assert "(not asked)" in md


def test_an_empty_analysis_still_produces_every_section():
    md, _ = built(a=make_empty_analysis())
    for s in SECTIONS:
        assert s in md


# --- never call a fallback a decision (NON-NEGOTIABLE RULE 8) ---------------------

def test_a_fallback_says_no_model_decided_it():
    a = make_analysis()
    d = {"route": "fallback", "picks": None, "errors": ["flash: busy"], "notes": [],
         "why": None, "seconds": {"flash": 2.0, "strong": 0.0}, "sheet": fact_sheet(a)}
    md, _ = built(a=a, d=d)
    assert "No model decided this." in md
    assert "flash: busy" in md


def test_a_gate_says_no_model_was_called():
    md, _ = built()
    assert "no model was called" in md


def test_a_model_changing_the_answer_is_stated_plainly():
    a = make_analysis()
    d = {"route": "strong", "picks": [{"cid": "C3", "reason": "container network latency",
                                       "fact_ids": ["F6"]}],
         "errors": [], "notes": [], "why": None,
         "seconds": {"flash": 2.1, "strong": 5.4}, "sheet": fact_sheet(a),
         "strong": {"models": ["zai-org/GLM-5.2"], "seconds": 5.4, "error": None}}
    md, _ = built(a=a, d=d)
    assert "model changed the engine answer" in md
    assert "`zai-org/GLM-5.2`" in md


# --- grounding --------------------------------------------------------------------

def test_a_number_not_in_the_facts_fails_grounding():
    a = make_analysis()
    ok, bad = grounded("The read I/O hit 73.2 MB/s.", fact_sheet(a), a)
    assert not ok and "73.2" in bad[0]


def test_a_sentence_citing_real_facts_and_numbers_passes():
    a = make_analysis()
    sheet = fact_sheet(a)
    ok, bad = grounded("F1 shows shippingservice-1 reaching 2.7e+07 at its peak; "
                       "C2 followed it.", sheet, a)
    assert ok, bad


def test_small_integers_are_counting_not_citing():
    a = make_analysis()
    ok, _ = grounded("The first two candidates share a node.", fact_sheet(a), a)
    assert ok


def test_an_invented_component_fails_grounding():
    a = make_analysis()
    ok, bad = grounded("The fault is in paymentservice-9.", fact_sheet(a), a)
    assert not ok and "paymentservice-9" in bad[0]


def test_an_unknown_fact_id_fails_grounding():
    a = make_analysis()
    ok, bad = grounded("See F99.", fact_sheet(a), a)
    assert not ok and "F99" in bad[0]


def test_ungrounded_prose_is_dropped_from_the_file_and_flagged():
    a = make_analysis()
    d = {"route": "flash", "picks": [{"cid": "C1", "reason": "container read I/O load",
                                      "fact_ids": ["F1"]}],
         "errors": [], "notes": [], "seconds": {"flash": 2.0, "strong": 0.0},
         "sheet": fact_sheet(a),
         "why": "Throughput collapsed to 73.2 MB/s across the fleet."}
    md, d = built(a=a, d=d)
    assert "Throughput collapsed" not in md          # the sentence itself is gone
    assert "The model's reasoning" not in md
    # the offending number survives only inside the note that explains the removal,
    # which is transparency rather than a leak
    assert "model prose removed" in md and "number 73.2 is not in the facts" in md
    assert d["grounding_dropped"] is True


def test_grounded_prose_is_kept():
    a = make_analysis()
    d = {"route": "flash", "picks": [{"cid": "C1", "reason": "container read I/O load",
                                      "fact_ids": ["F1"]}],
         "errors": [], "notes": [], "seconds": {"flash": 2.0, "strong": 0.0},
         "sheet": fact_sheet(a),
         "why": "F1 shows the read I/O rise starting before anything on C2."}
    md, d = built(a=a, d=d)
    assert "F1 shows the read I/O rise" in md
    assert not d.get("grounding_dropped")


# --- low confidence has to be useful, not just hedged ------------------------------

def test_low_confidence_names_the_runner_up_and_what_would_settle_it():
    a = make_clear_analysis()
    a.margin = 0.01
    md, _ = built(a=a)
    assert "**Low.**" in md
    assert "What would settle it" in md
    assert "node-5" in md
