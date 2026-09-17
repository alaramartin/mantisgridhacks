#!/usr/bin/env python3
"""Minimal reproduction: Featherless returns GLM Flash answers in `message.reasoning`
with `message.content` empty, so the starter's `llm.py` returns "" on every call.

    export FEATHERLESS_API_KEY=...
    python scripts/featherless_reasoning_repro.py

Self-contained on purpose: it imports nothing from this repo, so an organiser can
drop it into the pristine starter and run it. It uses only the OpenAI SDK, exactly
as `docs/models.md` recommends.

WHAT IT SHOWS

  * `zai-org/GLM-4.7-Flash` answers with `content == ""` and the full answer in
    `message.reasoning`, at `finish_reason == "stop"` well under the token cap --
    so this is a completed response, not a truncation.
  * `zai-org/GLM-5.2` answers normally, with `content` populated. The behaviour is
    specific to the Flash models, not to the request.
  * The last block replays the starter's own extraction line
    (`r.choices[0].message.content or ""`) to show what an unmodified `llm.py`
    hands back: an empty string, for a call that was billed.

WHY IT MATTERS

`docs/models.md` steers teams to the Flash tier for cheap triage, and
`starter/agents/routed.py` uses it as its cheap tier. On an unmodified `llm.py`
every one of those calls returns "" while still consuming tokens, so the agent
sees no answer and silently falls back -- and the team is billed for it.
"""
from __future__ import annotations

import os
import sys

try:
    from openai import OpenAI
except ImportError:
    sys.exit("pip install openai")

BASE_URL = os.environ.get("FEATHERLESS_BASE_URL", "https://api.featherless.ai/v1")
KEY = os.environ.get("FEATHERLESS_API_KEY")
if not KEY:
    sys.exit("FEATHERLESS_API_KEY is not set")

# Thinking off, exactly as docs/models.md describes the hybrid-reasoning toggle.
THINKING_OFF = {"chat_template_kwargs": {"enable_thinking": False}}

PROMPT = """Reply with JSON only, no prose:
{"answer": "<one of: alpha, beta, gamma>", "why": "one short sentence"}
Pick "beta"."""

MODELS = ["zai-org/GLM-4.7-Flash", "zai-org/GLM-5.3-Flash", "zai-org/GLM-5.2"]
CALLS = 2
MAX_TOKENS = 700          # the cap a real agent would use, not a truncating one

client = OpenAI(api_key=KEY, base_url=BASE_URL)

print(f"endpoint: {BASE_URL}")
print(f"settings: max_tokens={MAX_TOKENS}, temperature=0, thinking OFF\n")
print(f"{'model':<24} {'#':<2} {'finish':<7} {'out':>4}  {'content':>9}  {'reasoning':>9}")
print("-" * 70)

rows = []
for model in MODELS:
    for i in range(1, CALLS + 1):
        try:
            r = client.chat.completions.create(
                model=model, messages=[{"role": "user", "content": PROMPT}],
                max_tokens=MAX_TOKENS, temperature=0, timeout=60,
                extra_body=THINKING_OFF)
            m = r.choices[0].message
            content = m.content or ""
            reasoning = getattr(m, "reasoning", None) or ""
            rows.append((model, content, reasoning))
            print(f"{model:<24} {i:<2} {r.choices[0].finish_reason:<7} "
                  f"{r.usage.completion_tokens:>4}  "
                  f"{(str(len(content)) + ' ch') if content.strip() else 'EMPTY':>9}  "
                  f"{(str(len(reasoning)) + ' ch') if reasoning.strip() else '-':>9}")
        except Exception as e:                       # noqa: BLE001
            print(f"{model:<24} {i:<2} FAILED {type(e).__name__}: {str(e)[:40]}")

print("\n--- what the starter's llm.py would return for each call ---")
print("    (its extraction line is: text = r.choices[0].message.content or \"\")\n")
for model, content, reasoning in rows:
    starter = repr((content or "")[:60])
    patched = repr((content if content.strip() else reasoning)[:60])
    print(f"  {model}")
    print(f"     starter returns : {starter}")
    print(f"     answer actually : {patched}")

empty = sum(1 for _, c, r in rows if not c.strip() and r.strip())
print(f"\n{empty} of {len(rows)} calls put the answer in `reasoning` with `content` empty.")
if empty:
    print("On those calls an unmodified starter/llm.py returns the empty string,")
    print("after the tokens have already been counted and billed.")
