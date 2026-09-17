# AI use log (ORIGIN)

Running log for the README's AI-disclosure section. Updated as we go; Person 2 owns it.
Last updated: 2026-09-17, Phase 1.

## Models the product uses

The submitted agent calls **only the GLM family via Featherless AI**
(`FEATHERLESS_BASE_URL`, key from `FEATHERLESS_API_KEY`) — no other network
access at judged runtime, no runtime installs.

| Tier | Models (preference order) | Used for |
|---|---|---|
| cheap | `zai-org/GLM-4.7-Flash` → `zai-org/GLM-5.3-Flash` | the routine pick over the engine's candidate list |
| strong | `zai-org/GLM-5.2` → `zai-org/GLM-5.1` | escalated cases (low margin / thin support / multi-failure) |
| none | — | clear cases answered by the deterministic engine alone (the confidence gate) |

Tiers are set in `origin/config.py` below `# --- PERSON 2 ---` and are finalised
at Checkpoint 1 from the measurements in `docs/model-findings.md`.

## Agent frameworks

**None.** The agent is plain Python on the OpenAI SDK through the starter's
`llm.py` wrapper (retries, model fallback, per-model token accounting). No
LangChain, no agent framework, no tool-calling loop. Dependencies stay
`pandas`, `numpy`, `openai`.

## Coding assistants used to build it

| Person | Assistant | What it was used for |
|---|---|---|
| Person 1 | _(fill in)_ | data loading, signals, candidate engine |
| Person 2 | Claude Code (Claude Opus 5) | agent entry point, routing, eval harness, docs |

All AI-generated code was read and edited by a human before commit; the team is
responsible for every line.

## Module provenance

Filled in as modules land. "AI-generated" means an assistant wrote the first
draft; "team-written" means a human typed it.

| Module | Owner | Origin |
|---|---|---|
| `run.py`, `llm.py`, `cost.py`, `score.py`, `agents/heuristic.py`, `agents/routed.py`, `scripts/validate_submission.py` | — | **MantisGrid starter, unmodified** (see `ATTRIBUTION.md`; `run.py`'s default `--agent` is the one edit) |
| `origin/contract.py`, `origin/config.py` | P1 | team-written (typed from PLAN.md §1–§3) |
| `origin/case.py`, `origin/timeslice.py`, `origin/load.py`, `origin/signals.py`, `origin/candidates.py`, `origin/facts.py`, `origin/engine.py` | P1 | _(fill in)_ |
| `origin/anomaly.py` | P2 | AI-generated from the PLAN pseudocode, human-reviewed |
| `origin/fixture.py`, `origin/router.py`, `origin/validate.py`, `origin/evidence.py` | P2 | _(fill in)_ |
| `agents/origin.py` | P2 | _(fill in)_ |
| `eval/split.py` | P2 | AI-generated, human-reviewed |
| `eval/run_eval.py`, `eval/summarize.py` | P2 | _(fill in)_ |
| `REPORT.md`, `README.md`, `docs/model-findings.md`, `docs/ai-use.md` | P2 | AI-drafted from measured numbers, human-edited |

## Data

`Market-cloudbed-1` from the MantisGrid hackathon bundle (OpenRCA lineage),
CC BY-NC 4.0 — see `ATTRIBUTION.md`. Not committed. No data is sent to any model
except the small, explicitly-built fact sheet in the prompt.
