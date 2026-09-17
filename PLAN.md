# ORIGIN — PLAN.md (v2, after check-in)

MantisGrid AI Hackathon · **Track 1 — Root Cause Analysis** · Sep 17, 2026
Build 10:00 · Freeze 2:15 · Record 2:15–2:40 · Submit by 2:50 · **Form closes 3:00pm PDT**
Repo: https://github.com/alaramartin/mantisgridhacks

`SPEC.md` (v6.0) says **what** and **why**. This file says **how**, **who** and
**when**. The official docs in `docs/` beat both. If SPEC and PLAN disagree:
SPEC wins on product, claims and priorities; PLAN wins on file names, function
signatures and data shapes.

v1 of this plan (Claude agent, Streamlit, OTel graph) is **dead**. Do not
build anything from it.

---

## READ THIS FIRST

You are a coding agent (Claude Code / Cursor). Your human will tell you **"I'm
Person 1"** or **"I'm Person 2"**. Read **READ THIS FIRST**, **PRIORITIES**,
**NON-NEGOTIABLE RULES**, **WHAT'S ALREADY IN THE REPO**, **REPO LAYOUT** and
**SHARED CONTRACT** (everyone builds against those), then jump to your person's
section and do only that section, top to bottom. You do not need to read the
other person's section. Before writing code that touches data, models or
output, also read the official doc it depends on: `docs/data.md`,
`docs/models.md`, `docs/scoring.md`, `docs/submission.md`.

**THE GOLDEN RULE — stop at every 🛑 CHECKPOINT.** Do not keep coding past a
checkpoint. Instead, print the checkpoint's instructions to your human (who to
merge with, exact commands, expected output), then wait for the human to say it
passed before starting the next phase. Checkpoints are how two people stay in
sync. Blowing past one breaks integration.

**⏱ GATES are solo checkpoints.** No merge. Stop, print the gate block to your
human, and take the listed branch (continue / fall back) once they answer.

When the human confirms the work up to a checkpoint is sound, **record it in
this PLAN.md** — tick the boxes, add your notes, and update any part of the
plan that changed. This is so the human can `/clear` the chat and resume from
where they left off.

**Commit after every completed task**, not just at checkpoints. One task, one
commit, conventional message (`feat(load): byte-offset window reader`). Small
commits from both GitHub accounts. **Never squash.**

**Task bookkeeping.** Each task is a `- [ ]` checkbox. When you finish it,
change it to `- [x]` and write a one-line note underneath saying how it went —
`done`, or `changed X because Y`, or `blocked on Z`. Be honest about
deviations; the other person reads this file. Only edit your own person's
section. The CHECKPOINT LOG is edited only on `main`, by whoever runs the merge.

**Branches.** Person 1 works on `person1`, Person 2 works on `person2`. Merge
both into `main` at each checkpoint (procedure below). Never commit directly to
`main` outside a checkpoint — the one exception is Person 1 pushing the
existing bootstrap commit and `origin/contract.py` + `origin/config.py` in Phase 1.

**Hardcoding.** Avoid hardcoding values unless absolutely necessary (i.e.
something is required of another person and for the meantime, you use
hardcoded values). If there is anything required of the human (like API keys,
links, etc) tell them. If anything is hardcoded/temporary/placeholder, make
that clear to the human and tell us next steps for how to get the real values.
Mark placeholders in code with `# PLACEHOLDER:` so
`grep -rn PLACEHOLDER origin agents eval` finds them all. **Special rule for
this track: never hardcode a component name (`shippingservice-1`, `node-5`, …)
or anything read from the dev answers into the agent.** Judges run a different
deployment with different component names, and more than once, to catch
exactly that.

**The clock is part of the task.** Every phase has a hard stop from the SPEC
clock. If a phase isn't done at its hard stop, stop, tell your human what's
missing, and take that phase's fallback. Never silently spend past a hard stop.

**Priorities decide what to skip.** Anything tagged **STRETCH** is built only
after Checkpoint 4 passes, and only if the human says so.

### Merge procedure (used at every 🛑 CHECKPOINT)

Both people push their branch first. Person 1's human runs the merge; Person 2
pulls afterwards.

```sh
# both people, on their own branch
git add -A && git commit -m "chore: checkpoint N" ; git push origin HEAD

# Person 1's machine
git checkout main && git pull
git merge --no-ff origin/person1 -m "merge: person1 at checkpoint N"
git merge --no-ff origin/person2 -m "merge: person2 at checkpoint N"
python -m pytest -q
# ...run the checkpoint's smoke commands...
git push origin main

# then BOTH people
git checkout person1   # or person2
git merge main && git push
```

Conflict rules: `origin/config.py` → keep both sections (Person 2 only appends
below `# --- PERSON 2 ---`). `PLAN.md` → keep both sides. `requirements.txt` →
keep both sides' lines. Anything else means someone edited a file they don't
own — stop and ask the humans.

---

## PRIORITIES — copied from SPEC, do not reorder

| # | Must-have | Owner | Must work at |
|---|-----------|-------|--------------|
| 1 | **Valid, judgeable submission**: root Dockerfile, `run.py` CLI unchanged, our agent as default, exact failure count, key order, one evidence file per case, `make validate` + `make docker` pass at 2 CPU / 8 GB | P2 | 🛑 CP3 (validate), 🛑 CP4 (docker, 20 cases < 20 min) |
| 2 | **Fast, correct window loading**: UTC+8, seconds vs milliseconds, only the window + baseline read | P1 | ⏱ 11:00, 🛑 CP2 |
| 3 | **Deterministic candidate engine**: robust z + onset, trace edges for network faults, topology from names, causal filter, legal reasons | P1 (P2 writes `score_series`) | 🛑 CP3 |
| 4 | **Grounded evidence for every case**: every number copied from raw rows with file / cmdb_id / KPI / epoch ts; grounding check on model prose | P1 facts, P2 assembly | 🛑 CP3 |
| 5 | **Routing across GLM**: gate → Flash → GLM-5.2 on escalation, fallback per tier, deadline guard | P2 | 🛑 CP3 |
| 6 | **Eval**: routed vs single model (+ engine, heuristic) on the holdout, $/case, s/case, variance, failure taxonomy, calibration; `REPORT.md` + `eval/` committed | P2 | 🛑 CP4 |
| 7 | **~4-min presentation**: live case, evidence file + grep, eval table | both | 2:40 |

**Always emit a best guess; doubt goes in the evidence.** Blank and wrong both score zero.

**If nothing works:** starter heuristic + our loader + UTC+8 fix + grounded
evidence + eval table, reported honestly.

**Cut order if behind (first goes first):** `log_service` signal →
`metric_service` signal → repeats beyond 2 → `starter-routed` row → model prose in
evidence → node promotion in the causal filter → `single-flash` row → trace edges
(say "blind to network faults") → the confidence gate.

---

## NON-NEGOTIABLE RULES

1. **Models never write timestamps, numbers, component names outside the
   candidate list, or reasons outside the legal list.** They pick candidate IDs
   and legal reasons; code fills the rest.
2. **Every number in `## Evidence` is copied from raw rows**, with the file,
   `cmdb_id`, KPI and epoch timestamp, so a judge can grep it. Derived numbers
   (medians, scores) say what they are ("median of 60 samples").
3. **Exact count, key order, exact strings.** Always build predictions with
   `run.format_prediction()`, and only include the fields the case asks for.
4. **Times are UTC+8** in answers and evidence (with epoch seconds beside them).
   Traces are in milliseconds, everything else in seconds; convert once, at load.
5. **Never read a whole `trace_span.csv` or `log_proxy.csv`** into memory. 2 CPU,
   8 GB; the judged run has 60 s per case on average.
6. **Only `FEATHERLESS_BASE_URL`**, key from `FEATHERLESS_API_KEY`. No other
   network (so no MCP inside the judged agent; our MCP server is a separate STRETCH entry point). No runtime installs. Read only `--dataset`, write only `--out`.
7. **Holdout discipline.** Nothing is tuned on the 21 holdout cases. Parameters
   and the reason table change only from dev-tune results, and every change is
   logged in `REPORT.md` → "Tuning log".
8. **Never present a fallback or engine-only run as the model deciding.**
9. **Secrets:** `.env` is gitignored and dockerignored. Never print a key.
10. **Keep `run.py`'s command line.** The only edit to `run.py` is its default `--agent`.

---

## WHAT'S ALREADY IN THE REPO (done by the planner at 9:45)

The Track 1 starter from https://github.com/MantisGridAI/hackathon-2026-official
was copied **flat into the repo root** (no subfolder). Track 2 was left out on
purpose, because its Dockerfile would make the root one ambiguous.

| Path | What | Owner from now |
|---|---|---|
| `run.py` | Starter entry point: `solve(instruction, dataset_dir, ctx) -> Solution`, `format_prediction()`; writes predictions / evidence / usage.jsonl after every case | P2 (default `--agent` only) |
| `llm.py` | Featherless client (OpenAI SDK), per-model usage, retries, fallback list, breaker; strips `<think>` | P2 (read-only unless needed) |
| `cost.py` | Prices usage at the GLM table; `dollars(models)` | P2 (read-only) |
| `score.py` | OpenRCA's evaluator, vendored unchanged; `--report per_case.csv` | nobody edits |
| `agents/heuristic.py` | Free baseline (0.073). **Its window parser treats times as UTC, not UTC+8** — do not copy that part | nobody edits (baseline) |
| `agents/routed.py` | Starter routing example; `RCA_MODEL` pins one model | nobody edits (baseline) |
| `Dockerfile`, `requirements.txt`, `.dockerignore` | `python:3.12-slim`, `COPY . .`; `.dockerignore` now excludes `data/`, `out/`, `.env`, `.git`, `docs/`, `eval/results/` | P2 |
| `Makefile` | Adapted to the root layout: `make data / validate / dev / score / cost / docker`; `OUT=` picks the output dir; `docker` adds `--cpus 2 --memory 8g` | P2 |
| `scripts/validate_submission.py` | Official shape checker | nobody edits |
| `docs/` | Official: `BRIEF.md` (track-1 README), `GET_DATA.md`, `data.md`, `models.md`, `scoring.md`, `submission.md`, `STARTER_README.md`, `PARTICIPANT_AGREEMENT.md` | read-only |
| `ATTRIBUTION.md`, `LICENSE-MANTISGRID` | Data (CC BY-NC 4.0) and starter licence — starter code is MantisGrid's, usable for the hackathon | read-only |
| `.gitignore`, `.env.example` | `data/`, `out/`, `.env`, caches ignored | P1 |

A local git repo exists with one commit on `main` and remote `origin` set to
`https://github.com/alaramartin/mantisgridhacks.git` (not pushed yet).

---

## REPO LAYOUT (target)

```
mantisgridhacks/                     (repo root = the submission)
├── Dockerfile  run.py  llm.py  cost.py  score.py  requirements.txt  Makefile      starter (see above)
├── README.md                        P2  what / how to run / AI disclosure / attribution
├── mcp_server.py                    P1  STRETCH #1 only: FastMCP server over the engine (never imported by the agent)
├── REPORT.md                        P2  eval write-up (P1 contributes engine + tuning sections)
├── agents/
│   ├── heuristic.py  routed.py      starter baselines, untouched
│   └── origin.py                    P2  solve(): budget, gate, router, validate, evidence
├── origin/
│   ├── __init__.py                  P1
│   ├── contract.py                  P1  dataclasses + constants shared by everyone
│   ├── config.py                    P1  fixed params + reason table (P2 appends model tiers)
│   ├── case.py                      P1  parse_instruction()
│   ├── timeslice.py                 P1  byte-offset window reads
│   ├── load.py                      P1  load_window() -> Window
│   ├── anomaly.py                   P2  score_series()
│   ├── signals.py                   P1  metric / edge / disappearance signals
│   ├── candidates.py                P1  ranking, causal filter, reasons, engine answers
│   ├── facts.py                     P1  render_fact(), render_ruled_out()
│   ├── engine.py                    P1  analyze() -> Analysis
│   ├── query.py                     P1  STRETCH: get_series / get_edge (MCP server + strong-model query tools)
│   ├── fixture.py                   P2  a hand-built Analysis for router development
│   ├── router.py                    P2  fact sheet, prompts, model calls, parsing
│   ├── validate.py                  P2  legality, count, time, confidence
│   └── evidence.py                  P2  assemble the evidence markdown + grounding check
├── eval/
│   ├── split.py                     P2  stratified holdout
│   ├── splits/holdout.csv dev_tune.csv split.json     P2 (committed)
│   ├── run_eval.py                  P2  run a config over a split, score, price, time
│   ├── summarize.py                 P2  tables + routing breakdown + taxonomy + calibration
│   ├── verify_traps.py              P1  the trap checks, re-runnable
│   └── results/                     P2  committed summaries (small files only)
├── tests/                           each person owns tests for their modules
├── docs/  (official, plus:)
│   ├── data-notes.md                P1  trap findings, file sortedness, kpi_name lists, answer forms
│   ├── model-findings.md            P2  availability, latency, thinking toggle, JSON reliability
│   └── ai-use.md                    P2  running AI-use log for the README
├── data/                            gitignored: data/Market-cloudbed-1/…
├── out/  cache/                     gitignored
```

