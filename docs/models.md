# Models and cost

## The rule: GLM family, chosen per call

Everything your agent runs uses the **GLM family** (`zai-org/*`) on **Featherless AI**.
Within that family, **your agent picks the model for each call** — and building that
routing is the core of this track.

An RCA agent makes very different kinds of calls. Some are cheap — filtering a list,
extracting a timestamp, formatting an answer. Some are hard — reasoning over correlated
anomalies to decide which one caused the others. Paying the top model's price for the
cheap calls wastes money; using the cheapest model for the hard ones loses accuracy.

**Build a harness that routes each call to the model it needs**, so you keep accuracy
where it matters and spend little where it doesn't. You're scored on both — see
`docs/scoring.md`.

## The family

| Model | Context | $/M input | $/M output | Cost of a typical case |
|---|---|---|---|---|
| `zai-org/GLM-4.7-Flash` | 202K | 0.065 | 0.40 | $0.04 |
| `zai-org/GLM-5.3-Flash` | 262K | 0.15 | 0.50 | $0.09 |
| `zai-org/GLM-4.6` | 202K | 0.55 | 2.20 | $0.34 |
| `zai-org/GLM-4.7` | 202K | 0.55 | 2.20 | $0.34 |
| `zai-org/GLM-5` | 202K | 0.95 | 3.15 | $0.56 |
| `zai-org/GLM-5.1` | 202K | 1.30 | 4.30 | $0.76 |
| `zai-org/GLM-5.2` | 262K | 1.40 | 4.40 | $0.81 |

"A typical case" is about **474K input and 34K output tokens** — measured usage from
this kind of agent, if it ran every call on that one model. Yours will differ; that's
the point. On a typical case the top model costs about **18× the cheapest**.

- **Flash models** are the small, cheap end; **GLM-5.x** the large end.
- **GLM-4.5 onward are hybrid reasoning models**: thinking is a toggle on the same
  weights, not a different model. That makes it a clean dial — the weights stay fixed
  and only the reasoning budget moves.
- **Prices move.** Featherless publishes live per-model pricing at
  `https://api.featherless.ai/v1/models`, no key needed. Check before a long run.

## Calling it

The API is OpenAI-compatible, so the OpenAI SDK works unchanged. **Read the key and the
endpoint from the environment** — that's how we run your agent on our key when we
evaluate it (see `docs/submission.md`):

```python
import os
from openai import OpenAI

client = OpenAI(base_url=os.environ.get("FEATHERLESS_BASE_URL", "https://api.featherless.ai/v1"),
                api_key=os.environ["FEATHERLESS_API_KEY"])

def ask(model, messages):
    return client.chat.completions.create(model=model, messages=messages)

ask("zai-org/GLM-4.7-Flash", [...])   # cheap: triage, extraction, formatting
ask("zai-org/GLM-5.2",       [...])   # expensive: the reasoning that decides the answer
```

`starter/llm.py` wraps this and counts tokens per model; `starter/cost.py` turns the
counts into dollars at the table above; `starter/agents/routed.py` puts both to work.

## When a model is unavailable

In production, models can become temporarily unavailable but service should not stop.
Treat that as part of the problem, not an accident of the day.

Capacity errors come back with **HTTP 200**, not 503 — the status line says success and
the body carries the error:

```json
{"error": {"message": "This model is busy, please try again later.",
           "type": "server_error", "code": "completion_error"}}
```

There is no `choices` key in that response, so code that reaches straight for
`response.choices[0].message.content` raises an exception instead of seeing the error.

What a resilient agent does:

- **Check for `error` before reading `choices`.** A 200 is not a success.
- **Retry the same model a few times, with a growing pause.** Most capacity errors clear
  on their own, and a failed call returns no `usage` — so retries cost you nothing.
- **Then fall back to another model in the family.** Name a second choice for each tier,
  a cheap one and a strong one, rather than routing every call of a kind to a single
  point of failure.
- **Stop retrying a model that stays down.** Retries cost nothing in dollars — a failed
  call carries no `usage` — but they spend the case's ten-minute clock, and an
  unavailable model is usually unavailable for minutes. Rediscovering that on every
  call is how a run times out while billing nothing. Drop a model after a couple of
  failures and stop offering it.
- **Degrade, don't die.** A case that cannot reach its model should still write an answer
  and an evidence file saying what happened. One unavailable model must not end a run.

`starter/llm.py` does the retry, the fallback and the giving-up for you — `ask()` takes a
list of models and walks down it, and drops one that has failed twice. Read it before you trust it; the policy it picks is a starting point,
not the only sensible one.

Availability moves. Check before a long run, and don't assume the model you developed
against is the one serving you an hour later.

## How cost is measured

**In dollars, not tokens.** An input token on GLM-5.2 costs about 21× one on Flash
(an output token, 11×), so token counts across models aren't comparable. We take your per-model usage from
Featherless's own accounting and price it at the table above. There's nothing for you
to instrument or report.

Two numbers, always read alongside accuracy:

- **Dollars per case** — the main one.
- **Dollars per correct answer** — the one that really matters, but with few correct
  answers one lucky case swings it a lot, so it's reported rather than ranked on.

An agent that answers nothing costs almost nothing and scores zero. Cheap is only good
if it's also right.

## Limits

| | |
|---|---|
| **Cost per case** | **$3**, priced as above |
| **Time per case** | 10 minutes |
| **Exceeding either** | that case scores zero; the run continues |
| **Cost per run** | **$25** for the 20 judged cases, priced as above |
| **Time per run** | **20 minutes** for all 20 cases |
| **Exceeding either** | the run stops where it is; the cases not yet reached score zero |

$25 over 20 cases is **$1.25 per case on average** — more than an agent that runs every
call on GLM-5.2 spends on a typical case (about $0.81), so it only binds an agent that is
heavy across the board. The cases run in a fixed order, the same for every team.

**Twenty minutes is one minute a case, and it is the limit most likely to bind.** It is
not there to stop runaway loops — the per-case limits do that — it is there because every
submission is judged in one sitting and the sitting is an hour. Budget for it: an agent
averaging three minutes a case finishes seven of twenty and scores zero on the rest, however
good those seven are. `run.py` writes `predictions.csv` after every case, so whatever you
finished before the limit still counts.

We enforce all of these from outside your agent, so you can't change them; give your agent
its own stop well below them, so a loop costs you nothing worse than a weaker answer.

## Your budget

Each person gets a Featherless key with **$25 of credit** — about **$125 for a team of
five**. **None of it is spent on judging**: we evaluate your agent on our own key. It's
all yours to build with.

That's a lot of room at the cheap end: running a typical case on Flash alone costs about
four cents. **Spend across the family, not up it.** Do most of your development on the
cheap models, then measure what the expensive ones actually buy. If the top model costs
18× more and doesn't buy 18× anything, that's a finding — and exactly the kind this
event exists to surface.

## Why only GLM

Token counts and quality across unrelated model families aren't comparable —
different tokenizers, prices and strengths. If your comparison pits a Qwen against a
Mistral against a GLM, it's a model-shopping report, and what we're grading is **your
harness**. Holding the family fixed keeps every result attributable to a decision you
made. Featherless serves thousands of models, some tuned for observability; finding one
of those would be model selection doing the work, not agent design.
