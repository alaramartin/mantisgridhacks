"""A Featherless client that counts tokens per model and survives a busy one.

    llm = LLM()                                   # key and endpoint from the environment
    text = llm.ask("zai-org/GLM-4.7-Flash", "How many failures does this ask for? ...")
    llm.usage
    # {"zai-org/GLM-4.7-Flash": {"prompt_tokens": 812, "completion_tokens": 40, "calls": 1}}

Return `llm.usage` as your Solution's `usage` and run.py writes it to usage.jsonl,
per case and per model. `cost.py` turns that into dollars.

The key comes from FEATHERLESS_API_KEY and the endpoint from FEATHERLESS_BASE_URL
(default https://api.featherless.ai/v1). That is how we run your agent on our key,
so never hard-code either.

**Models go busy.** A capacity error arrives as HTTP 200 with an error body and no
`choices`, so the naive `r.choices[0]` raises instead of seeing it. `ask()` retries
with a growing pause, then moves to the next model you named:

    llm.ask(["zai-org/GLM-4.7-Flash", "zai-org/GLM-5.3-Flash"], prompt)

A failed call carries no usage, so retries cost nothing in dollars -- but they do
cost the case's ten-minute clock, and a model that is down stays down for minutes,
not milliseconds. So a model that fails twice is dropped for the rest of the run
rather than rediscovered on every call. Without that, one unavailable model can eat
a whole run in retries while billing nothing.

The policy here is a starting point, not the only sensible one -- `docs/models.md`
says what it is defending against, and tuning it is fair game.
"""
from __future__ import annotations

import os
import re
import time

from openai import APIStatusError, APITimeoutError, APIConnectionError, OpenAI

DEFAULT_BASE_URL = "https://api.featherless.ai/v1"
RETRIES = 3          # per model, before moving to the next one
BACKOFF = 2.0        # seconds, doubling each time
BREAKER = 2          # give up on a model for the whole run after this many failures


class ModelUnavailable(RuntimeError):
    """Every model offered was busy, or failed, for this call."""


class LLM:
    def __init__(self, retries: int = RETRIES, backoff: float = BACKOFF,
                 breaker: int = BREAKER) -> None:
        key = os.environ.get("FEATHERLESS_API_KEY")
        if not key:
            raise RuntimeError("FEATHERLESS_API_KEY is not set")
        self.client = OpenAI(api_key=key,
                             base_url=os.environ.get("FEATHERLESS_BASE_URL", DEFAULT_BASE_URL))
        self.usage: dict[str, dict[str, int]] = {}
        self.retries = retries
        self.backoff = backoff
        self.breaker = breaker
        self.failures: list[str] = []      # what went wrong, for your evidence file
        self.down: dict[str, int] = {}     # model -> failures seen this run

    def ask(self, model: str | list[str], prompt: str | list[dict], **kwargs) -> str:
        """One chat call. `prompt` is a string (one user message) or a message list.

        `model` is one name, or several in preference order -- each is retried
        before the next is tried at all.
        """
        messages = [{"role": "user", "content": prompt}] if isinstance(prompt, str) else prompt
        models = [model] if isinstance(model, str) else list(model)
        if not models:
            raise ValueError("ask() needs at least one model")

        tried = [m for m in models if self.down.get(m, 0) < self.breaker]
        if not tried:
            # every option is already known bad; do not spend the case's clock
            # rediscovering that
            raise ModelUnavailable(f"all of {models} tripped the breaker this run")

        for name in tried:
            for attempt in range(self.retries + 1):
                try:
                    return self._once(name, messages, **kwargs)
                except ModelUnavailable as e:
                    self._failed(name, str(e))
                    if attempt < self.retries and not self._tripped(name):
                        time.sleep(self.backoff * 2 ** attempt)
                    else:
                        break
                except (APITimeoutError, APIConnectionError) as e:
                    self._failed(name, type(e).__name__)
                    if attempt < self.retries and not self._tripped(name):
                        time.sleep(self.backoff * 2 ** attempt)
                    else:
                        break
                except APIStatusError as e:
                    # 4xx that is not capacity -- a bad request or an unknown
                    # model. Retrying will not fix it; try the next model.
                    self._failed(name, f"HTTP {e.status_code}")
                    break
        raise ModelUnavailable(f"none of {models} answered: {self.failures[-3:]}")

    def _failed(self, model: str, why: str) -> None:
        self.failures.append(f"{model}: {why}")
        self.down[model] = self.down.get(model, 0) + 1

    def _tripped(self, model: str) -> bool:
        return self.down.get(model, 0) >= self.breaker

    def _once(self, model: str, messages: list[dict], **kwargs) -> str:
        r = self.client.chat.completions.create(model=model, messages=messages, **kwargs)

        # A busy model answers 200 with an error body and no choices. The SDK
        # parses it happily, so the check has to be ours.
        if not getattr(r, "choices", None):
            err = getattr(r, "error", None) or {}
            msg = err.get("message") if isinstance(err, dict) else str(err)
            raise ModelUnavailable(msg or "no choices in the response")

        # Only a call that produced something is billed, so count it only here.
        u = self.usage.setdefault(model, {"prompt_tokens": 0, "completion_tokens": 0,
                                          "calls": 0})
        u["calls"] += 1
        if r.usage:
            u["prompt_tokens"] += r.usage.prompt_tokens or 0
            u["completion_tokens"] += r.usage.completion_tokens or 0
        text = r.choices[0].message.content or ""
        # GLM models can think out loud first; keep only the answer
        return re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()