Dependencies stay **`pandas`, `numpy`, `openai`** (plus `pytest` for dev only,
not in `requirements.txt`). No networkx, no plotting libraries in the image.
If a plot is wanted for REPORT.md, generate it outside Docker with matplotlib
installed locally and commit the PNG.

---

## SHARED CONTRACT

Both people build against this. **Do not change it without telling the other
person** and recording it in the CHECKPOINT LOG. Person 1 types §1–§3 into
`origin/contract.py` and `origin/config.py` in Phase 1 and pushes them to `main`.

### §1 Constants — `origin/contract.py`

```python
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import timezone, timedelta
import pandas as pd

UTC8 = timezone(timedelta(hours=8))
TIME_FMT = "%Y-%m-%d %H:%M:%S"
LEVELS = ("node", "pod", "service")

NODE_REASONS = (
    "node CPU load", "node CPU spike", "node disk read I/O consumption",
    "node disk space consumption", "node disk write I/O consumption", "node memory consumption",
)
POD_REASONS = (
    "container CPU load", "container memory load", "container network latency",
    "container network packet corruption", "container network packet retransmission",
    "container packet loss", "container process termination",
    "container read I/O load", "container write I/O load",
)
NETWORK_REASONS = (
    "container network latency", "container network packet corruption",
    "container network packet retransmission", "container packet loss",
)
def legal_reasons(level: str) -> tuple[str, ...]:
    return NODE_REASONS if level == "node" else POD_REASONS   # services take container reasons

def fmt_ts(ts: float) -> str:          # epoch seconds -> "YYYY-mm-dd HH:MM:SS" in UTC+8
    ...
```

### §2 Data shapes — `origin/contract.py`

```python
@dataclass
class Case:
    instruction: str
    n_failures: int                     # from the instruction; getting this wrong zeroes the case
    asks: dict[str, bool]               # {"datetime": bool, "component": bool, "reason": bool}
    lo_ts: float                        # window start, epoch seconds (instruction time read as UTC+8)
    hi_ts: float                        # window end
    days: list[str]                     # telemetry folders needed incl. baseline, e.g. ["2022_03_20"]
    notes: list[str] = field(default_factory=list)

@dataclass
class Window:
    case: Case
    base_lo_ts: float                   # baseline actually used
    base_hi_ts: float
    metrics: pd.DataFrame               # ts(float s), source(str file stem), cmdb_id(str), component(str),
                                        #   level(str), kpi(str), value(float)
    edges: pd.DataFrame                 # ts(float s), trace_id, caller(pod), callee(pod),
                                        #   parent_ms, child_ms, gap_ms, error(bool)
    pod_spans: pd.DataFrame             # ts(float s, 30 s bucket start), pod, count, errors, p50_ms
    logs: pd.DataFrame | None           # ts(float s), pod, is_error(bool), text(str, ≤ 200 chars)
    pod_node: dict[str, str]            # "adservice-2" -> "node-5"
    pod_service: dict[str, str]         # "adservice-2" -> "adservice"
    nodes: set[str]
    pods: set[str]
    services: set[str]
    stats: dict                         # {"files": {name: {"rows","bytes","seconds","method"}}, "load_s": float}

@dataclass
class Signal:
    id: str                             # "F1", "F2", ... (the fact ID shown to models and in evidence)
    kind: str                           # "metric" | "edge_gap" | "edge_errors" | "disappear" | "pod_errors" | "log_errors"
    component: str                      # the component this signal is evidence about
    level: str                          # "node" | "pod" | "service"
    source: str                         # "metric_container.csv", "trace_span.csv", ...
    cmdb_id: str                        # raw cmdb_id (edges: "caller → callee")
    kpi: str                            # raw kpi_name, or "call gap ms" / "call errors" / "series missing"
    score: float                        # sustained robust z (capped)
    onset_ts: float | None              # epoch s of the first sustained breach
    direction: str                      # "up" | "down"
    base_median: float
    base_n: int
    first_value: float | None           # raw value at onset_ts
    peak_ts: float
    peak_value: float                   # raw value at peak_ts
    breach_samples: int
    reason_votes: dict[str, float]      # legal reason -> weight

@dataclass
class Candidate:
    cid: str                            # "C1", "C2", ... in rank order
    component: str
    level: str
    score: float                        # after the causal filter
    raw_score: float                    # before
    onset_ts: float | None              # earliest onset among its signals
    support: int                        # distinct anomalous signals
    reasons: list[tuple[str, float]]    # legal reasons, best first
    signal_ids: list[str]               # best first
    demoted_by: str | None              # sentence, e.g. "node-5 went wrong 3 min earlier (F4)"
    promoted_over: list[str]            # pods this node was promoted over

@dataclass
class Analysis:
    case: Case
    signals: dict[str, Signal]
    candidates: list[Candidate]         # ≤ 15, rank order
    margin: float                       # (s1 - s2) / s1, 1.0 if one candidate, 0.0 if none
    engine_answers: list[dict]          # exactly n dicts: {"datetime","component","reason","cid","signal_ids"} (chronological)
    window_stats: dict
    timings: dict                       # {"load_s","signals_s","candidates_s","total_s"}
    notes: list[str]
```

### §3 Function contracts

```python
# P1
origin.case.parse_instruction(instruction: str) -> Case
origin.load.load_window(case: Case, dataset_dir: Path) -> Window
origin.engine.analyze(instruction: str, dataset_dir: Path, deadline_ts: float | None = None) -> Analysis
origin.facts.render_fact(sig: Signal) -> str             # one markdown bullet, grep-able
origin.facts.render_ruled_out(a: Analysis, chosen: list[str], k: int = 3) -> list[str]

# P2
origin.anomaly.score_series(ts: np.ndarray, values: np.ndarray, base_lo: float, base_hi: float,
                            win_lo: float, win_hi: float, tau: float = TAU, k: int = K) -> dict | None
    # None if < MIN_BASE_SAMPLES baseline points or < k window points.
    # keys: score, onset_ts, direction, base_median, iqr_floor, base_n, first_value,
    #       peak_ts, peak_value, breach_samples, zero_baseline
agents.origin.solve(instruction: str, dataset_dir: Path, ctx: dict) -> run.Solution
```

### §4 Per-case trace — `<out>/origin_trace.jsonl` (P2 writes; eval reads)

One line per case, appended by `agents/origin.py` (it only writes inside `--out`):

```json
{"instruction_sha1": "…", "mode": "routed", "route": "gate|flash|strong|engine_only|fallback",
 "n_failures": 1, "asks": {"datetime": true, "component": true, "reason": false},
 "engine_top": ["shippingservice-1", "container read I/O load"], "margin": 0.22,
 "flash_pick": [["shippingservice-1", "container read I/O load"]], "strong_pick": null,
 "final": [["2022-03-20 09:09:00", "shippingservice-1", "container read I/O load"]],
 "confidence": "Medium", "grounding_dropped": false, "errors": [],
 "seconds": {"engine": 6.1, "flash": 3.2, "strong": 0.0, "total": 9.6}}
```

`run.py` doesn't pass `row_id` to agents, so eval joins on `sha1(instruction)`.

---

# PERSON 1 — DATA + ENGINE

You own: the dataset and its traps, the case parser, the window loader,
normalization and topology, trace edges, turning series into signals,
candidates + causal filter + reasons, facts rendering, `engine.analyze()`, and
engine accuracy on dev-tune. You do not touch model calls, the agent entry
point, evidence assembly, Docker or the eval harness.

You depend on Person 2 for `origin.anomaly.score_series` (§3). Until CP2, use a
local stand-in in `tests/_p1_score_stub.py` with the same signature and keys
(robust z vs median/IQR, sustained over k). Delete it after CP2.

## Phase 1 — Push, data, traps, contract, parser (10:00–10:30, hard stop 10:30)

- [x] **Start the data download first (9:45).** `make data` from the repo root
      (1.3 GB zip → ~12 GB in `data/Market-cloudbed-1/`). It runs in the
      background while you do the next tasks. If Person 2 can't download, give
      them the zip by USB / AirDrop — don't make them wait on Wi-Fi.
      > done. Unzipped everything **except `log_proxy.csv`** (6.5 GB, never read) because the laptop had ~15 GB free; the zip stays in `data/` if it is needed.
- [x] **Push the bootstrap (by 10:05).** The planner already ran `git init`
      and committed. Ask the human to confirm the remote is empty and they're
      logged in to GitHub, then: `git push -u origin main`,
      `git checkout -b person1 && git push -u origin person1`. Tell the human
      "Person 2 can clone now."
      > done. `main` was already on the remote; `person1` created and pushed.
- [x] **Contract + config (by 10:12).** Type §1 and §2 into
      `origin/contract.py` exactly (implement `fmt_ts` with
      `datetime.fromtimestamp(ts, tz=UTC8).strftime(TIME_FMT)`). Create
      `origin/__init__.py` (empty) and `origin/config.py`:

  ```python
  # ---- fixed parameters (SPEC "Fixed parameters"); change only from dev-tune, log in REPORT.md ----
  TAU = 3.0
  K = 2
  Z_CAP = 50.0
  IQR_FLOOR_FRAC = 0.05
  MIN_BASE_SAMPLES = 5
  BASELINE_S = 3600             # 60 min before the window
  READ_PAD_S = 120              # slack around every time filter
  EDGE_BUCKET_S = 30
  DISAPPEAR_MIN_BASE = 10       # baseline samples before "missing" means anything
  CAUSAL_EARLIER_S = 60         # dependency must be this much earlier to demote
  CAUSAL_DEMOTE = 0.3
  NODE_PROMOTE_MIN_PODS = 2
  NODE_PROMOTE_WINDOW_S = 120
  SPIKE_MAX_SAMPLES = 3         # node CPU breach this short = "node CPU spike"
  MULTI_FAILURE_SEP_S = 300     # for n >= 2, prefer candidates with onsets this far apart
  MAX_CANDIDATES = 15
  ONSET_SHIFT_S = 0             # PLACEHOLDER: dev-tune may set -30; log it
  METRIC_SOURCES = ("metric_container", "metric_node", "metric_service")
  # reason table: filled in Phase 3 from docs/data-notes.md kpi lists
  REASON_RULES: list[tuple[str, str, str, float]] = []   # (level, regex on kpi, reason, weight)

  # --- PERSON 2 ---  (model tiers / budget constants appended below this line)
  ```

  Push these two files to `main` as well (the allowed direct commit) so Person 2 can import them.
      > done, typed exactly; committed to `main` (4f9a2e8) and pushed.
- [x] **Verify the traps on real files (by 10:25).** Write
      `eval/verify_traps.py` (run with `python eval/verify_traps.py`) that
      prints evidence for each, and copy its output into `docs/data-notes.md`:
  1. **Headers and first rows** of every file in `telemetry/2022_03_20/{metric,log,trace}/`
     (`head -c 2000`, never `cat`). Note column names and whether
     `timestamp` is integer seconds / float / milliseconds.
  2. **Sortedness** of each file by timestamp: read the timestamp at 64
     evenly spaced byte offsets (seek, discard the partial line, parse the next
     line with `csv.reader`). Sorted = non-decreasing within 120 s of jitter.
     This decides whether `timeslice.py` can binary-search.
  3. **UTC+8 check:** take one dev case with a datetime answer (read
     `dev/query_dev.csv` with `pd.read_csv`; the answer is in `scoring_points`,
     "…occurrence time is within 1 minutes (i.e., <=1min) of 2022-03-20 09:09:06").
     Convert that time as UTC+8 to epoch and confirm the answer component's
     metrics change within a few minutes of that epoch. If they instead change
     8 hours away, the data is not UTC+8 epoch — **stop and tell both humans**.
     Also confirm the telemetry day folder matches the UTC+8 date.
  4. **Units:** trace `timestamp` magnitude (ms ≈ 1.6e12) vs metric `timestamp`
     (s ≈ 1.6e9); trace `duration` typical magnitude (ms or µs? report the
     median and p99 from a 100 k-row sample).
  5. **Sampling interval** of `metric_container` and `metric_node` (median
     diff between consecutive timestamps of one series).
  6. **Distinct values:** all `kpi_name` for `metric_container` and
     `metric_node` (from a full read with `usecols=["kpi_name"]`, fine for these
     sizes) → write the full lists into `docs/data-notes.md`; `cmdb_id`
     examples per file; `trace_span.type` and `status_code` value counts
     (sample); `log_service.log_name` values.
  7. **Answer forms** (allowed: this is about label *shape*, not memorising
     answers): from `dev/query_dev.csv` `scoring_points`, tabulate how answer
     components look — `node-N`, pod (`name-N`), bare service (`name`), other —
     with counts, and the count of each reason. Do **not** copy component names
     into code.
      > done; see `docs/data-notes.md`. UTC+8 yes (55/55 answer times in their windows). Trace duration is **µs**. Only `metric_node` is time-sorted; `trace_span` is ~10 time-sorted shards (seek per shard); metric_container/service are grouped by series (per-day cache). **24/54 answer components are bare services** → service candidates needed. Sortedness uses 1,024 probes (not 64), because 64 hid the shard structure.
