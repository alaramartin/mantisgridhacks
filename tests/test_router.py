"""origin.router -- the gate, the escalation and what a model is allowed to say.

The model is never trusted to write a name, a number or a free reason, so the
tests that matter are the rejection ones: a reply naming a candidate that does
not exist, or a reason illegal for that candidate's level, must be thrown away
whole rather than half-used.
"""
from __future__ import annotations

import json

import pytest

from origin import router
from origin.config import CHEAP, ESCALATE_MARGIN, STRONG, STRONG_MIN_REMAINING_S
from origin.fixture import make_analysis, make_clear_analysis, make_empty_analysis

FAR = 1e12          # a deadline that is never close


class FakeLLM:
    """Records calls and replays scripted replies, one per call."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls: list[dict] = []
        self.usage: dict = {}

    def ask(self, models, prompt, **kw):
        self.calls.append({"models": list(models), "prompt": prompt, "kw": kw})
        if not self.replies:
            raise AssertionError("more calls than scripted replies")
        r = self.replies.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def reply(cid="C1", reason="container read I/O load", facts=("F1",),
          confidence="high", why="F1 shows the read I/O rise first."):
    return json.dumps({"answers": [{"candidate": cid, "reason": reason,
                                    "fact_ids": list(facts)}],
                       "confidence": confidence, "why": why})


# --- the fact sheet -----------------------------------------------------------

def test_fact_sheet_has_every_section_and_the_legal_vocabulary():
    sheet = router.fact_sheet(make_analysis())
    for header in ("CASE:", "LEGAL REASONS", "CANDIDATES", "FACTS", "NOTES"):
        assert header in sheet
    assert "container read I/O load" in sheet and "node CPU spike" in sheet
    assert "C1 shippingservice-1 (pod, on node-5)" in sheet
    assert "DEMOTED: its callee shippingservice-1" in sheet
    assert "2022-03-20 09:09:00" in sheet          # onset, not epoch


def test_fact_sheet_respects_the_candidate_and_fact_caps(monkeypatch):
    monkeypatch.setattr(router, "CANDIDATES_SHOWN", 2)
    monkeypatch.setattr(router, "FACTS_MAX", 3)
    sheet = router.fact_sheet(make_analysis())
    assert not any(l.startswith("C3 ") for l in sheet.splitlines())
    assert sum(l.startswith("- F") for l in sheet.splitlines()) == 3


# --- the gate -----------------------------------------------------------------

def test_clear_case_is_gated_and_calls_nothing():
    llm = FakeLLM()
    d = router.route(make_clear_analysis(), llm, "routed", FAR)
    assert d["route"] == "gate" and llm.calls == []
    assert d["picks"] is None


def test_ambiguous_case_is_not_gated():
    # component+reason only, so the "all three fields asked" escalation stays out of it
    a = make_analysis(asks={"datetime": False, "component": True, "reason": True})
    llm = FakeLLM(reply())
    d = router.route(a, llm, "routed", FAR)
    assert d["route"] == "flash" and len(llm.calls) == 1


def test_all_three_fields_asked_escalates_on_its_own():
    """Spec'd in PLAN Phase 3. Worth knowing at tuning time: most tasks ask all
    three, so this one rule sends most cases to the strong model."""
    llm = FakeLLM(reply(), reply())
    d = router.route(make_analysis(), llm, "routed", FAR)
    assert d["route"] == "strong"
    assert "all three fields asked" in " ".join(d["notes"])


def test_two_failures_are_never_gated():
    llm = FakeLLM(reply(), reply())
    d = router.route(make_clear_analysis(n_failures=2), llm, "routed", FAR)
    assert d["route"] != "gate" and llm.calls


def test_engine_mode_and_no_client_call_nothing():
    assert router.route(make_analysis(), FakeLLM(), "engine", FAR)["route"] == "engine_only"
    assert router.route(make_analysis(), None, "routed", FAR)["route"] == "engine_only"


def test_no_candidates_calls_nothing():
    d = router.route(make_empty_analysis(), FakeLLM(), "routed", FAR)
    assert d["route"] == "engine_only" and "no candidates" in d["notes"][0]


# --- thinking off, and the call parameters --------------------------------------

def test_flash_call_turns_thinking_off_and_caps_tokens():
    llm = FakeLLM(reply())
    router.route(make_analysis(), llm, "routed", FAR)
    kw = llm.calls[0]["kw"]
    assert kw["extra_body"] == {"chat_template_kwargs": {"enable_thinking": False}}
    assert kw["temperature"] == 0 and kw["max_tokens"] == 700 and kw["timeout"] == 25
    assert llm.calls[0]["models"] == CHEAP


# --- rejecting a bad reply ------------------------------------------------------

@pytest.mark.parametrize("bad, why", [
    ("not json at all", "no JSON"),
    ('{"answers": []}', "count"),
    (reply(cid="C99"), "unknown candidate"),
    (reply(reason="it broke"), "illegal reason"),
    (reply(reason="node CPU load"), "node reason on a pod"),
    ("", "empty"),
])
def test_unusable_replies_are_rejected_whole(bad, why):
    picks, _, _, err = router.parse_reply(bad, make_analysis())
    assert picks is None, why
    assert err


def test_a_good_reply_parses_into_picks():
    picks, conf, w, err = router.parse_reply(reply(), make_analysis())
    assert err is None and conf == "high"
    assert picks == [{"cid": "C1", "reason": "container read I/O load",
                      "fact_ids": ["F1"]}]


def test_json_wrapped_in_prose_is_still_read():
    picks, _, _, err = router.parse_reply("Sure!\n```json\n" + reply() + "\n```", make_analysis())
    assert err is None and picks[0]["cid"] == "C1"


def test_unknown_fact_ids_are_dropped_not_fatal():
    picks, _, _, err = router.parse_reply(reply(facts=("F1", "F999")), make_analysis())
    assert err is None and picks[0]["fact_ids"] == ["F1"]


# --- escalation -----------------------------------------------------------------

def test_flash_disagreeing_with_the_engine_escalates():
    llm = FakeLLM(reply(cid="C3", reason="container network latency"), reply())
    d = router.route(make_analysis(), llm, "routed", FAR)
    assert d["route"] == "strong"
    assert llm.calls[1]["models"] == STRONG
    assert "disagreed" in " ".join(d["notes"])
    assert "A fast model picked" in llm.calls[1]["prompt"]


def test_strong_call_also_turns_thinking_off():
    """Deviation from PLAN Phase 3, measured at CP3 on GLM-5.2, 3 calls each:
    thinking ON parsed 2/3 at 9.5-28.7 s (one hit the token cap and returned no
    JSON); OFF parsed 3/3 at 2.4-10.7 s. ON also exceeded CALL_TIMEOUT_S on 2/3,
    which would trip llm.py's breaker and demote us to GLM-5.1 for the run."""
    llm = FakeLLM(reply(cid="C3", reason="container network latency"), reply())
    router.route(make_analysis(), llm, "routed", FAR)
    assert llm.calls[1]["kw"]["extra_body"] == {
        "chat_template_kwargs": {"enable_thinking": False}}


