# REPORT.md — ORIGIN, Track 1 (Root Cause Analysis)

**What this is.** The eval write-up the submission asks for: what ORIGIN does, how we tested it, what
the numbers are, where it fails, and what we would change. Numbers are produced by the benchmark's
own evaluator (`score.py`, vendored unchanged) through our harness (`eval/run_eval.py`); every run is
appended to `eval/results/runs.csv` with its git SHA.

> **P2: the sections marked `⟨P2⟩` are yours — the holdout tables, the routed-vs-single comparison,
> routing breakdown, calibration and the cost/time numbers. Everything else is written. Delete this
> block before submitting.**

**Two scores, never mixed.** **Partial** = the fraction of a case's scoring points (one per asked
field per failure). **Strict** = the share of cases where *every* point was right. `docs/scoring.md`
puts the published state of the art at **11.34% strict / 17.31% partial** (RCA-Agent on Claude 3.5
Sonnet) — measured over all 335 OpenRCA cases on three systems, so **not like-for-like** with our 49
Market cases. We quote both, and we say which.

---

## How we evaluate

**The splits.** 70 dev cases with answers, split **49 dev-tune / 21 holdout**, stratified 3 holdout
cases per task type, fixed by `row_id` in `eval/splits/split.json` *before any run* by a
deterministic rule (`md5(row_id)` order — re-running `eval/split.py` reproduces it byte for byte).

**Holdout discipline.** Nothing was tuned on the holdout. Every parameter change came from dev-tune
results and is logged below with its before/after number. The engine CLI refuses to score any split
but dev-tune, so the rule is enforced in code rather than by memory. The judges' 20 cases are a third
set, on a **different deployment**, which matters more than the split (see "Honest caveats").

**The configurations.** One agent (`agents/origin.py`); `ORIGIN_MODE` changes how much of it runs:

| Config | What runs | Models called |
|---|---|---|
| `heuristic` | the starter baseline | none |
| `engine` | our pipeline with no model calls (ablation) | none |
| `single-flash` | the full flow, no gate | GLM-4.7-Flash every call |
| `single-strong` | the full flow, no gate | GLM-5.2 every call |
| **`routed`** | **the submitted agent** | gate → Flash → GLM-5.2 on escalation |

**What is cached and why the times are honest.** `ORIGIN_ENGINE_CACHE` lets repeat runs reuse an
engine analysis so three repeats of a model config do not pay the load three times. The cache key
includes a hash of the engine's own source, so a parameter change can never be silently replayed —
we found that bug the hard way (a whole dev-tune run came back in 0.6 s with pre-tuning numbers) and
fixed it. Reported per-case seconds use the **cold** engine time recorded by the agent, not the
cached read, and the Docker numbers below are from an uncached run.

## Results

<!-- BEGIN SUMMARY -->

## 1. Holdout (21 cases, never tuned on)

| config | runs | mean score | fully solved | easy | middle | hard | $/case | $/correct* | s/case mean/max | tok in/out |
|---|---|---|---|---|---|---|---|---|---|---|
| `heuristic` | 2 | 0.111 ± 0.000 | 1.0/21 | 0.111 | 0.111 | 0.110 | $0.0000 | $0.0000 | 1.3 / 6.3 | 0 / 0 |
| `engine` | 2 | 0.524 ± 0.000 | 7.0/21 | 0.667 | 0.444 | 0.333 | $0.0000 | $0.0000 | 6.0 / 25.5 | 0 / 0 |
| `routed` | 1 | 0.417 (n=1) | 5.0/21 | -- | -- | -- | $0.0073 | $0.0175 | 12.6 / 27.1 | nan / nan |
| `routed-duel` | 1 | 0.524 (n=1) | 7.0/21 | 0.556 | 0.556 | 0.333 | $0.0001 | $0.0001 | 6.6 / 18.7 | 735 / 38 |

\* `$/correct` is noisy at n=21 — one case moves it a lot. Quoted for completeness, not for ranking.

## 2. dev_tune (49 cases) — **tuned on these, so optimistic**