- [x] **Case parser (by 10:30).** `origin/case.py` `parse_instruction()`:
  - Window: reuse the starter regex from `agents/heuristic.py::parse_window`
    (month name, day, year, `HH:MM` to `HH:MM`, with an optional second date),
    but build the datetimes with `tzinfo=UTC8`. If the second time is ≤ the
    first, add a day. `lo_ts = lo.timestamp()`.
  - `n_failures`: search the lowercase instruction for
    `r"\b(one|two|three|four|five|\d+)\s+failures?\b"` (word → int). If none,
    1, and add a note.
  - `asks`: `datetime` if the text mentions `occurrence time`/`datetime`/`time of`;
    `component` if `component`; `reason` if `reason`. **Check this against
    `docs/data.md`'s task table** on all 70 instructions: for each `task_index`,
    all instructions must give the same `asks` and match the table. Write that
    check as `tests/test_case.py`. If the wording doesn't split cleanly, map
    by the phrases you find and note them in `docs/data-notes.md`.
  - `days`: UTC+8 date folders for `lo_ts − BASELINE_S` through `hi_ts`.
  - Tests: the example from `docs/data.md` ("March 20, 2022, from 09:00 to
    09:30", "one failure") → `lo_ts` = epoch of 2022-03-20 09:00 UTC+8, n = 1;
    a window crossing midnight; all 70 parse without exception.

      > done; all 70 parse, `asks` matches the task table, `n_failures` matches the answer count on all 70. Changed: count words include `a failure` / `a single failure`; `asks` is read from the **last sentence only** (verbs vary: identify / determine / pinpoint).
### 🛑 CHECKPOINT 1 — contract lock + traps + models (10:30)

Print this to your human and stop:

> **Person 1 ready for Checkpoint 1.**
>
> Pushed: bootstrap, `origin/contract.py`, `origin/config.py`, `origin/case.py`,
> `eval/verify_traps.py`, `docs/data-notes.md`.
>
> **Merge with Person 2.** Person 2 should have `docs/model-findings.md`, the
> holdout split in `eval/splits/`, and a heuristic baseline score.
>
> Run:
>
> ```
> python -m pytest -q
> python eval/verify_traps.py | head -60
> python -c "from origin.case import parse_instruction; import pandas as pd; q=pd.read_csv('data/Market-cloudbed-1/dev/query_dev.csv'); c=parse_instruction(q.instruction[0]); print(c)"
> ```
>
> Expected: tests pass; the trap report shows sortedness per file, the UTC+8
> check passing, units, and sampling interval.
>
> **Decide together now (write in the CHECKPOINT LOG):**
> 1. Files sorted by time? `[per file]` → loader method `[seek / chunked]`
> 2. UTC+8 confirmed? `[yes/no]`. Trace duration unit: `[ms/µs]`
> 3. Answer component forms: `[node a, pod b, service c]` → do we need service-level candidates? `[yes/no]`
> 4. From Person 2: which models are up, Flash / GLM-5.2 latency, how to turn thinking off, JSON reliability.
> 5. Holdout: 21 row_ids fixed in `eval/splits/split.json` — nobody looks at per-case results on those until CP4.
> 6. **Ask an organizer:** does Track 1 expect MantisGrid MCP / an MCP? If **required**, STRETCH #1 (our MCP
>    server, Person 1's STRETCH section) moves to right after CP3, and the cut order drops `log_service` and
>    `metric_service` signals to make room. If optional, it stays a stretch after CP4.
>
> Waiting for your confirmation that this passed.

## Phase 2 — Window loader, normalization, topology, trace edges (10:30–11:30, gate at 11:00, hard stop 11:30)

- [x] **`origin/timeslice.py` (by 10:50).**

  ```python
  def read_slice(path: Path, lo: float, hi: float, ts_col: str, ts_scale: float = 1.0,
                 usecols: list[str] | None = None, dtype: dict | None = None) -> tuple[pd.DataFrame, dict]
      # returns rows with lo <= ts/ts_scale < hi, and {"rows","bytes","seconds","method"}
  ```

  - `ts_scale` is 1000 for `trace_span.csv` (ms), 1 elsewhere. `lo`/`hi` are epoch seconds.
  - Read the header line to find the timestamp column index.
  - `_ts_at(fh, offset)`: `fh.seek(offset)`; if `offset > 0` call
    `fh.readline()` to drop the partial line; loop up to 50 lines: read a line,
    parse with `next(csv.reader([line.decode("utf-8", "replace")]))`, return
    `(float(row[i]) / ts_scale, line_start_offset)` on the first line that parses.
    Open files in binary mode.
  - **Seek method** (file sorted per CP1): binary search the smallest line-start
    offset whose ts ≥ `lo − READ_PAD_S` and the smallest whose ts > `hi + READ_PAD_S`
    (~40 iterations). Read those bytes, prepend the header, then
    `pd.read_csv(io.BytesIO(buf), usecols=usecols, dtype=dtype)` and filter exactly.
  - **Chunked method** (not sorted): `pd.read_csv(path, usecols=usecols,
    dtype=dtype, chunksize=1_000_000)`, filter each chunk, concat.
  - Keep a module-level LRU dict `{(path, lo, hi): df}` of the last 8 reads, so
    the eval and repeated calls don't re-read.
  - Test on a tiny temp CSV (sorted and unsorted) that both methods return the
    same rows. Time a 90-minute slice of `trace_span.csv` and print it.
      > done, **changed**: files are split into time-sorted runs first (1,024 timestamp probes), then each run is binary-searched, because `trace_span.csv` is ~10 sorted shards, not one. Files with > 32 runs use chunked. Added a `method=` override. 90-min trace slice: **0.4 s**, same rows as a full scan (`tests/test_timeslice.py`).
- [x] **`origin/load.py` — metrics (by 11:00).** `load_window(case, dataset_dir)`:
  - `base_lo = lo_ts − BASELINE_S`, `base_hi = lo_ts`. Read range = `[base_lo, hi_ts]`
    across every folder in `case.days` (concat). If a baseline would need a
    missing folder, use `[hi_ts, hi_ts + BASELINE_S]` as the baseline instead and
    note it.
  - `metric_container.csv` and `metric_node.csv`: `usecols=["timestamp","cmdb_id","kpi_name","value"]`,
    `dtype={"cmdb_id": "category", "kpi_name": "category", "value": "float64"}`.
    Drop NaN / ±inf values.
  - Components:
    - `metric_container`: `cmdb_id = "<node>.<pod>"` → split on the **first** `.`:
      `node, pod`. `component = pod`, `level = "pod"`. Record `pod_node[pod] = node`.
    - `metric_node`: `component = cmdb_id`, `level = "node"`.
    - `pod_service[pod] = re.sub(r"-\d+$", "", pod)`.
  - `metric_service.csv` (`service,timestamp,rr,sr,mrt,count`): melt `rr, sr, mrt, count`
    into `kpi`/`value`; `component = service` with a trailing `-grpc` / `-http` suffix removed
    (verify the suffixes in data-notes); `level = "service"`. Only use it as
    a candidate source if CP1 said services appear in answers; otherwise keep
    it for evidence only (`level="service"`, never ranked).
  - `source` = file stem without `.csv`.
      > done, **changed**: metric files are grouped by series, so each day is read once and cached in-process (metric_container 1.4 s / 67 MB) instead of seeked. `metric_service` is loaded as `level="service"` (services are 24/54 answers, so they will be candidates). `pod_service`: `<name>2-0` maps to `<name>` only when `<name>` is a service from other pods or metric_service (no names in code). `load_window` takes an optional `deadline_ts` (extension of §3, backward compatible).
- [x] **Trace edges (by 11:20).** In `load.py`:
  - `trace_span.csv` via `read_slice(..., ts_col="timestamp", ts_scale=1000,
    usecols=["timestamp","cmdb_id","span_id","trace_id","duration","status_code","parent_span"])`,
    `dtype` strings for ids, `category` for cmdb_id / status_code.
    `ts = timestamp / 1000`. Convert `duration` to ms using the CP1 finding (÷1000 if µs).
  - Join child → parent: `spans.merge(spans[["trace_id","span_id","cmdb_id","duration"]],
    left_on=["trace_id","parent_span"], right_on=["trace_id","span_id"], suffixes=("","_p"))`.
    Keep rows where `cmdb_id != cmdb_id_p`: `caller = cmdb_id_p`, `callee = cmdb_id`.
  - Only parents with exactly one cross-pod child get a gap:
    count children per `(trace_id, parent_span)`; `gap_ms = parent_ms − child_ms`
    where count == 1, else NaN. `error = status_code not in {"0","Ok","OK","ok",""}`
    (adjust to the CP1 value counts).
  - `pod_spans`: per 30 s bucket (`floor(ts / 30) * 30`) and pod: count,
    errors, median duration.
  - Pods seen only in traces still go into `pods` / `pod_service` (no node known).
  - If the trace read would take longer than `deadline − 20 s`, skip it,
    return empty frames, and add a note (the router sees the note).
      > done. Duration is µs, so `/1000`. `error` = status_code not in `{0, Ok, OK, ok, 200, ""}`. Test checks one edge's parent_ms / child_ms against the raw rows. Negative gaps (to −4 ms, clock skew) are kept as-is.
- [x] **Logs (STRETCH-lite, only if ahead at 11:20).** `log_service.csv`
      window only: `is_error` = `value` contains `error|exception|fail|fatal`
      (case-insensitive), `pod = cmdb_id`. Skip `log_proxy.csv` entirely.
      > done. Only error-like lines are kept, in one chunked pass per day (~11 s) that is then cached, so `is_error` is always True. Controlled by `config.LOAD_LOGS`. The first case of each day costs +11 s, and the pass is skipped if the deadline is < 35 s away. **Cut it first if Docker time is tight.**
- [x] **Load test.** `tests/test_load.py` on the first dev case: `metrics` has
      both levels, every pod has a node, `edges` non-empty, all `ts` within
      `[base_lo − 120, hi + 120]`, and **no `ts` > 1e11** (catches ms leaking in).

      > done: `tests/test_load.py` (both levels + service, every pod has a node, ts range, no ms, edge numbers vs raw rows, baseline fallback, midnight, deadline skip). All 70 dev windows load: **mean 2.7 s, max 5.3 s, peak RSS 1.8 GB** (before logs). Also fixed `case.days` wrongly listing the next day for windows that end at 00:00.
### ⏱ GATE — load speed (11:00, solo)

Print this to your human and stop:

> **Person 1 at the 11:00 load gate.**
>
> ```
> python -c "import time; from pathlib import Path; import pandas as pd; from origin.case import parse_instruction; from origin.load import load_window; q=pd.read_csv('data/Market-cloudbed-1/dev/query_dev.csv'); t=time.time(); w=load_window(parse_instruction(q.instruction[0]), Path('data/Market-cloudbed-1')); print(round(time.time()-t,1),'s'); print(w.stats)"
> ```
>
> Cold load of one case (metrics only so far): `[X] s`. Target < 15 s cold, < 5 s warm.
>
> - **Under target:** continue with trace edges.
> - **Over target:** the files aren't seekable or pandas is slow. Fallback:
>   metric files are small enough to load **once per day** into a module
>   cache (`usecols`, categories) and filter in memory; the seek path is kept
>   for `trace_span.csv` only. If traces can't be sliced in < 15 s either,
>   read them with `chunksize` **once per day** into edge aggregates (30 s
>   buckets) and cache those.
>
> Waiting for your go.

> **Gate result (P1):** cold **3.1 s** / warm **1.0 s** on the first dev case with metrics + traces (under target, so continued).
> With logs on, the first case of a day is **14.2 s** cold (one-off log pass), then 1.6–3 s.

> **P1 pre-CP2 finding (the human let P1 continue without the CP1 merge; Person 2's `origin/anomaly.py` isn't here yet).** CP2 smoke
> run with `tests/_p1_score_stub.py` (PLACEHOLDER) on dev rows 0, 3, 7: the top list is **not** "a few components". 92–181
> anomalous series on 31–43 of 59 cmdb_ids, many capped at 50. Causes seen: (a) periodic single spikes also present in the
> baseline (baseline max 0.61 > window max 0.32 on a `container_network_receive_MB.eth0` series) with a tiny IQR, and
> two spikes in a row count as sustained; (b) 26/92 anomalies are zero-baseline series. **Suggestions for `score_series`
> (P2):** don't breach inside the baseline's own [min, max] (or p1–p99) range; require the zero-baseline rule to beat the
> baseline's nonzero fraction. The loader looks right: true causes do show up (row 7 `node-1` disk reads at 12:08;
> row 3 `node-1` `system.mem.free` z 26.8 at 10:30).

### 🛑 CHECKPOINT 2 — real window + anomalies (11:30)

Print this to your human and stop:

