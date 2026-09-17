# ORIGIN — Track 1 — Root Cause Analysis

**When one component in a cloud system fails, everything downstream of it also
looks broken — usually louder than the thing that broke.** ORIGIN separates the
cause from its symptoms: a deterministic engine ranks candidates and then demotes
any component whose *own dependencies* went wrong first. A language model is
called only where that ranking is genuinely ambiguous, and it is never allowed to
write the answer — it picks a candidate ID and a reason from a fixed list, and
code fills in every name, number and timestamp from the data.

The published state of the art on this benchmark solves about one case in nine.

## Pipeline

```
0 parse case      instruction -> window (UTC+8), failure count, fields asked
1 load window     only the window + a 60-min baseline; metrics, trace edges, error logs
2 anomalies       robust z vs baseline median/IQR, sustained over k samples -> onsets
3 candidates      group signals by component, rank, CAUSAL FILTER, legal reasons
4 route           gate (no model) -> GLM-4.7-Flash -> GLM-5.2 on escalation
5 validate        candidate id + legal reason -> answer; code writes every number
6 render          prediction (exact key order) + grounded evidence markdown
```

Only stage 4 involves a model.

## Results

Holdout (21 cases, split by `row_id` before any tuning, never tuned on):

| config | mean score | fully solved |
|---|---|---|
| `heuristic` (starter baseline, no model) | 0.111 | 1/21 |
| `engine` (ours, no model) | **0.512** | **7/21** |

Judged configuration, in Docker at 2 CPU / 8 GB: **20 cases in 5 min 54 s**
(17.6 s/case), peak **1.74 GiB**, **$0.126** for the run.

Full tables, the routed-vs-single-model comparison, the failure taxonomy and the
calibration result are in **[REPORT.md](REPORT.md)**, generated from the
committed CSVs in `eval/results/` by `python -m eval.summarize`.

## How to run

```bash
pip install -r requirements.txt
make data                                    # 1.3 GB zip -> ~12 GB in data/
export FEATHERLESS_API_KEY=...               # without it, ORIGIN runs engine-only

make validate                                # 2 cases, checks the output shape
make dev && make score                       # all 70 dev cases, then score them
make docker                                  # build and run exactly as judges do

python -m eval.run_eval --config routed --split holdout
python -m eval.summarize                     # regenerate every table in REPORT.md
```

`python run.py --dataset <dir> --queries <query.csv> --out <dir>` is the judged
entry point; its command line is unchanged from the starter.

## AI disclosure

**Models the product calls.** Only the GLM family via Featherless AI
(`FEATHERLESS_BASE_URL`, key from `FEATHERLESS_API_KEY`). No other network access
at runtime, no runtime installs.

| Tier | Models (preference order) | Used for |
|---|---|---|
| none | — | clear cases: the engine answers alone (the confidence gate) |
| cheap | `zai-org/GLM-4.7-Flash` → `zai-org/GLM-5.3-Flash` | the routine pick over the candidate list |
| strong | `zai-org/GLM-5.2` → `zai-org/GLM-5.1` | escalated cases (low margin, thin support, multi-failure) |

**Agent frameworks: none.** Plain Python on the OpenAI SDK through the starter's
`llm.py`. No LangChain, no tool-calling loop. Dependencies are `pandas`, `numpy`,
`openai`, pinned to the versions we tested.

**Coding assistants.** Both of us used Claude Code (Claude Opus 5) heavily. Every
AI-written line was read and edited by a human before commit, and we are
responsible for all of it. Per-module provenance — which files an assistant
drafted and which we typed — is in [`docs/ai-use.md`](docs/ai-use.md).

## Attribution, and the one starter file we changed

Starter files (`run.py`, `score.py`, `cost.py`, `llm.py`, `agents/heuristic.py`,
`agents/routed.py`, `Dockerfile`, `Makefile`) are MantisGrid's — see
[`LICENSE-MANTISGRID`](LICENSE-MANTISGRID). `score.py` vendors OpenRCA's own
evaluator **unchanged**. Telemetry is OpenRCA-derived, CC BY-NC 4.0, and is **not
included** in this repository — see [`ATTRIBUTION.md`](ATTRIBUTION.md).

Two edits to the starter, both disclosed:

1. **`run.py`** — its default `--agent` is now `agents.origin`. The command line
   is otherwise untouched.
2. **`llm.py`** — `_once()` now falls back to `message.reasoning` when
   `message.content` is blank. Featherless returns the answer there on **both
   Flash models** (measured 4/4 calls, [`docs/model-findings.md`](docs/model-findings.md) §3),
   so the unpatched client returns `""` on **every `GLM-4.7-Flash` call while
   still being billed**. The patch sits after the token accounting and changes
   only which field the text is read from — counts, prices, retries and the
   circuit breaker are byte-identical, so it cannot flatter our cost numbers.
   Anyone using the starter `llm.py` with a Flash model is silently getting empty
   answers.