| config | runs | mean score | fully solved | easy | middle | hard | $/case | $/correct* | s/case mean/max | tok in/out |
|---|---|---|---|---|---|---|---|---|---|---|
| `heuristic` | 2 | 0.056 ± 0.000 | 1.0/49 | 0.071 | 0.037 | 0.062 | $0.0000 | $0.0000 | 1.6 / 5.9 | 0 / 0 |
| `engine` | 5 | 0.560 ± 0.020 | 19.8/49 | 0.548 | 0.575 | 0.645 | $0.0000 | $0.0000 | 3.8 / 36.8 | 0 / 0 |
| `routed` | 1 | 0.440 (n=1) | 14.0/49 | 0.357 | 0.487 | 0.541 | $0.0059 | $0.0134 | 10.9 / 29.2 | 7,492 / 332 |
| `routed-reason` | 1 | 0.559 (n=1) | 19.0/49 | 0.524 | 0.562 | 0.645 | $0.0063 | $0.0113 | 13.1 / 30.3 | 7,782 / 444 |
| `routed-duel` | 1 | 0.524 (n=1) | 19.0/49 | 0.452 | 0.550 | 0.645 | $0.0001 | $0.0002 | 6.0 / 31.2 | 997 / 53 |

## 3. Score by task type (holdout)

| task | `engine` | `routed` | `routed-duel` |
|---|---|---|---|
| task_1 | 0.500 | 0.167 | 0.500 |
| task_2 | 0.833 | 0.833 | 0.500 |
| task_3 | 0.667 | 0.500 | 0.667 |
| task_4 | 0.500 | 0.417 | 0.833 |
| task_5 | 0.500 | 0.250 | 0.500 |
| task_6 | 0.333 | 0.417 | 0.333 |
| task_7 | 0.333 | 0.333 | 0.333 |

## 4. Where the routing went (`routed`, all splits)

| route | cases | share | mean score | $/case | s/case |
|---|---|---|---|---|---|
| `strong` | 87 | 46% | 0.445 | $0.0084 | 15.5 |
| `gate` | 45 | 24% | 0.567 | $0.0000 | 1.8 |
| `engine_only` | 29 | 15% | 0.712 | $0.0000 | 4.5 |
| `duel` | 20 | 11% | 0.325 | $0.0002 | 11.0 |
| `flash` | 7 | 4% | 0.429 | $0.0019 | 9.0 |
| `fallback` | 1 | 1% | 0.000 | $0.0075 | 25.4 |

## 5. Knowing when it doesn't know (all model configs, per split)

| split | confidence | cases | share | mean score | fully solved | note |
|---|---|---|---|---|---|---|
| dev_tune | High | 102 | 26% | 0.738 | 60/102 |  |
| dev_tune | Medium | 64 | 16% | 0.367 | 16/64 |  |
| dev_tune | Low | 225 | 58% | 0.498 | 74/225 |  |
| holdout | High | 15 | 18% | 0.283 | 0/15 |  |
| holdout | Medium | 16 | 19% | 0.234 | 0/16 |  |
| holdout | Low | 53 | 63% | 0.637 | 26/53 |  |

_**The two splits disagree, so we do not claim calibration.** On dev_tune High beats Low (0.738 vs 0.498, n=102); on the holdout it is the worse bucket (0.283 vs 0.637, n=15). Margin, the main input to the rule, correlates with score at only +0.06 on dev_tune and mean score is flat across all four margin quartiles -- so the dev_tune ordering may itself be chance, and we read the label as weakly informative at best._

## 6. Failure taxonomy — the first thing wrong, per missed scoring point

| first thing wrong | `engine` | `routed` | `routed-reason` | `routed-duel` |
|---|---|---|---|---|
| component wrong | 18 | 13 | 10 | 18 |
| reason wrong | 26 | 21 | 18 | 28 |
| time wrong (> 60 s off) | 20 | 21 | 15 | 20 |
| **total missed** | 64 | 55 | 43 | 66 |

## 7. Headlines

- **Do the models add anything over the engine?** **No** (0.524 engine vs 0.417 routed). The deterministic engine is the product; the models are not paying for themselves. Reported as a negative result.
- **Engine vs the free baseline:** 0.524 vs 0.111, at $0.00 either way.

_Holdout numbers. n=21: a difference of one or two cases is a tie._

<!-- END SUMMARY -->

## Routed vs single model ⟨P2⟩

<!-- P2: the required comparison. Headline sentences, computed not asserted, e.g. "routed reached X
     of single-strong's partial score at Y% of its cost and Z% of its time". If the strong model buys
     nothing, say so plainly -- docs/scoring.md explicitly prefers a defensible negative result. -->