> **Person 1 ready for Checkpoint 2.**
>
> `load_window` works on real data: `[rows]` metric rows, `[rows]` edges, cold
> `[X] s` / warm `[Y] s`, method `[seek/chunked]`.
>
> **Merge with Person 2.** Person 2 should have `origin/anomaly.py`, the
> fixture, the `agents/origin.py` skeleton and the eval harness running the
> heuristic.
>
> Run:
>
> ```
> python -m pytest -q
> python -c "from pathlib import Path; import pandas as pd, numpy as np; from origin.case import parse_instruction; from origin.load import load_window; from origin.anomaly import score_series; q=pd.read_csv('data/Market-cloudbed-1/dev/query_dev.csv'); c=parse_instruction(q.instruction[0]); w=load_window(c, Path('data/Market-cloudbed-1')); g=w.metrics.groupby(['cmdb_id','kpi'], observed=True); r=[(k, score_series(d.ts.values, d.value.values, w.base_lo_ts, w.base_hi_ts, c.lo_ts, c.hi_ts)) for k,d in g]; r=sorted([(k,s['score']) for k,s in r if s], key=lambda x:-x[1])[:10]; print(r)"
> ```
>
> Expected: a top-10 of anomalous (cmdb_id, kpi) with scores ≥ 3 on a real dev case.
>
> Check specifically: are any `ts` values in milliseconds? Does the top list
> look like a fault (a few components) rather than everything?
>
> Waiting for your confirmation that this passed.

After CP2: delete `tests/_p1_score_stub.py`; import `origin.anomaly.score_series`.

## Phase 3 — Signals, candidates, reasons, facts, engine (11:30–12:45, hard stop 12:45; lunch at the keyboard 12:00–12:30)

- [x] **Reason table (by 11:45).** From the kpi_name lists in `docs/data-notes.md`,
      fill `REASON_RULES` in `origin/config.py`: `(level, regex, reason, weight)`,
      **first matching rule wins**, regex matched case-insensitively against the
      raw `kpi_name`. Start from these patterns and adjust them to the real names.
      Check read/write before generic disk, and spike before load, in code.

  | level | regex (adjust to real names) | reason | weight |
  |---|---|---|---|
  | pod | `fs_read\|read_bytes\|reads` | container read I/O load | 1.0 |
  | pod | `fs_write\|write_bytes\|writes` | container write I/O load | 1.0 |
  | pod | `memory\|mem_\|rss\|working_set\|cache` | container memory load | 1.0 |
  | pod | `cpu` | container CPU load | 1.0 |
  | pod | `network.*(drop\|dropped)` | container packet loss | 0.8 |
  | pod | `network.*(err\|errors)` | container network packet corruption | 0.6 |
  | pod | `retrans` | container network packet retransmission | 0.8 |
  | pod | `network_(receive\|transmit)` | container network latency | 0.3 |
  | pod | `threads\|processes\|restart` | container process termination | 0.6 |
  | node | `cpu` | node CPU load (→ spike if `breach_samples ≤ SPIKE_MAX_SAMPLES`) | 1.0 |
  | node | `mem` | node memory consumption | 1.0 |
  | node | `(io\|disk).*(read\|r_s\|rkb)` | node disk read I/O consumption | 1.0 |
  | node | `(io\|disk).*(write\|w_s\|wkb)` | node disk write I/O consumption | 1.0 |
  | node | `disk.*(used\|pct\|usage\|free\|avail)\|fs.*(used\|usage)` | node disk space consumption | 1.0 |

  Non-table votes (in `signals.py`): `edge_gap` → callee gets
  `{"container network latency": 1.0, "container network packet retransmission": 0.3}`;
  `edge_errors` → callee gets `{"container packet loss": 0.6, "container network packet corruption": 0.4,
  "container network packet retransmission": 0.4}`; `disappear` → `{"container process termination": 1.5}`.
  A KPI that matches no rule gets no vote but still counts as support.
      > done, **changed/added** (all tuned on dev-tune only, logged for REPORT.md):
      > `metric_node` names are `system.*`, so the node regexes are anchored on them; `container_spec_*`,
      > `*_limit`, `threads_max` and `ulimits` are configuration, not load, and vote for nothing.
      > Three **additions** beyond the table: (1) a signal only votes if it moved the way that means *more*
      > load (`free|usable|avail|idle` down, everything else up) — a falling CPU load is not `container CPU load`;
      > (2) `MAGNITUDE_RULES`: every container fault drags CPU, memory, threads and fds up together, so the
      > injected one is picked by absolute size (`container_fs_reads_MB`/`writes_MB` peak ≥ 1000, or
      > `container_cpu_usage_seconds` peak ≥ 10), which is what separates read/write I/O from CPU on dev-tune;
      > (3) `metric_service` `mrt`/`sr` vote weakly for latency / packet loss.
- [x] **`origin/signals.py` (by 12:05).**

  ```python
  def build_signals(w: Window, deadline_ts: float | None = None) -> dict[str, Signal]
  ```

  - **Metric signals:** group `w.metrics` by `(source, cmdb_id, kpi)`; for each group,
    `s = score_series(ts, value, w.base_lo_ts, w.base_hi_ts, case.lo_ts, case.hi_ts)`;
    keep if `s` and `s["score"] >= TAU and s["onset_ts"] is not None`.
    Vectorize if it's slow (sort once, `groupby(...).indices`). Target < 5 s for all series.
  - **Disappearance:** for each group with `base_n >= DISAPPEAR_MIN_BASE`, interval =
    median baseline diff; if the window has a gap ≥ 2 intervals (including
    "stops before `hi_ts`"), make a `disappear` signal: `onset_ts = last seen ts + interval`,
    `score = min(Z_CAP, TAU + gap_intervals)`, `first_value = None`, `peak_value` = last seen value,
    `peak_ts` = last seen ts. Only for pods.
  - **Edge signals:** for each `(caller, callee)` with ≥ 20 baseline calls:
    bucket `gap_ms` medians (and `child_ms` medians) per `EDGE_BUCKET_S`,
    run `score_series` on the bucket series → `edge_gap` signal on the
    **callee** (`component = callee`, `cmdb_id = f"{caller} → {callee}"`,
    `kpi = "call gap ms"`, `source = "trace_span.csv"`). Error-rate per bucket → `edge_errors`.
    Also a signal on the **callee's own** child_ms (`kpi = "server span ms"`).
  - Reason votes per the table (level of the component).
  - Assign IDs `F1…Fn` in order of descending score (stable: ties by onset, then cmdb_id).
  - Respect `deadline_ts`: if near, stop adding edge signals and note it.
      > done. All series scored in **0.6–0.8 s** per case. **Added two guards** (see the pre-CP2 finding above —
      > without them 92–181 "anomalies" per case): a breach must also leave the baseline's own [min, max] in the
      > anomaly's direction, and it must **not** have happened at the same clock offset 30 or 60 min earlier
      > (`PERIODIC_LAGS_S`) — the shop runs half-hourly/hourly jobs that spike node network and `disk.used` at
      > exactly :00/:30, which is where every case window starts. The onset is recomputed as the first
      > k-run that passes both guards, so periodic noise can't move the answer time.
      > Disappearance is **one signal per pod** (the series with the longest gap, carrying the count of series
      > that went missing) so 60 dead KPIs can't look like 60 independent facts. `pod_errors` = per-pod span
      > error rate per 30 s bucket. **Kept `score_series` as Person 2's contract**: `origin/anomaly.py` is not
      > merged yet, so `signals.py` falls back to `tests/_p1_score_stub.py` (marked PLACEHOLDER) — delete that
      > import once Person 2's module is on `main`.
- [x] **`origin/candidates.py` (by 12:25).**

  ```python
  def rank(w: Window, signals: dict[str, Signal]) -> tuple[list[Candidate], float]
  def engine_answers(case: Case, cands: list[Candidate], signals: dict[str, Signal]) -> list[dict]
  ```

  - Group signals by component. `raw_score = max(score) + 2 * log1p(support)`;
    `onset_ts = min(onset_ts)`; `reasons` = sum of `score * weight` per reason, sorted, legal only.
    If no legal reason has votes: pods default to the reason of their highest-scoring
    signal's *family*, else `container CPU load`; nodes `node CPU load`. Note it.
  - **Causal filter (demote):** for a pod `p`: if `pod_node[p]` is a candidate whose onset ≤
    `p.onset − CAUSAL_EARLIER_S` → `score = raw * CAUSAL_DEMOTE`,
    `demoted_by = f"{node} went wrong {m} min earlier ({best node fact})"`. If a callee `c` of `p`
    (an edge `p → c` exists with an `edge_gap`/`edge_errors` signal on `c`) has onset ≤
    `p.onset − CAUSAL_EARLIER_S` → demote the same way, naming `c`.
  - **Node promotion:** a node `n` that is a candidate with ≥ `NODE_PROMOTE_MIN_PODS` of its pods
    anomalous with onsets within `NODE_PROMOTE_WINDOW_S` of `n.onset` → `n.score = max(n.score,
    max pod raw score)`, and those pods are demoted with `demoted_by` naming `n`; `promoted_over`
    lists them.
  - **Shared callee:** a pod that is the callee in ≥ 2 anomalous edges from different callers
    gets `+2` score (network suspect).
  - Sort by `score` desc, then onset asc, then component; keep `MAX_CANDIDATES`; assign `C1…`.
    `margin = (s1 − s2) / s1` (1.0 if one, 0.0 if none).
  - `engine_answers`: take `n = case.n_failures` candidates: C1 first; for each further
    answer, the best-scored remaining candidate whose onset is ≥ `MULTI_FAILURE_SEP_S` from
    every chosen one, else the next best. **If there are fewer candidates than n, pad
    with the next components by `raw_score`, and if still short, repeat C1's
    level-default guess** (the count must be exact). Each answer:
    `datetime = fmt_ts(onset of the top signal supporting the chosen reason + ONSET_SHIFT_S)`
    (fallback: window start), `component`, `reason = reasons[0]`, `cid`, `signal_ids`.
    Sort answers by datetime.
      > done, **with three additions** (all from dev-tune):
      > (1) **Service candidates** (24/54 dev answer components are bare services, CP1): a service is the suspect
      > when ≥ `SERVICE_PROMOTE_MIN_PODS` (3) and ≥ 75% of its pods went wrong within 120 s of each other,
      > counting only pods scoring ≥ 40% of the strongest — one loud pod does not promote its service.
      > (2) **A node with exactly one anomalous pod is demoted as that pod's symptom** ("what node-6's metrics
      > show is that pod's own load"); a pod's own read-I/O storm otherwise wins the node the top spot. Node
      > promotion likewise ignores bystander pods (< 50% of the strongest).
      > (3) Candidate score uses `score × the signal's own reason weight` (floor 0.3, cap 1), so a noisy KPI that
      > votes for nothing — `container_network_receive_MB`, `system.net.*` — cannot make a component top suspect.
      > Reason score = best vote + 2·log(1 + other votes for it), not the sum, so one family with many KPIs
      > doesn't outvote the injected one. Candidate onset = earliest onset among signals ≥ 50% of the
      > candidate's best score (a weak early signal was dragging service onsets out of the promotion window).
- [x] **`origin/facts.py` (by 12:35).**
  - `render_fact(sig)` → one bullet, only raw or clearly labelled derived numbers:
    `- F3 · metric_container.csv · node-5.shippingservice-1 · container_fs_reads./dev/vda — baseline median 2.1 (60 samples, 08:00–09:00 UTC+8); first outside normal at 2022-03-20 09:09:00 (ts 1647738540), value 47.02; peak 51.3 at 2022-03-20 09:12:00 (ts 1647738720); score 18.3 (how many normal ranges away)`.
    Edge facts: `F7 · trace_span.csv · frontend-0 → shippingservice-1 · call gap ms — baseline median 3.1 ms per 30 s bucket (…); bucket starting 2022-03-20 09:09:00 (ts …ms 1647738540000) median 41.0 ms; …`
    (for trace facts print the epoch **in ms** too, since that's what the file holds).
    Disappearance: `… · series missing — last sample at … (ts …), value …; no samples for 6 expected intervals`.
    Values: `f"{v:.4g}"` for derived medians, and the raw value exactly as parsed
    (`repr(float)` trimmed to ≤ 6 significant digits).
  - `render_ruled_out(a, chosen, k=3)` → sentences for the top `k` non-chosen candidates, each built from facts:
    demoted → `"{comp} — {demoted_by}."`; later onset → `"{comp} — first went wrong at {t} ({Fx}), {m} min after {chosen}."`;
    lower score → `"{comp} — weaker: score {s:.1f} vs {s1:.1f} ({Fx})."`; if no node candidate for the chosen
    pod's node → `"{node} — no node-level metric left its normal range, so the node layer isn't the cause."`
      > done. Raw values are printed as the file holds them and, when long, **cut (never rounded) to 6
      > significant digits with a trailing `…`**, so the printed digits stay a prefix of the CSV text and a
      > judge's grep matches (`tests/test_facts.py` asserts that on real values). Trace facts print the epoch in
      > ms as well. `render_ruled_out` reads `pod_node` from `Analysis.window_stats["pod_node"]` (engine puts it
      > there) for the "no node-level metric moved" sentence.
- [x] **`origin/engine.py` + smoke run (by 12:45).** `analyze(instruction, dataset_dir, deadline_ts)`:
      parse → load → signals → rank → engine_answers, fill `timings`, catch
      exceptions per stage, and **always return an Analysis** (on failure:
      empty signals, `engine_answers` from a level-default guess with the window
      start as time, and a note). Env `ORIGIN_ENGINE_CACHE=<dir>` pickles the
      Analysis by `sha1(instruction)` for the eval (default off). Also:
      `python -m origin.engine --row <row_id>` prints the candidates table,
      the engine answers and the rendered facts for one dev case.
      > done. Every stage is caught and noted; a parse failure still answers (level default + window start).
      > CLI: `python -m origin.engine --row <id>` (candidates, answers, facts, ruled out, notes) and
      > `--split dev_tune --score` (scores with the vendored `score.evaluate`, writes
      > `out/engine/engine_dev_tune_per_case.csv`). `--score` **refuses any split but dev_tune** so the holdout
      > stays closed (PLAN rule 7). `ORIGIN_ENGINE_CACHE=<dir>` pickles by sha1(instruction).
      > Also added **`agents/p1_engine_only.py`** — P1's dev harness so the engine can run through `run.py`,
      > `make validate` and `make docker` before Person 2's agent lands (and SPEC emergency step 4's
      > engine-only fallback). Person 2 owns `agents/origin.py`; nothing in P2's files was touched.
      > **Engine-only on dev-tune: mean 0.539, 18/49 fully solved, 3.5 s/case mean (16 s max, the first case of
      > a day pays the one-off log pass)** vs the heuristic's 0.073 on all 70.

