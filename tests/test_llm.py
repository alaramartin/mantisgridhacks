"""The Featherless `reasoning` patch in llm.py (PLAN Person 2, Phase 2).

Featherless's Flash models return the answer in `message.reasoning` with an
empty `message.content` (docs/model-findings.md section 3). The starter client read
only `.content`, so every Flash call came back as "" -- billed and useless.
These tests pin the fallback so nobody "tidies" it away.
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import llm as llm_mod  # noqa: E402


def _client(message) -> llm_mod.LLM:
    """An LLM whose one call returns `message`, with no network and no key."""
    obj = llm_mod.LLM.__new__(llm_mod.LLM)
    obj.usage, obj.failures, obj.down = {}, [], {}
    obj.retries, obj.backoff, obj.breaker = 0, 0.0, 2

    response = SimpleNamespace(
        choices=[SimpleNamespace(message=message)],
        usage=SimpleNamespace(prompt_tokens=100, completion_tokens=20),
    )
    obj.client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(
        create=lambda **kw: response)))
    return obj


def test_reasoning_used_when_content_is_empty():
    out = _client(SimpleNamespace(content="", reasoning='{"a":1}')).ask("m", "p")
    assert out == '{"a":1}'


def test_reasoning_content_is_also_accepted():
    out = _client(SimpleNamespace(content=None, reasoning=None,
                                  reasoning_content='{"b":2}')).ask("m", "p")
    assert out == '{"b":2}'


def test_content_wins_when_both_are_populated():
    out = _client(SimpleNamespace(content='{"real":1}', reasoning="rambling")).ask("m", "p")
    assert out == '{"real":1}'


@pytest.mark.parametrize("field", ["content", "reasoning"])
def test_think_tags_stripped_on_both_fields(field):
    text = "<think>first I shall ponder</think>{\"a\":1}"
    kwargs = {"content": "", "reasoning": ""} | {field: text}
    assert _client(SimpleNamespace(**kwargs)).ask("m", "p") == '{"a":1}'


def test_whitespace_only_content_falls_through_to_reasoning():
    out = _client(SimpleNamespace(content="   \n ", reasoning="answer")).ask("m", "p")
    assert out == "answer"


def test_usage_is_counted_once_per_call():
    obj = _client(SimpleNamespace(content="", reasoning="x"))
    obj.ask("zai-org/GLM-4.7-Flash", "p")
    assert obj.usage["zai-org/GLM-4.7-Flash"] == {
        "prompt_tokens": 100, "completion_tokens": 20, "calls": 1}


def test_an_answerless_reply_is_a_failure_not_a_success():
    """The starter returned "" here, which reads as a successful call: retry,
    model fallback and the breaker all stay asleep while the call is billed and
    the caller gets nothing. Raising lets the machinery do its job."""
    obj = _client(SimpleNamespace(content="", reasoning="", reasoning_content=""))
    with pytest.raises(llm_mod.ModelUnavailable):
        obj.ask("m", "p")
    assert obj.down.get("m", 0) >= 1          # the breaker saw it


def test_a_reply_that_is_only_think_tags_is_also_a_failure():
    obj = _client(SimpleNamespace(content="<think>hmm</think>", reasoning=""))
    with pytest.raises(llm_mod.ModelUnavailable):
        obj.ask("m", "p")