_TODO P2._

**What we already know points one way, and we should say it:** on the 5 cases we ran both ways during
demo selection, the **engine alone scored 5/5 strict while routed scored 3/5** — the strong model
overrode a correct engine answer twice. One documented instance: dev row 0, engine top-1
`shippingservice-1 / container read I/O load` (correct), strong model chose
`emailservice2-0 / container network latency` at margin 0.06, scoring zero. The validator allowed it
because the pick was a legal candidate with a legal reason. So the **override path** deserves its own
row in the routing breakdown: *cases where the model agreed with engine C1* vs *cases where it
overrode*, with accuracy for each. If overriding is net-negative, the fix is a validator rule (the
model may only override when its pick has support comparable to C1's), not a prompt change — and our
confidence rule already marks exactly those cases **Low**.

## Routing breakdown ⟨P2⟩

<!-- P2: % of cases by route (gate / flash / strong / fallback), mean score and $/case per route. -->

_TODO P2._ From the 20-case Docker run: **gate 4, strong 16, flash-only 0, fallback 0, errors 0**.
The gate answers ~20% of cases with **zero tokens**, which is the cheapest accuracy on the curve.

## Knowing when it doesn't know ⟨P2⟩

<!-- P2: accuracy by confidence level with counts, then the abstention framing docs/scoring.md asks
     for: "above confidence T we would abstain on N% of cases, and accuracy on the rest is X times
     higher". We never abstain in the prediction -- a blank and a wrong answer both score zero -- so
     this is reported as an analysis, not as behaviour. -->

_TODO P2._ The confidence rule is fixed and stated in the evidence file for every case: **High** =
margin ≥ 0.35, support ≥ 2, and any model called agreed with the engine; **Low** = margin < 0.15, or
the model overrode the engine, or a fallback/error/deadline skip; **Medium** otherwise.

## Cost and time ⟨P2⟩

_TODO P2 for the per-config table._ Measured facts already in hand, from the judged path:

| Measurement | Value | Limit |
|---|---|---|
| 20 cases, routed, in the container at 2 CPU / 8 GB | **5 min 54 s** (17.6 s/case mean, 37.7 s max) | 20 min |
| Cost, same run | **$0.126** total, $0.0063/case (max $0.0112) | $25/run, $3/case |
| Split of that spend | GLM-5.2 **95%**, GLM-4.7-Flash 5% | — |
| Tokens | 7,451 in / 380 out per case | vs 474 K for a "typical case" that reads the window |
| Peak memory | 1.74 GiB | 8 GB |
| Cases over our own 45 s soft deadline | 0 | — |
| Engine alone, per case | 3.8 s, $0.00 | — |

The token number is the point of the architecture: the model never sees telemetry, only a fact sheet
of ≤ 40 facts, so we spend ~1.6% of the input tokens a context-stuffing agent would.
**Prompt caching:** our fact sheet is byte-stable in structure by design (fixed section order, fixed
legal-reason block), so the repeated scaffolding is cacheable, but **we did not measure cache hits** —
listed under future work rather than claimed.


## What the engine does

ORIGIN answers three questions per case — when the failure started, which component caused it, why —
without a model seeing any telemetry. Stages 0–3 are deterministic Python:

```
0 parse the case   -> window (UTC+8), failure count, which fields are asked
1 load the window  -> only [window start - 60 min, window end], from 12 GB of CSV
2 signals          -> which (component, KPI) series and trace edges left their normal range, and when
3 candidates       -> rank the legal suspects, apply the causal filter, pick legal reasons, render facts
```

A model is asked only at stage 4, and only ever to **choose among candidates the data already
supports** — never to write a timestamp, a number, a component name or a reason.

### 1. Reading only the window

The case window is 30 minutes; the baseline is the 60 minutes before it (the 60 after, if the day
folder before is missing). `trace_span.csv` is 1.3 GB/day and `log_proxy.csv` 2.9 GB/day, so nothing
is ever fully read:

| file | size/day | how it is read |
|---|---|---|
| `metric_node.csv` | 22 MB | fully time-sorted → byte-offset binary search |
| `trace_span.csv` | 1,357 MB | **~10 concatenated time-sorted shards** → find the shard boundaries, binary-search inside each, read only the matching byte ranges (90-minute slice: **0.4 s**) |
| `metric_container.csv`, `metric_service.csv` | 278 MB, 1 MB | grouped by series, not by time → read once per day with `usecols` + categories, cached in-process, then filtered |
| `log_service.csv` | 705 MB | not sorted → one chunked pass per day keeping only error-looking lines, cached |
| `metric_mesh`, `metric_runtime`, `log_proxy` | 259 / 93 / 2,900 MB | never read |

Result: **3.8 s per case mean, 17.9 s max** on a laptop (dev-tune), **4.2 s / 16.6 s** over the
holdout instructions, and inside the judged container **20 cases in 5 min 54 s at 2 CPU / 8 GB with
peak memory 1.74 GiB**. The maxima are all the one-off log pass for the first case of a telemetry day.

Two traps from `docs/data.md`, both handled once at load: every time in the data and in the answers is
**UTC+8** (confirmed: all 55 dev answer times fall inside their window when parsed as UTC+8, and the
answer component's metrics move at that instant, while the same reading ±8 h shows only noise), and
**traces are milliseconds while everything else is seconds** (trace `duration` is microseconds —
confirmed by checking that 99.9% of child spans start inside their parent's duration under that
reading). Every `ts` in the engine is epoch seconds.

### 2. Topology from the names

There is no label metadata in this dataset; the topology is in the strings.
`metric_container.cmdb_id = "node-5.shippingservice-1"` gives pod → node, and stripping a trailing
`-<digits>` gives pod → service. A second deployment of a service (`adservice2-0`) maps to `adservice`
only when `adservice` exists as a service in its own right, so no component name is ever written in
code. Trace spans add who-calls-whom: each span is joined to its `parent_span` in the same trace, and
where the pods differ we record the call with `gap_ms = parent.duration − child.duration`, which is
the time the caller spent waiting that the callee did not spend working — **the only place a network
fault is visible**, and about a quarter of the dev reasons are network faults.

### 3. What counts as "went wrong"

Per (component, KPI) series, and per trace edge (median `gap_ms` per 30 s bucket), a robust z against
the baseline: median for the centre, IQR with a floor for the scale, capped at 50, and the score is
the best value **sustained over k = 2 consecutive samples**, so a one-sample blip can never qualify.
The onset is the first sample of the first sustained breach. Two guards were added after measuring
the first version on real data, where it reported 92–181 "anomalies" per case across 31–43 of 59
components:

1. **Baseline range.** A breach must also leave the baseline's own [min, max] in the anomaly's
   direction. A metric with a tiny IQR that periodically touches a value it has touched all hour is
   not news.
2. **Same time of day.** A breach that already happened at the same clock offset 30 or 60 minutes
   earlier is routine. Every case window in this dataset starts at :00 or :30, and the shop runs jobs
   on that boundary — node network counters and `system.disk.used` jump exactly there. This guard had
   to be "was this normal at this time of day", not "ignore the window start", because the true fault
   can be 12 seconds into the window (the earliest in dev-tune is 0.2 min).

A series that simply stops for ≥ 2 expected intervals is a **disappearance** signal (one per pod, not
one per KPI, so 60 dead series cannot look like 60 independent facts).

### 4. Ranking, and the direction of causality

Each component's score is its strongest signal times that signal's own reason weight (floored at 0.3,
capped at 1 — a noisy KPI that votes for nothing cannot make a component the top suspect), plus
`2·log(1 + support)` for the number of distinct anomalous KPIs or edges. Then structure is applied:

- **A service is the suspect** when ≥ 3 of its pods, and ≥ 75% of them, went wrong within 120 s of each
  other, counting only pods scoring ≥ 40% of the strongest. This matters: **24 of 54 dev answer
  components are bare service names**, and the starter heuristic scores a flat 0.000 on the two
  component-only task types precisely because it can only ever name a pod or a node.
- **A node is the suspect** when ≥ 2 of its pods went wrong around its own onset; its pods are then
  demoted as victims, naming the node in the evidence.
- **A node with exactly one anomalous pod is that pod's symptom**, not its cause. One pod's read-I/O
  storm drags its node's `system.io.*` and `system.cpu.iowait` to a capped z; before this rule the
  node won the top spot on the first dev case and the true pod came 5th.
- **A component that depends on something that went wrong earlier is demoted** (×0.3): its node, or a
  pod it calls whose call-gap went bad more than two samples before its own onset.

### 5. Why — the reason table

A fixed KPI-pattern → reason table per level, first match wins, only legal reasons for that level
(node reasons for nodes, container reasons for pods and services). A signal only votes if it moved in
the direction that means *more* load (`free|usable|avail|idle` down, everything else up) — a falling
CPU load is evidence of change, not of `container CPU load`. Two additions came out of dev-tune:

- **Magnitude rules.** Every container fault drags CPU, memory, threads and file descriptors up
  together, because a stress process starts inside the container. What identifies the injected one is
  absolute size: read-I/O faults push `container_fs_reads_MB` peaks to 4,000–15,000 (under 50 in any
  other fault), write-I/O `container_fs_writes_MB` to ~3,600 (under 0.1 otherwise), CPU faults
  `container_cpu_usage_seconds` to 12–28 (0.5–9.5 otherwise).
- **Delay or damage.** A call-gap anomaly cannot tell added latency from corrupted packets. TCP
  retransmissions at the node can: corrupted or dropped packets get retransmitted, pure delay does
  not. When any node's `tcp.retrans_*` leaves its normal range, call-gap facts vote packet
  corruption / retransmission / loss instead of latency. On dev-tune that signal is present in **3/3
  packet-corruption cases and absent in the latency case**; it lifted the reason-only task type from
  0.214 to 0.357. Three cases is a small sample and we say so.

### 6. Evidence that can be checked

Every fact carries its source file, `cmdb_id`, KPI, the baseline median with its sample count, the
onset and peak with **raw values and epoch timestamps**, so a judge can grep it. Raw values are
printed as the file holds them and, when long, **cut rather than rounded** (trailing `…`), so the
printed digits remain a prefix of the CSV text — a rounded number would not match a grep. Derived
numbers say they are derived. Worked example from the demo case:

```
- F6 · metric_node.csv · node-6 · system.io.w_s — baseline median 0 (60 samples); first outside
  normal at 2022-03-21 03:39:00 (ts 1647805140), value 502.5; …
$ awk -F, '$1==1647805140 && $2=="node-6" && $3=="system.io.w_s"' .../metric_node.csv
1647805140,node-6,system.io.w_s,502.5
```

`tests/test_engine.py::test_grep_metric_facts_against_raw_csv` performs that check automatically for
every metric fact behind every answer, so a rendering change cannot quietly break it.

---

## Fixed parameters and tuning log

Parameters were set before tuning (SPEC "Fixed parameters") and changed **only from dev-tune
results**. The holdout was never scored during tuning; the one thing it was used for is a timing pass
over its instructions.

| # | Change | Why | dev-tune (partial / strict) |
|---|---|---|---|
| 0 | starting point at the CP3 merge | — | **0.539 partial**, 18/49 strict |
| 1 | `ONSET_SHIFT_BY_KIND` = −20 s for metric and disappearance onsets, 0 for trace buckets | A metric sample stamped T reports the minute *ending* at T, so the fault began in (T−60, T]. Chosen on **slack, not hit count**: −20 s and −30 s both put 25/38 time answers inside the 60 s tolerance, but −30 leaves 5 of them within 5 s of the boundary against −20's 2 (median slack 38 s vs 28 s). The judged deployment samples on a different phase, so slack is worth more than the midpoint. +30 s scores 21/38 | 0.539 → **0.554 partial**, 20/49 strict |
| 2 | `EDGE_GAP_VOTES_RETRANS` — damage vs delay (§5) | 3/3 corruption cases show node TCP retransmissions, the latency case does not | 0.554 → **0.5747 partial**, 21/49 strict (42.9%) |
| — | `CAUSAL_DEMOTE` 0.3 → 0.5 | **Rejected.** Gains exactly one case (partial 0.585, strict unchanged) while 0.4 changes nothing and 0.6 loses a different one — a knife edge fitted to one row | kept 0.3 |
| — | service/node promotion thresholds, `SIGNAL_MIN_FACTOR`, `SHARED_CALLEE_BONUS`, `REASON_REST_WEIGHT`, `CAUSAL_EARLIER_S`, `NODE_SINGLE_POD_FRAC` (2 values each) | **All swept, none adopted:** every neighbour of the current value scores the same or worse, so the engine sits at a local optimum rather than on a cliff — the more reassuring of the two for a different deployment | kept |

## Engine failure taxonomy (dev-tune, measured at partial 0.539 / 18-49 strict)

| bucket | cases | detail |
|---|---|---|
| wrong reason | 12 | network group 4 · node group 3 · process termination 2 · other 3 |
| wrong component **level** | 10 | **every** component error was node/pod/service confusion, never an unrelated component — the right family is nearly always found |
| time only | 9 | 4 of them at +75…+109 s, which change 1 addresses |
| wrong count | 0 | the parser has never missed a failure count on any of the 70 dev cases |

## What the engine is blind to

Stated rather than guessed at:

- **`container process termination`** (3/55 dev reasons) is **not visible in this bundle**. For both
  dev-tune cases that have it: no metric series stops or gaps, `container_start_time_seconds` never
  changes, per-pod span counts hold, and `log_service.csv` has no error lines in the window. The
  disappearance rule is implemented and unit-tested; it fires on no dev case.
- **`node disk space consumption`** (4/55): `system.disk.used` on the busiest node swings from 3.6 GB
  to 9.7 GB *within the baseline hour*, so a fault that consumes disk hides inside normal variation.
  Detrending is the obvious next step; it was not attempted before the freeze.
- **The same component failing twice** in one window (1 of 7 multi-failure dev-tune cases): the engine
  answers distinct candidates, so it cannot express "read I/O then write I/O on one service". Left
  alone deliberately — fixing it for one case risks the other six.
- **`metric_mesh`** edge metrics and **`log_proxy`** access logs are never read.

## Honest caveats

- Dev-tune's **partial 0.5747 / strict 42.9%** is **optimistic by construction**: every change above was chosen by looking at
  dev-tune failures. The holdout number is the honest one.
- **n = 21 on the holdout**, so one case is worth ~0.048 of the mean and differences under ~0.1
  between configurations are noise. That is what the repeats are for.
- The judged bundle is **another deployment with different component names**. Nothing in the engine
  names a component: topology comes from string shape, reasons from KPI-name patterns, and
  `grep -rn PLACEHOLDER origin agents eval` is part of the submission check.
- The magnitude rules and the retransmission rule assume the **same fault-injection tooling and the
  same shop**. They are the parts most likely to transfer badly, and the first thing we would revisit
  with more of the organizers' data.

---

## What we would change first

1. **`SERVICE_PROMOTE_MIN_PODS` 3 → 2.** It scores *identically* on dev-tune, and it removes a hidden
   assumption: every service in this bundle has 4 pods, so "at least 3 broke together" can never be
   satisfied by a 2-pod service — and bare service names are 24 of 54 dev answer components. We did
   not ship it because the holdout numbers describe the code we shipped, and a re-run was not
   affordable inside the freeze. It is assumption-reduction, not tuning.
2. **Make the magnitude rules relative rather than absolute.** Comparing a pod's reads to what *any*
   pod normally does would survive a deployment with different container sizes. A first attempt was
   too noisy to adopt in the time available.
3. **Constrain the override path** if the holdout confirms it is net-negative (see "Routed vs single
   model").
4. **Detrend `system.disk.used`** so node disk-space faults stop hiding inside normal variation.
5. **Measure prompt-cache hits** on the stable fact-sheet prefix.

## Honest caveats

- **Dev-tune numbers are optimistic by construction** — every change was chosen by looking at
  dev-tune failures. The holdout number is the honest one.
- **n = 21 on the holdout**: one case is worth ~0.048 of the mean partial score, and `docs/scoring.md`
  says a one-or-two-case difference is a tie. Differences under ~0.1 between configs are noise, which
  is what the repeats are for.
- **Our holdout is a weaker test than the judges' set.** It is 21 unseen *cases* from the *same*
  deployment, same two days, same 42 pods. It tests whether we fitted particular cases. It does not
  test whether we fitted this deployment — and the judged bundle is a different one. The assumptions
  riding on that are named in "What the engine is blind to" and in item 1 above.
- **Not like-for-like with published results**: the 11.34% strict / 17.31% partial baseline covers 335
  cases across three systems; ours is 49 Market cases.
- **The judges run the agent more than once, under undisclosed conditions.** Nothing in the engine
  names a component, a date or a case: topology is parsed from id shape, reasons from KPI-name
  patterns. `grep -rn PLACEHOLDER origin agents eval` is part of our submission check.