> **P1 notes for Person 2 at CP3 (read before merging).**
> 1. `origin/anomaly.py` is still missing on every branch, so `origin/signals.py` imports
>    `tests/_p1_score_stub.py` as a **PLACEHOLDER** (`grep -rn PLACEHOLDER origin agents eval tests`). When your
>    `score_series` lands, the fallback import is deleted — no other change. Two things the stub taught us on real
>    data, worth having in yours: don't call a breach anomalous if it stays inside the baseline's own [min, max],
>    and the zero-baseline rule needs the same treatment (26/92 "anomalies" were zero-baseline series). The engine
>    applies both guards itself on top of whatever `score_series` returns, so it is safe either way.
> 2. **Contract addition (backward compatible):** `Analysis.window_stats["pod_node"]` now carries the pod → node
>    map (`origin/facts.render_ruled_out` needs it). Nothing was removed.
> 3. `agents/p1_engine_only.py` is P1's dev harness (engine only, no model calls) so the engine could be run
>    through `run.py` and the official validator before your agent exists. It also renders the four evidence
>    sections from the facts — reuse or replace as you like; `agents/origin.py` is yours.
> 4. Engine numbers on dev-tune (49 cases): **mean 0.539, 18/49 fully solved, 3.5 s/case mean, 16.1 s max**
>    (the first case of a telemetry day pays a one-off ~11 s `log_service` pass; `config.LOAD_LOGS = False`
>    removes it and is cut-order #1 if Docker time is tight). Per task: t1 0.50 · t2 0.21 · t3 0.80 · t4 0.25 ·
>    t5 0.75 · t6 0.56 · t7 0.65. Weakest are the **reason-only tasks (t2, t4)**: network-group reasons and
>    process termination. `margin` is populated, so the gate and escalation conditions can be measured.

### 🛑 CHECKPOINT 3 — first end-to-end ORIGIN (12:45)

Print this to your human and stop:

> **Person 1 ready for Checkpoint 3.**
>
> `engine.analyze()` works end to end: `[X] s` per case. Engine-only on dev-tune: `[score]`.
>
> **Merge with Person 2.** Person 2 should have `agents/origin.py` with the gate,
> router, validator, confidence, evidence and grounding check, `run.py`
> defaulting to `agents.origin`, and the harness.
>
> Run:
>
> ```
> python -m pytest -q
> python -m origin.engine --row [a dev_tune row_id]
> ORIGIN_MODE=engine python -m eval.run_eval --config engine --split dev_tune
> make validate AGENT=agents.origin
> make dev AGENT=agents.origin N=3 OUT=out/smoke && make score OUT=out/smoke && cat out/smoke/evidence/*.md | head -80
> ```
>
> Expected: engine-only mean score on dev-tune `[X]` vs heuristic `[Y]`
> (should be ≥ heuristic); `make validate` passes; evidence files have all
> four sections and facts with timestamps.
>
> **Grep test (do it now, both humans):** pick one fact line from an evidence
> file and find it in the raw CSV, e.g. `awk -F, '$1==1647738540' data/Market-cloudbed-1/telemetry/2022_03_20/metric/metric_container.csv | grep shippingservice-1 | grep fs_reads`.
> The value must match. If it doesn't, fix `facts.py` before anything else.
>
> **If engine-only is worse than the heuristic:** SPEC emergency step 3 —
> Person 1 compares the two on dev-tune by task type before anything else.
>
> Waiting for your confirmation that this passed.

## Phase 4 — Accuracy and speed on dev-tune only (12:45–1:45, hard stop 1:45)

Work **only from dev-tune results** (`eval/results/engine_dev_tune_per_case.csv`
from Person 2's harness). Never open holdout per-case results. Log every change
in `REPORT.md` → "Tuning log" (what, why, dev-tune before → after).

- [ ] **Failure taxonomy on dev-tune (by 1:00).** For every dev-tune case not
      fully solved, classify the first thing wrong, in this order: wrong count
      (should be impossible) · time off > 60 s · wrong level (node vs pod) ·
      symptom picked over cause (true component is a lower candidate) · true
      component not a candidate at all · wrong reason within the network group
      · wrong reason otherwise. Write the counts into `REPORT.md` → "Engine
      failure taxonomy (dev-tune)". To look at a case: `python -m origin.engine --row <id>`.
- [ ] **Fix the biggest bucket first (by 1:35).** Allowed levers, one at a time,
      each re-scored on dev-tune: `ONSET_SHIFT_S` (0 / −30 / −60),
      `REASON_RULES` patterns and weights, edge vote weights,
      `CAUSAL_DEMOTE`, `NODE_PROMOTE_*`, `SPIKE_MAX_SAMPLES`. **Not allowed:**
      anything naming a specific component, day or case.
- [ ] **Speed (by 1:45).** Run the 21 holdout **instructions** (no scoring) through
      `analyze` with timings and report mean / max seconds. Target mean < 15 s on a laptop
      (the judge's 2 CPUs are slower; Person 2 measures that in Docker).
      If over: cache per-day metric reads, skip `metric_service`, reduce edge signals to
      edges with ≥ 50 baseline calls.

### 🛑 CHECKPOINT 4 — docker + final eval (1:45)

Print this to your human and stop:

> **Person 1 ready for Checkpoint 4.**
>
> Engine tuned on dev-tune only: `[before] → [after]`, changes logged in
> REPORT.md. Engine time mean `[X] s`, max `[Y] s`.
>
> **Merge with Person 2.** Person 2 should have the full eval on the holdout
> (engine, single-flash, single-strong, routed, heuristic; routed and
> single-strong repeated) and `make docker` passing on 20 cases under 20 min.
>
> Run:
>
> ```
> python -m pytest -q
> cat eval/results/summary.md
> FEATHERLESS_API_KEY=$FEATHERLESS_API_KEY make docker
> ```
>
> Expected: summary table with holdout numbers per config, $/case, s/case,
> std across repeats; docker run writes 2 evidence files.
>
> **Now, both humans (mandatory walkthrough):** each explains the other's
> half out loud — UTC+8 and ms traps, the loader, robust z and onset, trace
> edge gaps, the causal filter, reasons, facts and the grep test; the gate and
> escalation, the validator, confidence, the grounding check, the eval split
> and repeats. **Pick the demo case**: a dev case (not holdout) that the
> routed agent solves, with a readable evidence file and a greppable fact.
>
> Waiting for your confirmation that this passed.

## Phase 5 — Walkthrough, report, freeze (1:45–2:50)

- [ ] **REPORT.md engine sections (by 2:05):** loading (files, methods, time),
      signals (metrics, trace edges, disappearance), topology from names, causal
      filter, reason table, fixed parameters + tuning log, engine failure
      taxonomy, what the engine is blind to (e.g. `log_proxy`, mesh metrics,
      corruption vs retransmission).
- [ ] **2:15 freeze.** Bug fixes only.
- [ ] **2:15–2:40 presentation:** you drive the terminal for the live case and
      the grep; Person 2 narrates the eval.
- [ ] **Submission check with Person 2** (FINAL SUBMISSION).

## STRETCH (Person 1) — only after CP4 and only if the human says so

- [ ] `metric_mesh.csv` edge signals (quoted `kpi_name` with commas → always `csv`/pandas, never split).
- [ ] `log_service.csv` error bursts per pod as `log_errors` signals.
- [ ] Fix test: ridge counterfactual on pod CPU/memory → "Verifier check (simulated)" line in Ruled out.
- [ ] **STRETCH #1 — ORIGIN MCP server (~45–60 min; build this first).** Our own MCP server over the
      engine, so an on-call engineer can ask Claude Desktop / Claude Code "what broke between 09:00 and
      09:30?". **It stays outside the judged path:** don't touch `Dockerfile`, `requirements.txt`,
      `run.py` or `agents/`, and never import `fastmcp` from `origin/`.
  1. **Query backend first** (also used by Person 2's STRETCH #2), in `origin/query.py`:

     ```python
     def get_series(a: Analysis, w: Window, component: str, kpi: str) -> Signal | None
         # score_series on that (component, kpi) over the case's baseline + window; returns a Signal with the
         # next free fact ID (added to a.signals) even if it is NOT anomalous (score < TAU), so "it was normal"
         # is also a grounded fact. None if the series doesn't exist.
     def get_edge(a: Analysis, w: Window, caller: str, callee: str) -> Signal | None   # same, for the call-gap series
     ```

     `engine.analyze` must also keep the `Window` it loaded (add `window: Window | None` to `Analysis`,
     **excluded from the pickle cache**) so these don't re-read files. Tell Person 2 about the contract change.
  2. **`mcp_server.py` at the repo root** (not a package named `mcp/`, which would shadow the `mcp` SDK), using FastMCP:

     ```python
     from fastmcp import FastMCP
     mcp = FastMCP(name="ORIGIN RCA", instructions="Root-cause analysis over OpenRCA Market telemetry. "
         "Every fact carries its source file, cmdb_id, KPI and epoch timestamp; quote facts, don't invent numbers. "
         "Times are UTC+8. Call analyze_case before the other case tools.")
     DATASET = Path(os.environ.get("ORIGIN_DATASET", "data/Market-cloudbed-1"))
     _CASES: dict[str, Analysis] = {}        # case_id -> Analysis, in memory
     ```

     Tools (each docstring written for the model, short, saying what's fact vs model-chosen):
     - `list_cases(limit: int = 20) -> list[dict]` — `row_id`, `task_index`, the window and failure count parsed from
       `query.csv` (never `scoring_points`).
     - `analyze_case(row_id: int | None = None, instruction: str | None = None) -> dict` — runs `engine.analyze`
       (engine only, **no GLM calls**), stores it under `case_id = str(row_id)` or `sha1(instruction)[:8]`, returns
       `case_id`, n_failures, asked fields, the engine answers, margin, and the top 5 candidates (cid, component, level,
       score, onset in UTC+8, top reason, demoted_by).
     - `get_candidates(case_id: str, k: int = 8) -> list[dict]` — the ranked candidates with their fact IDs.
     - `get_evidence(case_id: str) -> str` — the four evidence sections for the engine answers, reusing
       `origin/facts.py` (+ Person 2's `origin/evidence.py` builder with an engine-only decision).
     - `get_fact(case_id: str, fact_id: str) -> str` — `render_fact` of one fact.
     - `get_series(case_id: str, component: str, kpi: str) -> str` and `get_edge(case_id: str, caller: str, callee: str) -> str`
       — the query backend above; return the rendered new fact, or "no such series" with the KPIs that do exist for that component (≤ 20).

     End the file with `if __name__ == "__main__": mcp.run()` (stdio).
  3. **Run and connect.** `uv run --with fastmcp --with-requirements requirements.txt python mcp_server.py`
     (or `pip install fastmcp` into the local `.venv` only). Claude Code: `claude mcp add origin -- uv run --with fastmcp
     --with-requirements requirements.txt python /abs/path/mantisgridhacks/mcp_server.py`, then ask "use origin to list
     cases and analyze row 0". Claude Desktop: the same command in `claude_desktop_config.json` under `mcpServers.origin`
     with `"cwd"` set to the repo. Write both snippets into README.md → "MCP server (optional)".
  4. **Test:** `tests/test_mcp_tools.py` calls the tool functions directly (FastMCP-decorated functions are still
     callable via `mcp_server.analyze_case.fn(...)`, or keep plain helper functions that the tools wrap and test those).
     Then one real conversation from a client; save the transcript screenshot for the presentation.
  5. Tell Person 2 it's ready for the optional presentation beat (their Phase 5 table).

---

# PERSON 2 — AGENT, ROUTING, EVAL, PRESENTATION

You own: Featherless model findings, the holdout split, `score_series`, the
agent entry point (`agents/origin.py`) with budget, gate, cheap/strong calls,
validator, confidence, evidence assembly and grounding check, `run.py`'s
default agent, the eval harness and every eval run, `REPORT.md`, `README.md`,
Docker, and leading the presentation. You do not touch loading, signals,
candidates or fact rendering.

You develop against `origin/fixture.py` (yours) until real engine output lands at CP3.

## Phase 1 — Env, model spike, split, baseline (10:00–10:30, hard stop 10:30)

- [x] **Clone + env (by 10:05).** When Person 1 says pushed:
      `git clone https://github.com/alaramartin/mantisgridhacks.git && cd mantisgridhacks`,
      `git checkout -b person2 && git push -u origin person2`.
      `python3.12 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt pytest`.
      `cp .env.example .env`, ask the human for their Featherless key, put it in `.env`
      and `export FEATHERLESS_API_KEY=...` in the shell (`llm.py` reads the
      environment, not `.env`). Get the data from Person 1 (or `make data`).
      Start `docs/ai-use.md`: product models (GLM family via Featherless),
      coding assistants each person uses, agent frameworks (none — OpenAI SDK +
      starter `llm.py`), and a module table "AI-generated / team-written" to
      fill as you go.
      done — repo was already local; branch `person2` created and pushed. Python 3.14.7 with
      pandas/numpy/openai already present, so no venv (PLAN said 3.12; nothing needed it).
      `.env` written from `.env.example` with the human's key, confirmed gitignored + dockerignored;
      the shell exports it via `set -a && . ./.env`. Data downloaded with `make data`'s URL (~10 min).
      `docs/ai-use.md` started.
- [x] **Model spike (by 10:20).** A throwaway script (not committed), findings into
      `docs/model-findings.md`:
  1. `curl -s https://api.featherless.ai/v1/models | python -c "import sys,json; d=json.load(sys.stdin); print([m['id'] for m in d['data'] if 'zai-org' in m['id']])"`
     — which of the 7 GLM models are listed? Note the live prices if present.
  2. For `GLM-4.7-Flash`, `GLM-5.3-Flash`, `GLM-5.2`, `GLM-5.1`: one call with a
     ~3 K-token prompt (paste a fake fact sheet) asking for JSON
     `{"answers":[{"candidate":"C1","reason":"..."}],"confidence":"low","why":"..."}`,
     using `llm.LLM().ask(model, prompt, max_tokens=..., temperature=0, timeout=40)`.
     Record wall seconds, prompt / completion tokens, whether the JSON parsed.
  3. **Thinking toggle:** repeat the GLM-5.2 and Flash calls with
     `extra_body={"chat_template_kwargs": {"enable_thinking": False}}`, then with
     `extra_body={"thinking": {"type": "disabled"}}`. Whichever measurably cuts
     completion tokens and seconds is the switch; record it. Also check whether
     the reply has a `reasoning_content` field (print `r.choices[0].message`
     once, from a direct `client.chat.completions.create`).
  4. Note any capacity errors (HTTP 200 with `error` body) you hit.
      done — `docs/model-findings.md`. All 7 documented GLM models are live and live prices match
      `docs/models.md`. Three findings that change the build:
      (1) **thinking must be off on every call** — with it on, all four models blow past a 1,200-token
      output cap mid-JSON and 0/4 parse; the working switch is
      `extra_body={"chat_template_kwargs": {"enable_thinking": False}}` and
      `{"thinking": {"type": "disabled"}}` is silently ignored.
      (2) **Featherless returns the answer in `message.reasoning` with `content` empty** for both Flash
      models — not `reasoning_content`, no `<think>` tags — so the starter `llm.py` returns `""` on
      every GLM-4.7-Flash call. `llm.py` needs a `reasoning` fallback in Phase 2.
      (3) **GLM-5.3-Flash is the unreliable one** (2/4 parses, 207–530 output tokens), so cheap tier is
      GLM-4.7-Flash first. No capacity errors seen in 20 calls.
- [x] **Holdout split (by 10:25).** `eval/split.py` (run once, commit its output):
      read `data/Market-cloudbed-1/dev/query_dev.csv` with `pd.read_csv`;
      per `task_index`, sort that task's `row_id`s by
      `hashlib.md5(str(row_id).encode()).hexdigest()` and take the first
      `min(3, count)` as holdout. Write `eval/splits/holdout.csv` and
      `eval/splits/dev_tune.csv` (same columns as `query_dev.csv`, filtered) and
      `eval/splits/split.json` (`{"holdout": [...], "dev_tune": [...], "rule": "..."}`).
      Print counts per task. **Do not run anything on holdout until CP4.**
      done — `eval/split.py` + `eval/splits/{holdout,dev_tune,split}.{csv,json}` committed.
      21 holdout / 49 dev_tune, exactly 3 per task_index (every task has >= 7 cases). Not opened.
- [x] **Baseline scores (by 10:30).** `make dev AGENT=agents.heuristic OUT=out/heuristic && make score OUT=out/heuristic`
      (free, ~1 min). Record the mean (expect ≈ 0.073) in `docs/model-findings.md`.

      done — `agents.heuristic` over all 70 dev cases: **mean 0.073**, 2/70 fully solved, 1.5 min,
      0 tokens. Matches the brief's 0.073. task_3 and task_5 score a flat 0.000 — flagged for CP1.
### 🛑 CHECKPOINT 1 — contract lock + traps + models (10:30)

Print this to your human and stop:

> **Person 2 ready for Checkpoint 1.**
>
> `docs/model-findings.md`: models up `[list]`; Flash `[s, tokens]`; GLM-5.2
> `[s, tokens]` thinking on / off; thinking switch `[param]`; JSON parse rate `[x/y]`.
> Holdout split committed: `[21]` cases, 3 per task type. Heuristic baseline: `[0.07x]`.
>
> **Merge with Person 1.** Person 1 should have `origin/contract.py`,
> `origin/config.py`, `origin/case.py`, the trap report.
>
> Run:
>
> ```
> python -m pytest -q
> python eval/verify_traps.py | head -60
> cat docs/model-findings.md
> ```
>
> Expected: tests pass; UTC+8 confirmed; units known; model latencies known.
>
> **Decide together now:** does GLM-5.2 with thinking fit the time budget
> (≤ 25 s)? If not, strong runs with thinking **off**, or strong = GLM-5.1 /
> GLM-4.7 — decide from the numbers and write it in the CHECKPOINT LOG.
>
> Waiting for your confirmation that this passed.

## Phase 2 — score_series, fixture, agent skeleton, harness (10:30–11:30, hard stop 11:30)

- [ ] **`origin/anomaly.py` `score_series` (by 10:50).** Exactly §3.

  ```
  order = argsort(ts); ts, x = ts[order], values[order]; drop NaN / inf
  base = x[(ts >= base_lo) & (ts < base_hi)];  win_mask = (ts >= win_lo) & (ts < win_hi)
  if len(base) < MIN_BASE_SAMPLES or win_mask.sum() < k: return None
  med = median(base); iqr = q75 − q25
  u = unique(base); step = min positive diff of u (0 if len(u) < 2)
  zero_baseline = (med == 0 and iqr == 0)
  wt, wx = ts[win_mask], x[win_mask]
  if zero_baseline:
      breach = wx != 0;  floor = step if step > 0 else 1.0
      z = where(breach, Z_CAP, 0.0)
  else:
      floor = max(iqr, IQR_FLOOR_FRAC * abs(med), step, 1e-9)
      z = minimum(abs(wx − med) / floor, Z_CAP)
      breach = z >= tau
  sustained[p] = min(z[p : p+k])   for p in 0..len−k   (pd.Series(z).rolling(k).min().shift(−(k−1)))
  first = first p with all(breach[p:p+k])   (None if none)
  score = nanmax(sustained) (0 if none); if zero_baseline and first is not None:
      score = min(Z_CAP, tau + 10 * breach.mean())
  peak = argmax(z)
  return {"score", "onset_ts": wt[first] or None, "direction": "up" if wx[peak] >= med else "down",
          "base_median": med, "iqr_floor": floor, "base_n": len(base),
          "first_value": wx[first] or None, "peak_ts": wt[peak], "peak_value": wx[peak],
          "breach_samples": int(breach.sum()), "zero_baseline": zero_baseline}
  ```

  Import `TAU, K, Z_CAP, IQR_FLOOR_FRAC, MIN_BASE_SAMPLES` from `origin.config`.
  `tests/test_anomaly.py`: constant baseline 5.0 → floor 0.25, no divide-by-zero;
  all-zero baseline with 3 nonzero window points → score ≥ τ and an onset;
  a single spike (1 point) with k = 2 → score < τ; a step up at sample 10 →
  onset = ts[10], `first_value` = the raw value there; a drop → `direction="down"`.
- [ ] **`origin/fixture.py` (by 11:00).** `make_analysis(n_failures=1) -> Analysis`
      hand-built with realistic shapes: 5 candidates (a pod with read I/O
      signals, its node, a caller pod demoted by an earlier callee, a pod with an
      `edge_gap` signal, another node), ~12 Signals with plausible numbers,
      `margin` 0.22, `engine_answers` for C1. Also `make_clear_analysis()` with
      margin 0.6 / support 3 (gate case) and a 2-failure variant. `# PLACEHOLDER: fixture until CP3`.
- [ ] **Patch `llm.py` for Featherless's `reasoning` field (by 10:40) — BLOCKER, do this first.**
      Measured at CP1 (`docs/model-findings.md` §3): Featherless returns the answer in
      `message.reasoning` with `message.content == ""` on **both Flash models, 4/4 calls**.
      It is not `reasoning_content` and there are no `<think>` tags. `llm.py`'s `_once()`
      reads only `.content`, so **it returns `""` on every GLM-4.7-Flash call** — our cheap
      tier, the model most cases will use. The agent would see an empty answer, fall back to
      the engine, and still be billed. In `_once()`, after the usage accounting:

      ```python
      msg = r.choices[0].message
      text = msg.content or ""
      if not text.strip():        # Featherless puts it here on the Flash models
          text = getattr(msg, "reasoning", None) or getattr(msg, "reasoning_content", None) or ""
      return re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()
      ```

      This is the **only** starter file we change beyond `run.py`'s default `--agent`.
      Record it in `README.md` and `ATTRIBUTION.md`, and tell Person 1 at the merge —
      anyone using the starter `llm.py` with a Flash model is silently getting empty strings.
      `tests/test_llm.py`: a stub response with `content=""` and `reasoning='{"a":1}'` must
      come back as `'{"a":1}'`; one with both populated must prefer `content`; `<think>`
      stripping must still work on both fields.

- [ ] **Docker installed and `make docker` green (by 11:20) — BLOCKER for CP4, start early.**
      Checked at CP1: **Docker is not installed on Person 2's machine at all** (not on PATH,
      nothing in `Program Files`). Priority #1 needs `make docker` passing at 2 CPU / 8 GB by
      CP4, and Docker Desktop is a large download plus a reboot, so it cannot wait until 1:45.
      Human action: install Docker Desktop, enable the WSL2 backend, confirm
      `docker version` works, then `make docker` (builds the image and runs 2 dev cases).
      If Docker cannot be installed in time, the fallback is for Person 1 to run
      `make docker` on their machine and paste the output — but the image must be proven
      somewhere before the submission, because judges run it.

- [ ] **Model tiers + agent skeleton (by 11:20).** Append to `origin/config.py` below `# --- PERSON 2 ---`:

  ```python
  # tiers confirmed by the CP1 spike (docs/model-findings.md): 4.7-Flash parsed 4/4 at
  # ~90 output tokens and 2.4-3.7 s; 5.3-Flash only 2/4 (it rambles past the JSON), so it
  # is the availability fallback, never the first choice. GLM-5.3 exists on Featherless
  # but is NOT in cost.py's PRICES and would raise KeyError -- never call it.
  CHEAP = ["zai-org/GLM-4.7-Flash", "zai-org/GLM-5.3-Flash"]
  STRONG = ["zai-org/GLM-5.2", "zai-org/GLM-5.1"]     # 5.2: 1.5-17 s, ~45 out tok, 4/4
  CHEAP_MAX_TOKENS = 700          # measured worst case 95 with thinking off; 700 is slack
  STRONG_MAX_TOKENS = 700         # was 4000 for thinking-on; CP1 turned thinking OFF
  CALL_TIMEOUT_S = 25
  CASE_SOFT_DEADLINE_S = 45
  STRONG_MIN_REMAINING_S = 20
  RUN_AVG_LIMIT_S = 50            # above this running average, go engine-only
  GATE_MARGIN = 0.35
  GATE_SUPPORT = 2
  ESCALATE_MARGIN = 0.15
  FACTS_MAX = 40
  CANDIDATES_SHOWN = 8
  # CONFIRMED at CP1, not a placeholder. Pass this as extra_body on EVERY model call.
  # With thinking on, all four models spend the whole output budget narrating and get cut
  # off mid-JSON: 0/4 parsed at a 1200-token cap. With it off: 12/16 parsed, 1.5-4 s.
  # The other documented switch, {"thinking": {"type": "disabled"}}, is silently ignored.
  THINKING_OFF = {"chat_template_kwargs": {"enable_thinking": False}}
  ```

  `agents/origin.py`:

  ```python
  import hashlib, json, os, sys, time
  from pathlib import Path
  sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
  from run import Solution, format_prediction
  from llm import LLM

  _RUN = {"start": None, "cases": 0, "seconds": 0.0}
  _LLM = None      # one client for the whole run, so the breaker remembers dead models

  def solve(instruction, dataset_dir, ctx) -> Solution:
      t0 = time.time(); deadline = t0 + CASE_SOFT_DEADLINE_S
      mode = os.environ.get("ORIGIN_MODE", "routed")        # routed | engine | single
      avg = _RUN["seconds"] / _RUN["cases"] if _RUN["cases"] else 0
      if avg > RUN_AVG_LIMIT_S: mode = "engine"; note("running average over limit: engine only")
      a = analyze(instruction, Path(dataset_dir), deadline)   # P1; fixture until CP3 via ORIGIN_FIXTURE=1
      llm = get_llm()   # None if FEATHERLESS_API_KEY missing -> engine only, noted
      if llm: llm.usage = {}                                 # usage is per case
      decision = route(a, llm, mode, deadline)               # origin/router.py
      answers, confidence, notes = validate(a, decision)     # origin/validate.py
      evidence = build_evidence(a, answers, decision, confidence, notes, time.time() - t0)   # origin/evidence.py
      prediction = format_prediction([{k: v for k, v in x.items() if a.case.asks.get(k)} for x in answers])
      write_trace(ctx["out_dir"], ...)                       # §4
      _RUN["cases"] += 1; _RUN["seconds"] += time.time() - t0
      return Solution(prediction=prediction, evidence=evidence, usage=(llm.usage if llm else {}))
  ```

  - `get_llm()`: create `LLM(retries=1, backoff=1.0, breaker=2)` once; catch
    `RuntimeError` (no key) → `None`.
  - Wrap the whole body in `try/except Exception`: on any crash, return the
    best available answers (engine answers if `a` exists, else a level-default
    guess with the window start) and evidence containing the traceback summary.
    **Never return an empty prediction.**
  - If `asks` has no field at all (parser failed), include all three fields.
- [ ] **Eval harness v1 (by 11:30).** `eval/run_eval.py`:

  ```
  python -m eval.run_eval --config <name> --split holdout|dev_tune [--repeat R] [--limit N]
  ```

  - `CONFIGS = {"heuristic": {"agent": "agents.heuristic", "env": {}},
    "starter-routed": {"agent": "agents.routed", "env": {}},
    "engine": {"agent": "agents.origin", "env": {"ORIGIN_MODE": "engine"}},
    "single-flash": {"agent": "agents.origin", "env": {"ORIGIN_MODE": "single", "RCA_MODEL": "zai-org/GLM-4.7-Flash"}},
    "single-strong": {"agent": "agents.origin", "env": {"ORIGIN_MODE": "single", "RCA_MODEL": "zai-org/GLM-5.2"}},
    "routed": {"agent": "agents.origin", "env": {"ORIGIN_MODE": "routed"}}}`.
  - For each repeat `r`: `out = out/eval/{config}/{split}/r{r}`; run
    `python run.py --dataset data/Market-cloudbed-1 --queries eval/splits/{split}.csv --out {out} --agent {agent}`
    as a subprocess with the env merged into `os.environ` (plus
    `ORIGIN_ENGINE_CACHE=cache/engine` only for configs using `agents.origin`),
    timing the whole run.
  - Score: `python score.py --predictions {out}/predictions.csv --queries eval/splits/{split}.csv --report {out}/per_case.csv`.
  - Cost: read `{out}/usage.jsonl` (last line per row_id wins), `cost.dollars(models)` per case.
  - Time: `wall_s` per case from usage.jsonl. When the engine cache was hit, add
    the cold engine seconds stored in the cache entry, so s/case is honest. Say so in REPORT.md.
  - Join `{out}/origin_trace.jsonl` by `sha1(instruction)` for route / confidence.
  - Append one row per case to `eval/results/per_case.csv` (config, split, repeat,
    row_id, task_index, score, dollars, wall_s, route, confidence, n_failures)
    and one summary row to `eval/results/runs.csv` (config, split, repeat, n,
    mean_score, fully_solved, $/case mean, s/case mean + max, git sha, timestamp).
  - Print the summary row. Test it on `heuristic` / `dev_tune` now.

### 🛑 CHECKPOINT 2 — real window + anomalies (11:30)

Print this to your human and stop:

> **Person 2 ready for Checkpoint 2.**
>
> `score_series` with tests; fixture Analyses; `agents/origin.py` skeleton
> running on the fixture (`ORIGIN_FIXTURE=1`); eval harness scoring the heuristic on dev_tune: `[score]`.
>
> **Merge with Person 1.** Person 1 should have `load_window` on real data.
>
> Run:
>
> ```
> python -m pytest -q
> python -m eval.run_eval --config heuristic --split dev_tune
> ORIGIN_FIXTURE=1 ORIGIN_MODE=engine make dev AGENT=agents.origin N=2 OUT=out/fixture && cat out/fixture/predictions.csv
> ```
>
> Plus Person 1's anomaly smoke command (in their CP2 block).
>
> Expected: harness prints a heuristic summary row; the fixture run writes 2
> predictions with the right key order.
>
> Waiting for your confirmation that this passed.

## Phase 3 — Router, validator, confidence, evidence (11:30–12:45, hard stop 12:45; lunch at the keyboard 12:00–12:30)

- [ ] **`origin/router.py` — fact sheet + calls (by 12:05).**

  ```python
  def fact_sheet(a: Analysis) -> str
  def route(a: Analysis, llm, mode: str, deadline: float) -> dict
  # -> {"route": "gate"|"flash"|"strong"|"engine_only"|"fallback",
  #     "picks": [{"cid","reason","fact_ids"}] | None, "confidence_model": str|None,
  #     "why": str|None, "flash": {...}|None, "strong": {...}|None, "errors": [str], "seconds": {...}}
  ```

  Fact sheet (keep it byte-stable in structure; ≤ `CANDIDATES_SHOWN` candidates, ≤ `FACTS_MAX` facts):

  ```
  CASE: {n} failure(s) between {fmt window lo} and {hi time} (UTC+8). The answer needs: {component, reason | …}.
  LEGAL REASONS
    For node components (names like node-N): {NODE_REASONS joined by "; "}
    For pods and services: {POD_REASONS joined by "; "}
  CANDIDATES (engine ranking; score = how many normal ranges away, after checking what each depends on)
  C1 {component} ({level}{", on "+node if pod}) score {score:.1f}; first went wrong {HH:MM:SS}; engine reason: {reasons[0]}; facts {F…}{"; DEMOTED: "+demoted_by if any}
  …
  FACTS
  {render_fact(sig) for the facts referenced above, best first, up to FACTS_MAX}
  NOTES
  {a.notes, e.g. "traces skipped: deadline"}
  ```

  Prompt (after the sheet):

  ```
  You are diagnosing a microservice incident. The loudest component is often a victim.
  Prefer the component whose anomaly started first and whose dependencies (its node, the pods it calls) were normal.
  Network faults show up as call-gap facts on trace edges. Pick exactly {n} root cause(s).
  Reply with JSON only, no prose:
  {"answers": [{"candidate": "C<number>", "reason": "<one legal reason for that component's level>", "fact_ids": ["F<number>", ...]}],
   "confidence": "low" | "medium" | "high",
   "why": "at most 3 sentences; refer to facts by ID; do not write any number that is not in the facts"}
  ```

  Flow in `route()`:
  - `mode == "engine"` or `llm is None` → `route = "engine_only"`, picks None.
  - `mode == "routed"`: **gate** if `a.margin >= GATE_MARGIN and a.candidates[0].support >= GATE_SUPPORT and n == 1` → `route = "gate"`.
    Else **flash**: `llm.ask(CHEAP, messages, max_tokens=CHEAP_MAX_TOKENS, temperature=0, timeout=CALL_TIMEOUT_S, extra_body=THINKING_OFF)`.
    **Escalate** to strong if any: flash reply invalid (JSON parse fails, wrong count, unknown cid, illegal reason),
    flash top pick's component ≠ engine C1, `a.margin < ESCALATE_MARGIN`, `n >= 2`, or all three fields asked.
    Skip escalation if `deadline − now < STRONG_MIN_REMAINING_S` (note it) and use flash if valid, else engine.
    Strong prompt = the same + `"A fast model picked: {flash picks}. The engine's top candidate is C1. Decide independently."`,
    `max_tokens=STRONG_MAX_TOKENS`, `timeout=CALL_TIMEOUT_S`, thinking on (no `extra_body`).
  - `mode == "single"`: one call on `[os.environ["RCA_MODEL"]]` with the flash prompt, **no gate, no escalation**
    (max_tokens = STRONG_MAX_TOKENS if the model isn't a Flash model).
  - Parse: `re.search(r"\{.*\}", text, re.S)` → `json.loads`; on failure record the error.
  - `ModelUnavailable` / any exception → record, `route = "fallback"`, picks from the last valid stage or None.
  - Time each stage into `seconds`.
- [ ] **`origin/validate.py` (by 12:20).**

  ```python
  def validate(a: Analysis, d: dict) -> tuple[list[dict], str, list[str]]   # answers, confidence, notes
  ```

  - Start from `a.engine_answers`. If `d["picks"]` is valid: for each pick `i < n`: cid must exist
    → component; reason must be in `legal_reasons(level)` else the candidate's `reasons[0]` (note);
    `datetime` = `fmt_ts` of the onset of that candidate's best signal voting for the chosen reason
    (else the candidate onset, else the window start). Duplicated components are replaced by the next engine answer.
  - Exactly n answers (trim / pad from engine answers), sorted by datetime.
  - **Confidence:** `High` if `a.margin >= GATE_MARGIN` and C1 support ≥ `GATE_SUPPORT` and (no model
    called, or the final component(s) == engine's); `Low` if `a.margin < ESCALATE_MARGIN`, or the final
    top component ≠ engine C1, or the route is `fallback`/`engine_only` because of an error or deadline, or
    the engine noted a failed stage; else `Medium`. Also a one-sentence `confidence_why` from which rule fired.
- [ ] **`origin/evidence.py` (by 12:40).**

  ```python
  def build_evidence(a, answers, d, confidence, notes, seconds) -> str
  def grounded(text: str, sheet: str, a: Analysis) -> tuple[bool, list[str]]
  ```

  Sections, in this order:
  - `## Answer` — one line per answer: `{component} / {reason} / {datetime}` (only asked fields,
    but always show all three here with "(not asked)" labels if omitted from the prediction).
  - `## Confidence` — `{High|Medium|Low}.` + `confidence_why` + the model's `why` **only if**
    `grounded(why)`. Plain doubt sentences for Low: the runner-up and what would separate them (from facts).
  - `## Evidence` — `render_fact` for each answer's `signal_ids` (≤ 6 per answer) plus the
    model's cited `fact_ids` if they exist.
  - `## Ruled out` — `render_ruled_out(a, [answer components])`.
  - `## How this was produced` — route (gate / flash / strong / engine only / fallback), models with
    calls and tokens from `llm.usage`, seconds per stage, engine timings, notes, and
    **"engine answer kept"** vs **"model changed the engine's answer"**. Never describe a fallback as a model decision.
  - `grounded()`: every number in `text` (`re.findall(r"\d+(?:\.\d+)?", text)`) must appear
    as a substring of the fact sheet, unless it is an integer ≤ 10 or part of a fact ID (`F12`, `C3`); every token
    matching `r"\b[a-z]+(?:service|node)[\w-]*\b|\bnode-\d+\b"` must be a known component in
    `a.candidates` or the window. If not grounded → drop the prose, keep the template, add
    "model prose removed: it cited a number not found in the data" to notes.
  - `tests/test_evidence.py` on the fixture: all four sections present; a `why` containing "73.2"
    (not in facts) is dropped; a `why` citing `F3` and a fact's number is kept.
- [ ] **Switch the default agent (12:45).** In `run.py` change only
      `p.add_argument("--agent", default="agents.heuristic", …)` → `default="agents.origin"`.
      In `Makefile` `validate`, change `agents.heuristic` → `agents.origin`. Until CP3, `agents/origin.py`
      uses the fixture when `ORIGIN_FIXTURE=1`, and otherwise imports `origin.engine`
      lazily (on `ImportError`, fall back to `agents.heuristic.solve` and say so in evidence).

### 🛑 CHECKPOINT 3 — first end-to-end ORIGIN (12:45)

Print this to your human and stop:

> **Person 2 ready for Checkpoint 3.**
>
> Router (gate → Flash → GLM-5.2 escalation, single-model mode), validator,
> confidence, evidence with grounding check, `run.py` defaulting to `agents.origin`.
>
> **Merge with Person 1.** Person 1 should have `engine.analyze()` end to end.
>
> Run:
>
> ```
> python -m pytest -q
> make validate
> make dev N=3 OUT=out/smoke && make score OUT=out/smoke && make cost OUT=out/smoke
> cat out/smoke/evidence/0.md
> tail -3 out/smoke/origin_trace.jsonl
> python -m eval.run_eval --config engine --split dev_tune
> ```
>
> Expected: `make validate` passes; 3 cases with evidence (four sections, facts
> with timestamps, a route line); cost in cents; the engine dev_tune summary row.
>
> **Grep test (both humans)** — see Person 1's CP3 block. A mismatched number blocks everything.
>
> Waiting for your confirmation that this passed.

## Phase 4 — Eval runs, Docker, REPORT (12:45–1:45, hard stop 1:45)

Run configs **in parallel terminals** (they're independent processes). Budget
check: an ORIGIN case sends ~4–6 K tokens, so even GLM-5.2 on every case costs
cents. Stay far below $25.

- [ ] **dev_tune runs for Person 1 (by 1:00):** `engine` (free) whenever Person 1 asks;
      `routed` once on dev_tune at ~1:00 so the routing breakdown exists.
- [ ] **Holdout runs (1:15, after Person 1's last tuning change is merged or frozen):**
  - `heuristic` ×1, `starter-routed` ×1, `engine` ×1
  - `single-flash` ×2, `single-strong` ×3, `routed` ×3
  - Commit `eval/results/` after each.
- [ ] **`eval/summarize.py` (by 1:35)** → `eval/results/summary.md`:
  1. **Main table (holdout):** config · n · mean score (± std over repeats) · fully solved · easy / middle / hard ·
     $/case · $/correct (label "noisy") · s/case mean / max · tokens in/out per case.
  2. **Same table for dev_tune**, labelled "tuned on these — optimistic".
  3. **Per task type** (task_1…task_7) for `routed`, `single-strong`, `engine`.
  4. **Routing breakdown (routed):** % gate / flash / strong / fallback, mean score and $/case per route.
  5. **Calibration (routed, holdout + dev_tune pooled, say so):** High / Medium / Low → count and mean score.
  6. **Failure taxonomy** (pooled): from `per_case.csv` `passed/failed` columns: time wrong,
     component wrong, reason wrong, count wrong, fallback/timeout.
  7. **Headline sentences**, computed: e.g. "routed reached X of single-strong's score at Y% of its cost and Z% of its time";
     "GLM-5.2 bought +d over Flash for k× the cost".
     If the strong model isn't better, the sentence says so.
- [ ] **Docker (by 1:40).** Docker Desktop running. `FEATHERLESS_API_KEY=... make docker` (2 cases,
      `--cpus 2 --memory 8g`). Then the **timing run**: the same `docker run` with
      `--queries /data/dev/query_dev.csv --limit 20` under `time`, capturing peak memory with
      `docker stats --no-stream` in another terminal. Must finish 20 cases in **< 20 min** (target < 12).
      If slower: lower `CASE_SOFT_DEADLINE_S` to 30, `STRONG_MAX_TOKENS` to 1500, or strong thinking off —
      one change at a time, re-run, write it down.
- [ ] **REPORT.md (by 1:45 draft; polish until 2:15).** Sections: What ORIGIN does (pipeline diagram
      from SPEC) · How we evaluate (splits, configs, repeats, what's cached and why times are honest) ·
      Results (summary tables) · Routed vs single model (the required comparison, with the
      headline sentences) · Where it fails (taxonomy, blind spots) · Knowing when it doesn't know
      (calibration) · Cost and time (per route; tokens vs the 474 K "typical case"; the 20-case Docker run) ·
      Tuning log (from Person 1) · Honest caveats (dev numbers are optimistic; judged deployment differs;
      n = 21 is small; one or two cases is a tie).

### 🛑 CHECKPOINT 4 — docker + final eval (1:45)

Print this to your human and stop:

> **Person 2 ready for Checkpoint 4.**
>
> Holdout results: routed `[score ± std, $/case, s/case]`, single-strong `[…]`,
> single-flash `[…]`, engine `[…]`, heuristic `[…]`. Docker: 20 cases in `[m:ss]`,
> peak memory `[X] GB`. REPORT.md drafted.
>
> **Merge with Person 1.**
>
> Run:
>
> ```
> python -m pytest -q
> cat eval/results/summary.md
> make validate
> FEATHERLESS_API_KEY=$FEATHERLESS_API_KEY make docker
> ```
>
> Expected: the summary tables; validate and docker pass.
>
> **Now, both humans (mandatory walkthrough)** — see Person 1's CP4 block.
> **Pick the demo case** (a dev case, not holdout, solved by routed, with a greppable fact).
>
> Waiting for your confirmation that this passed.

## Phase 5 — README, presentation, submit (1:45–2:50)

- [ ] **README.md (by 2:10).** Title "ORIGIN — Track 1 — Root Cause Analysis"; the SPEC "Written" pitch;
      the pipeline in 6 lines; **how to run** (`pip install -r requirements.txt`, `make data`,
      `export FEATHERLESS_API_KEY=…`, `make validate`, `make dev && make score`, `make docker`,
      `python -m eval.run_eval --config routed --split holdout`); headline results + link to REPORT.md;
      **AI disclosure** from `docs/ai-use.md` (product models: GLM family on Featherless, per call;
      coding assistants used by each person; agent frameworks: none; per-module AI-generated vs
      team-written); **attribution**: starter files from MantisGrid (`LICENSE-MANTISGRID`), OpenRCA
      evaluator vendored in `score.py`, data CC BY-NC 4.0 not included (`ATTRIBUTION.md`).
- [ ] **2:15 freeze.** Bug fixes only.
- [ ] **2:15–2:40 record the ~4-min presentation** (Cmd+Shift+5 with mic; terminal font ≥ 18 pt).

  | Time | Beat | On screen | Say |
  |---|---|---|---|
  | 0:00–0:25 | Problem + honest bar | README top | "When one component fails, everything downstream looks broken. The best published agent solves 18 of 70." |
  | 0:25–1:20 | **Live case** | `python run.py --dataset data/Market-cloudbed-1 --queries eval/splits/demo.csv --out out/demo` (a one-row CSV of the demo case) | "It reads only this half hour, rebuilds who runs where and who calls whom, ranks the suspects, and only calls a model if it's unsure." |
  | 1:20–2:20 | **Evidence + grep** | `cat out/demo/evidence/<row>.md`, then the `awk … | grep …` for one fact | "Every number here is copied from the raw data — here it is in the CSV. And here's what it ruled out, and why." |
  | 2:20–3:30 | **Eval** | `eval/results/summary.md` | routed vs single-model: score, dollars, seconds, variance; the routing breakdown; the negative result |
  | 3:30–4:00 | Where it fails + calibration + next | REPORT.md sections | one sentence each |
  | (inside 3:30–4:00, only if STRETCH #1 shipped; cut first) | Same engine as an MCP tool | Claude Code / Desktop asking "what broke between 09:00 and 09:30?" → `analyze_case`, `get_evidence` | "An on-call engineer can ask the same engine in chat, and get the same checkable facts." |

  Never show a `fallback` / `engine_only` case as the model deciding. If the live call is slow, keep talking; the `How this was produced` section explains the route.
- [ ] **Submit (FINAL SUBMISSION section) by 2:50.**

## STRETCH (Person 2) — only after CP4 and only if the human says so

- [ ] **STRETCH #1 (Person 1 builds it): ORIGIN MCP server** — your part is only the optional ~20 s presentation beat
      and the README "MCP server (optional)" section Person 1 hands you. Don't add `fastmcp` to `requirements.txt`.
- [ ] **STRETCH #2 — Bounded query tools** for the strong model: after its first reply, allow ≤ 2 requests
      `{"get_series": {"component","kpi"}}` / `{"get_edge": {"caller","callee"}}`, served by
      Person 1's `origin/query.py` (built for STRETCH #1), each result added to the sheet as a new fact ID; re-ask once. Only on escalated cases, only with ≥ 20 s left.
- [ ] Thinking on vs off ablation for GLM-5.2 on the holdout (one extra config).
- [ ] Cheaper strong tier (GLM-4.7 vs GLM-5.2) as an extra row.

---

# FINAL SUBMISSION (by 2:50; form closes 3:00pm PDT)

Only after both people confirm. Either person can run it.

- [ ] Both branches merged into `main` (`--no-ff`); `python -m pytest -q` passes on `main`; pushed.
- [ ] `make validate` passes on a fresh clone; `make docker` passes.
- [ ] Only one Dockerfile in the repo, at the root: `git ls-files | grep -i dockerfile`.
- [ ] Secrets: `git log -p | grep -iE "FEATHERLESS_API_KEY=.+|sk-[A-Za-z0-9]{10,}|rc_[A-Za-z0-9]{10,}"` → nothing;
      `git ls-files | grep -E "^\.env$"` → nothing.
- [ ] No data committed: `git ls-files | grep -E "^data/|\.csv$"` shows only `eval/splits/*.csv` and `eval/results/*.csv`.
      **The split CSVs contain `scoring_points` from the bundle** — that's the organizers' dev answers for a
      deployment they don't judge on; keep them, but if in doubt ask the organizers, or commit only `split.json` (row_ids) and regenerate.
- [ ] `run.py` default `--agent` is `agents.origin`; CLI unchanged.
- [ ] README has the AI disclosure and how to run; REPORT.md complete; `eval/` committed.
- [ ] Repo **public**; default branch shows the final commit from a logged-out browser.
- [ ] Form https://forms.gle/UbPSwZhKNfkovM8s5: both members with student/career status; title
      "ORIGIN"; description says **"Track 1 — Root Cause Analysis"**; repo link; presentation link
      (upload the recording, e.g. unlisted YouTube or Drive with view access); English.
- [ ] After 3:00: bug fixes and deploy repairs only.

---

# CHECKPOINT LOG

Update this on `main` after each merge so the humans can `/clear` and resume.

- [x] Planning (9:45) — official repo read (brief, data, models, scoring, submission, starter, agreement);
      starter copied flat to the repo root; Makefile adapted to the root layout; `.dockerignore` / `.gitignore`
      exclude data and secrets; SPEC v6.0 + PLAN v2 written; pushed to `main`.
  - Decision (humans): MCP = **STRETCH #1**, our own MCP server over the engine (`mcp_server.py`), outside the
    Docker path; MantisGrid's MCP is Track 2's API and unreachable from the judged container. Ask organizers at CP1.
  - MCP decision: recorded under Checkpoint 1 below.
- [x] Checkpoint 1 — contract lock + traps + models (10:30) — merged on `main` by Person 1's machine (both branches,
      no conflicts; 36 tests pass; `eval/split.py` re-run on P1's machine reproduces the committed split byte for byte).
      P1 had already finished Phase 2 when the merge ran, so its loader is in this merge too.
  - MCP decision at CP1 (required / optional): **PENDING — ask an organizer.**
  - Files sorted by time / loader method: `metric_node` sorted; `trace_span` = ~10 time-sorted shards → **seek per shard**;
    `metric_container` / `metric_service` grouped by series → **read once per day, cached**; `log_service` unsorted →
    chunked, error lines only, cached per day (`config.LOAD_LOGS`, cut first). `log_proxy` never read.
  - UTC+8 confirmed / trace duration unit: **UTC+8 yes** (55/55 answer times inside their windows; sharp metric changes at
    the answer time, noise at ±8 h). Trace timestamp **ms**, trace duration **µs**.
  - Answer component forms (node / pod / service counts) → service candidates?: **node 20 · pod 10 · service 24** →
    **yes, service-level candidates.** `<name>2-0` pods belong to service `<name>`. This also explains the heuristic's flat 0
    on task_3 / task_5 (component-only asks): it can only name pods/nodes, never a bare service.
  - Models up, latencies, thinking switch, strong-tier decision: all 7 priced GLM models up (plus unpriced `GLM-5.3`:
    **never call it**, cost.py would KeyError). **Thinking OFF on every call** via
    `extra_body={"chat_template_kwargs": {"enable_thinking": False}}` (thinking on: 0/4 parsed). Cheap = GLM-4.7-Flash
    (2.4–3.7 s, 4/4 JSON) → GLM-5.3-Flash fallback (2/4). Strong = GLM-5.2 (1.5–17 s, 4/4) → GLM-5.1. Details:
    `docs/model-findings.md`.
  - Blockers raised by P2: (1) starter `llm.py` returns `""` on Flash models (answer is in `message.reasoning`), P2 patches
    it first in Phase 2; (2) **Docker isn't installed on P2's machine.** Docker Desktop is installed on P1's Mac (daemon not
    running at merge time), so it's the fallback for `make docker`.
  - Holdout row_ids committed: **yes**, 21 holdout (3 per task) / 49 dev_tune in `eval/splits/split.json`. Nobody opens
    holdout per-case results until CP4.
  - Heuristic baseline: **0.073** mean on all 70 dev (2/70 fully solved; task_3 and task_5 = 0.000).
- [x] ⏱ 11:00 load gate — cold **3.1 s** / warm **1.0 s** (metrics + traces, first dev case), method: day-cache for metrics,
      seek per shard for traces. With logs: first case of a day 14.2 s, then 1.6–3 s. All 70 dev windows: mean 2.7 s, max
      5.3 s, peak RSS 1.8 GB.
- [ ] Checkpoint 2 — real window + anomalies (11:30)
- [ ] Checkpoint 3 — first end-to-end ORIGIN (12:45)
  - Engine-only dev_tune vs heuristic:
  - Grep test passed:
- [ ] Checkpoint 4 — docker + final eval (1:45)
  - Holdout table (routed / single-strong / single-flash / engine / heuristic):
  - Docker 20-case time and peak memory:
  - Demo case row_id:
  - Walkthrough done (both):
- [ ] 2:15 freeze · recorded · README · submitted
