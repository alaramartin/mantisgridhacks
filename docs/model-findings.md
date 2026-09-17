# Featherless / GLM findings

Person 2, Phase 1 spike. Measured, not assumed. Re-check before any long run —
availability and prices move (`docs/models.md`).

## 1. Which models are up

`GET https://api.featherless.ai/v1/models` (no key needed), 2026-09-17 ~10:10,
filtered to `zai-org/*`: **21,961 models listed, 17 of them `zai-org`.**

**All 7 models from the `docs/models.md` table are listed**, plus one the table
does not mention:

| Model | Context | max_completion | $/M in (live) | $/M out (live) | $/M in (docs) | $/M out (docs) | tool_use |
|---|---|---|---|---|---|---|---|
| `zai-org/GLM-4.7-Flash` | 202,752 | 32,768 | **0.06525** | 0.40 | 0.065 | 0.40 | yes |
| `zai-org/GLM-5.3-Flash` | 262,144 | 32,768 | 0.15 | 0.50 | 0.15 | 0.50 | yes (+image in) |
| `zai-org/GLM-4.6` | 202,752 | 32,768 | 0.55 | 2.20 | 0.55 | 2.20 | yes |
| `zai-org/GLM-4.7` | 202,752 | — | 0.55 | 2.20 | 0.55 | 2.20 | yes |
| `zai-org/GLM-5` | 202,752 | — | 0.95 | 3.15 | 0.95 | 3.15 | yes |
| `zai-org/GLM-5.1` | 202,752 | — | 1.30 | 4.30 | 1.30 | 4.30 | yes |
| `zai-org/GLM-5.2` | 262,144 | — | 1.40 | 4.40 | 1.40 | 4.40 | yes |
| `zai-org/GLM-5.3` ⚠️ | 262,144 | 32,768 | 1.40 | 4.40 | **not in the table** | | yes |

