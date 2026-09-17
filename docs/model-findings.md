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

_Pending — needs `FEATHERLESS_API_KEY` (see "Blocked" below)._

Method: one call per model with a ~3 K-token synthetic fact sheet (34 facts,
5 candidates, the legal-reason list) asking for
`{"answers":[{"candidate":"C1","reason":"..."}],"confidence":"...","why":"..."}`,
`temperature=0`, `max_tokens=700`, `timeout=120`.

| Model | wall s | prompt tok | completion tok | JSON parsed | `<think>` in body | `reasoning_content` |
|---|---|---|---|---|---|---|
| `zai-org/GLM-4.7-Flash` | | | | | | |
| `zai-org/GLM-5.3-Flash` | | | | | | |
| `zai-org/GLM-5.2` | | | | | | |
| `zai-org/GLM-5.1` | | | | | | |

## 3. Thinking toggle

_Pending — same blocker._

Two candidate switches, each passed as `extra_body`:

1. `{"chat_template_kwargs": {"enable_thinking": false}}`
2. `{"thinking": {"type": "disabled"}}`

| Model | variant | wall s | completion tok | JSON parsed |
|---|---|---|---|---|
| `zai-org/GLM-5.2` | default | | | |
| `zai-org/GLM-5.2` | chat_template_kwargs | | | |
| `zai-org/GLM-5.2` | thinking disabled | | | |
| `zai-org/GLM-4.7-Flash` | default | | | |
| `zai-org/GLM-4.7-Flash` | chat_template_kwargs | | | |
| `zai-org/GLM-4.7-Flash` | thinking disabled | | | |

**Switch we adopt:** _TBD — whichever measurably cuts completion tokens and seconds._

`llm.py` already strips `<think>…</think>` from the body. If the reply instead
carries a separate `reasoning_content` field, those tokens are still billed as
completion tokens even though `llm.py` never shows them — which is exactly why
the toggle matters for both latency and cost.

## 4. Capacity errors seen

_Pending._ (HTTP 200 with an `error` body and no `choices`; `llm.py` raises
`ModelUnavailable` and walks its model list.)

## 5. Heuristic baseline

_Pending — needs the dataset (downloading)._

`make dev AGENT=agents.heuristic OUT=out/heuristic && make score OUT=out/heuristic`,
free, all 70 dev cases. Expected ≈ **0.073** mean.

| Run | cases | mean score | wall total |
|---|---|---|---|
| `agents.heuristic` (dev, 70) | | | |

## Blocked / next steps

- **Need the Featherless API key from the human** to fill §2–§4. Put it in `.env`
  (gitignored) *and* `export FEATHERLESS_API_KEY=...` in the shell — `llm.py`
  reads the environment, not `.env`. The spike script is written and ready.
- Dataset (1.3 GB → ~12 GB) is downloading; §5 and the split counts land when it finishes.