def test_a_tiny_margin_escalates_even_when_flash_agrees():
    a = make_analysis()
    a.margin = ESCALATE_MARGIN / 2
    llm = FakeLLM(reply(), reply())
    assert router.route(a, llm, "routed", FAR)["route"] == "strong"


def test_unusable_flash_escalates_and_says_so():
    llm = FakeLLM("garbage", reply())
    d = router.route(make_analysis(), llm, "routed", FAR)
    assert d["route"] == "strong"
    assert any("flash:" in e for e in d["errors"])
    assert "A fast model failed to answer" in llm.calls[1]["prompt"]


def test_escalation_is_skipped_when_the_deadline_is_close():
    import time
    llm = FakeLLM(reply(cid="C3", reason="container network latency"))
    d = router.route(make_analysis(), llm, "routed",
                     time.time() + STRONG_MIN_REMAINING_S - 1)
    assert d["route"] == "flash" and len(llm.calls) == 1
    assert "escalation skipped" in " ".join(d["notes"])


def test_everything_failing_is_a_fallback_not_a_decision():
    llm = FakeLLM(RuntimeError("busy"), RuntimeError("busy"))
    d = router.route(make_analysis(), llm, "routed", FAR)
    assert d["route"] == "fallback" and d["picks"] is None and len(d["errors"]) == 2


# --- single-model ablation --------------------------------------------------------

def test_single_mode_makes_exactly_one_call_and_never_gates(monkeypatch):
    monkeypatch.setenv("RCA_MODEL", "zai-org/GLM-5.2")
    llm = FakeLLM(reply())
    d = router.route(make_clear_analysis(), llm, "single", FAR)
    assert d["route"] == "flash" and len(llm.calls) == 1
    assert llm.calls[0]["models"] == ["zai-org/GLM-5.2"]
    assert llm.calls[0]["kw"]["max_tokens"] == 700