Live prices match `docs/models.md` everywhere (GLM-4.7-Flash is 0.06525 vs the
table's 0.065 — a 0.4 % difference, ignore).

⚠️ **`zai-org/GLM-5.3` exists on the endpoint but is not in `docs/models.md`'s
family table and is not in `cost.py`'s `PRICES`.** `cost.py` raises `KeyError`
on any model it has no price for, so **the agent must not call GLM-5.3** — it
would break the judged cost accounting. Cheap tier uses `GLM-5.3-Flash`, which
*is* priced. (Decide at CP1 whether to raise this with the organisers; the safe
default is to stay inside the 7 priced models.)

Other `zai-org` entries (ignore — not GLM chat family): `GLM-4-32B-0414`,
`GLM-4-32B-Base-0414`, `GLM-Z1-32B-0414`, `GLM-4-9B-0414`, `agentlm-7b`,
`agentlm-13b`, `BPO`, `webrl-llama-3.1-8b`, `webrl-orm-llama-3.1-8b`.

## 2. Latency / tokens / JSON reliability

Method: one call per model with a ~2.7 K-token synthetic fact sheet (34 facts,
5 candidates, the legal-reason list) asking for
`{"answers":[{"candidate":"C1","reason":"..."}],"confidence":"...","why":"..."}`,
`temperature=0`, `max_tokens=1200`, `timeout=180`. Featherless counts the prompt at
~4,250 tokens. Measured 2026-09-17 ~10:25.

### Thinking ON (default) — all four models are unusable

| Model | wall s | prompt tok | completion tok | finish_reason | JSON parsed |
|---|---|---|---|---|---|
| `zai-org/GLM-4.7-Flash` | 27.4 | 4,244 | **1,200 (capped)** | `length` | no |
| `zai-org/GLM-5.3-Flash` | 22.5 | 4,251 | **1,200 (capped)** | `length` | no |
| `zai-org/GLM-5.2` | 22.4 | 4,251 | **1,200 (capped)** | `length` | no |
| `zai-org/GLM-5.1` | 19.9 | 4,244 | **1,200 (capped)** | `length` | no |

**Every model ran out of output tokens before finishing the JSON.** They are not so
much slow as verbose: they narrate the whole chain of thought first. At a 700-token
cap (first pass) the same thing happened. Thinking-on is not a budget question for
us — it does not produce a parseable answer at any cap we can afford.

### Thinking OFF (`chat_template_kwargs.enable_thinking = false`)

| Model | wall s | completion tok | finish | JSON reliability (4 calls) |
|---|---|---|---|---|
| `zai-org/GLM-4.7-Flash` | 2.4 – 3.7 | 82 – 95 | `stop` | **4/4** |
| `zai-org/GLM-5.3-Flash` | 3.0 – 16.1 | 207 – 530 | `stop` | **2/4** (worst) |
| `zai-org/GLM-5.2` | 1.5 – 17.2 | 43 – 52 | `stop` | **4/4** |
| `zai-org/GLM-5.1` | 1.6 – 1.8 | 72 – 82 | `stop` | **4/4** |

Overall **14/20 calls parsed**; every failure was either thinking-on truncation or
GLM-5.3-Flash. The occasional 16–17 s outliers on 5.3-Flash and 5.2 are queueing,
not generation — the token counts are unchanged.

**Conclusions:**

1. **Always send the thinking-off switch.** Non-negotiable, on every tier.
2. **GLM-5.3-Flash is the least reliable model here** — it keeps narrating even with
   thinking off (207–530 completion tokens vs 4.7-Flash's ~90) and failed 1 of 4
   parses by rambling past the JSON. Cheap tier = **`GLM-4.7-Flash` first**, with
   5.3-Flash only as the availability fallback.
3. **GLM-5.2 with thinking off easily fits the 25 s budget** (1.5–17 s, ~45 output
   tokens). The CP1 question "does GLM-5.2 fit?" answers **yes — with thinking off**.
   With thinking on it neither fits nor parses. **GLM-5.1 is the strong fallback**,
   and was the fastest model measured (1.6–1.8 s, 4/4 parses).

## 3. The thinking toggle — which switch actually works

| `extra_body` | Effect |
|---|---|
| `{"chat_template_kwargs": {"enable_thinking": false}}` | **This is the switch.** GLM-4.7-Flash 1,200 -> 95 tok and 27.4 s -> 2.5 s; GLM-5.2 1,200 -> 45 tok and 22.4 s -> ~4 s; GLM-5.1 1,200 -> 75 tok and 19.9 s -> 1.6 s. |
| `{"thinking": {"type": "disabled"}}` | **Silently ignored.** GLM-4.7-Flash still 16.3 s at the 700-token cap; GLM-5.2 still 12.5 s at the cap. Do not use. |

So, on every call:

```python
llm.ask(model, prompt, max_tokens=..., temperature=0, timeout=...,
        extra_body={"chat_template_kwargs": {"enable_thinking": False}})
```

### Featherless puts the answer in `message.reasoning`, and `llm.py` drops it

Printing the raw message object (PLAN asked for this) turned up the biggest finding
of the spike:

```
model_dump: {"content": "", "role": "assistant", ...,
             "reasoning": "```json\n{\n  \"answers\": [{\"candidate\": \"C1\", ...}]}\n```"}
```

- The field is **`reasoning`** — *not* `reasoning_content`, and *not* `<think>` tags.
  `getattr(msg, "reasoning_content", None)` is `None` on every model, and there are
  zero `<think>` markers in any reply.
- When `reasoning` is populated, **`content` is the empty string.**
- Which field carries the answer **varies by model**, even at `temperature=0`:

| Model (thinking off) | answer arrived in |
|---|---|
| `zai-org/GLM-4.7-Flash` | `reasoning` (4/4 calls) |
| `zai-org/GLM-5.3-Flash` | `reasoning` (4/4) |
| `zai-org/GLM-5.2` | `content` (4/4) |
| `zai-org/GLM-5.1` | `content` (4/4) |

**`llm.py` reads only `r.choices[0].message.content` and strips `<think>`.** Against
GLM-4.7-Flash — our cheap tier, the model that will run on most cases — it therefore
returns **`""` on every call**, so the agent silently sees an empty answer and falls
back, while still being billed for the tokens. This is not hypothetical: it is what
both Flash models did in every measurement above.

**Action (Person 2, Phase 2):** patch `llm.py`'s `_once()` to fall back to
`message.reasoning`, then `message.reasoning_content`, when `content` is blank, and
keep the `<think>` strip. This is the only starter file we change beyond `run.py`'s
default `--agent`; note it in `README.md` and `ATTRIBUTION.md`. Worth raising at the
merge and with the organisers — anyone using the starter `llm.py` with a Flash model
is silently getting empty strings.

## 4. Capacity errors seen

**None.** 20 spike calls across the four models, 2026-09-17 10:20–10:30: no HTTP 200
`error` bodies, no timeouts, no `ModelUnavailable`. That is a quiet-morning reading,
not a guarantee — `llm.py`'s retry / fallback / breaker policy stays exactly as it
is, and each tier keeps a named second choice.

## 5. Heuristic baseline

```
python run.py --dataset data/Market-cloudbed-1 \
  --queries data/Market-cloudbed-1/dev/query_dev.csv --out out/heuristic --agent agents.heuristic
python score.py --predictions out/heuristic/predictions.csv --queries data/Market-cloudbed-1/dev/query_dev.csv
```

Free (0 tokens), all 70 dev cases.

| Run | cases | mean score | fully solved | wall |
|---|---|---|---|---|
| `agents.heuristic` (dev, 70) | 70 | **0.073** | 2 / 70 (2.9 %) | 1.5 min total, mean 1.3 s/case |

Matches the 0.073 the brief predicts, so the harness is wired up correctly.

By difficulty: easy 0.083 (30), middle 0.060 (29), hard 0.075 (11).

By task: task_1 0.125, task_2 0.100, **task_3 0.000**, task_4 0.107,
**task_5 0.000**, task_6 0.083, task_7 0.075.

**task_3 and task_5 score a flat zero** — the baseline never gets one of those right.
Worth Person 1 and me checking at CP1 what those two task types ask for that the
others do not. They are 18 of the 70 dev cases and, at 3 apiece, 6 of the 21 holdout
cases.

## 6. Holdout split

`python eval/split.py` -> committed to `eval/splits/`.

| | cases |
|---|---|
| holdout | **21** (3 per `task_index` x 7) |
| dev_tune | **49** |

Every task has at least 7 cases, so all seven give exactly 3 to holdout:
task_1 12 -> 3/9, task_2 10 -> 3/7, task_3 8 -> 3/5, task_4 7 -> 3/4,
task_5 10 -> 3/7, task_6 12 -> 3/9, task_7 11 -> 3/8.

Rule (also in `split.json`, so it is re-derivable): per `task_index`, sort that
task's `row_id`s by `md5(str(row_id)).hexdigest()` and take the first 3.
**Nothing is run on the holdout until CP4.**

Covered by `tests/test_split.py` (5 tests): 3-per-task, disjoint, complete,
order-independent, small-task safe, and the committed files still agree with
`query_dev.csv`. Re-running `eval/split.py` is byte-identical.

## 7. Why the heuristic scores 0.000 on task_3 and task_5

Measured on dev_tune only (the holdout stays closed): **the heuristic gets the
component right in 1 of 29 cases** that ask for one — task_3 0/5, task_5 0/7,
task_6 0/9, task_7 1/8.

That single weakness explains the whole per-task table. task_3's only scoring
point is the component, and task_5's two points are the component and a datetime
within 1 minute, so both collect nothing. The tasks that score above zero are the
ones with a datetime point the heuristic can occasionally land (task_1, 0.125).

So it is not two odd task types — it is one weakness showing through wherever it
is not masked: **the baseline can roughly tell when something went wrong, but not
what broke.** Picking the right component out of the cascade is exactly what the
candidate engine and the routing are for, which is a good sign for the design.

## 8. What has and has not been verified

| Check | Result |
|---|---|
| `python -m pytest -q` | 5 passed (`tests/test_split.py`) |
| `scripts/validate_submission.py` (official shape checker) | **valid, 0 warnings** — run.py ran 2 cases, predictions.csv has row_id + prediction, one evidence .md per case |
| `python cost.py out/heuristic/usage.jsonl` | 70 cases, $0.0000 (heuristic uses no models) |
| `eval/split.py` re-run | byte-identical output |
| `.env` gitignored + dockerignored, key absent from every commit | confirmed |
| `make docker` | **NOT RUN — Docker is not installed on this machine.** See the PLAN blocker task. |
| `origin/anomaly.py`, router, agent, evidence | do not exist yet (Phase 2) |
