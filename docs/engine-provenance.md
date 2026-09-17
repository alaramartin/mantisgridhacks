# Where each engine method comes from

The SPEC has a document-level source list; this is the per-method version, because "why does your
engine do *that*?" is a fair question and the answers differ a lot. Five kinds of provenance:

| tag | meaning |
|---|---|
| **OFFICIAL** | stated in the organizers' docs (`docs/data.md`, `docs/scoring.md`, `docs/models.md`) |
| **STARTER** | MantisGrid's starter code, under `LICENSE-MANTISGRID` |
| **PLANNED** | our own design, written into SPEC.md / PLAN.md before any code (AI-assisted planning session; see the AI disclosure) |
| **STANDARD** | ordinary statistics / systems practice, not invented here and not novel |
| **MEASURED** | derived today from the real data, on the dev-tune split only, because the planned version demonstrably did not work. Each row says what the measurement was |

Nothing in the engine comes from the dev answers themselves beyond what is logged in
`docs/engine-tuning.md`, and no component name appears in any of it.

## Stage 0 — parse the case (`origin/case.py`)

| Method | Provenance |
|---|---|
| Window regex (month name, day, year, `HH:MM to HH:MM`, optional second date) | **STARTER** — same shape as `agents/heuristic.py::parse_window` |
| Reading that window as **UTC+8** | **OFFICIAL** (`docs/data.md` traps) — and verified by us: all 55 dev answer times fall inside their window under this reading, with sharp metric changes at the answer time and only noise ±8 h. The starter's own parser reads it as UTC, which is part of why it scores 0.073 |
| Failure-count words, incl. `a failure` / `a single failure` | **STARTER** list, extended **MEASURED** — checked against all 70 instructions and all 70 answer counts |
| Which fields are asked, read from the **last sentence only** | **MEASURED** — earlier sentences mention fields that are not being asked for; the last sentence is the request. Verified: one `asks` pattern per task type, matching `docs/data.md`'s table on all 70 |

## Stage 1 — load only the window (`origin/timeslice.py`, `origin/load.py`)

| Method | Provenance |
|---|---|
| Read `[window − 60 min, window end]`; baseline = the hour before, falling back to the hour after | **PLANNED** (check-in facts: each telemetry day is complete, the window is 30 min) |
| Byte-offset binary search over a time-sorted CSV | **STANDARD** — binary search on a sorted file, no more than that |
| Splitting a file into **sorted runs first**, then searching inside each | **MEASURED** — `trace_span.csv` is ~10 concatenated time-sorted shards, not one sorted file (found by sampling timestamps at 1,024 byte offsets; 64 probes hid the structure). A 90-minute slice costs 0.4 s |
| Reading the metric files **once per day** into an in-process cache instead of seeking | **MEASURED** — `metric_container` / `metric_service` are grouped by series, not time (~250–500 runs), so seeking cannot work |
| ms → s for trace timestamps; µs → ms for trace `duration` | **OFFICIAL** (traces are ms) + **MEASURED** for the duration unit: under a µs reading, 99.9% of child spans start inside their parent's duration and 100% of child durations are shorter |
| Topology from names: `node-6.pod-1` → pod on node; strip `-<digits>` → service | **PLANNED** ("the topology is in the names") + **OFFICIAL** cmdb_id formats. The `<name>2-0` → `<name>` rule is **MEASURED** (a second deployment per service exists) and never hardcodes a name |
| Call edges: join each span to its `parent_span`, keep cross-pod pairs, `gap_ms = parent.duration − child.duration` | **PLANNED**, and the concept is **STANDARD** span-tree analysis. `gap_ms` is the caller's wait that the callee did not spend working — the only place a network fault appears (**OFFICIAL**: "network faults show mainly in traces") |
| Only parents with exactly one cross-pod child get a `gap_ms` | **PLANNED** — with two children the parent's wait cannot be attributed to one of them |

## Stage 2 — what counts as an anomaly (`origin/anomaly.py` by P2, `origin/signals.py`)

| Method | Provenance |
|---|---|
| Median + IQR as centre and scale ("robust z") | **STANDARD** — robust statistics; the fault cannot inflate the scale it is measured against |
| A floor under the scale (IQR, a fraction of \|median\|, the series' own smallest step) | **PLANNED** — container metrics are often flat to the sampling resolution, and a zero IQR makes every quantisation step an infinite z |
| **Sustained** over k = 2 consecutive samples, onset = first sample of that run | **PLANNED**; **STANDARD** in alerting (the "for duration" idea) — a one-sample blip is noise |
| Zero-baseline rule (a flat-zero counter is judged on whether it moved and for how long) | **PLANNED** — "how many sigma" is meaningless with no scale |
| **Baseline-range guard**: a breach must also leave the [min, max] the series held all baseline hour | **MEASURED** — without it the engine reported 92–181 "anomalies" per case across 31–43 of 59 components, mostly periodic spikes with a tiny IQR |
| **Same-time-of-day guard**: not a fault if the same departure happened 30 or 60 min earlier | **MEASURED** — every case window starts at :00 or :30 and the shop runs jobs there; node network counters and `system.disk.used` jump exactly at the boundary. It had to be "unusual *for this time of day*" rather than "ignore the window start", because the earliest true fault in dev-tune is 12 s into the window |
| Disappearance (a series that stops for ≥ 2 expected intervals) | **PLANNED** — intended for process termination. **It fires on no dev case**; see the blind spots in `docs/report-engine-sections.md` |
| Trace edges bucketed at 30 s, scored the same way | **PLANNED** |

## Stage 3 — ranking, causality, reasons (`origin/candidates.py`, `origin/facts.py`)

| Method | Provenance |
|---|---|
| Candidate score = strongest signal + `2·log(1 + support)` | **PLANNED**; the log is **STANDARD** diminishing returns on corroborating signals |
| **Signal weight factor** (a signal counts by its own reason weight, floored at 0.3) | **MEASURED** — `container_network_receive_MB` and `system.net.*` are the noisiest series in the bundle and were winning cases while voting for nothing |
| **Causal filter**: demote a component whose node, or a pod it calls, went wrong earlier | **PLANNED**. Kin in the literature: fault propagation along the dependency graph, and the "grounding then verification" shape of **DiagGuard** ([arXiv:2608.21310](https://arxiv.org/abs/2608.21310), which raised Acc@1 from 43.5% to 52.5% by surveying evidence before localizing and auditing afterwards — verified against the paper) |
| Node promotion (≥ 2 of its pods broke around its own onset) | **PLANNED** |
| **A node with exactly one anomalous pod is that pod's symptom** | **MEASURED** — one pod's read-I/O storm drags its node's `system.io.*` and `system.cpu.iowait` to a capped z. Before this rule the node won the top spot on the very first dev case and the true pod ranked 5th. Reinforced by a second measurement: only node-5 (6 pods) and node-6 (36 pods) host containers at all |
| **Service-level candidates** (most of a service's pods breaking together ⇒ the service) | **MEASURED** at CP1 — **24 of 54** dev answer components are bare service names, which is also why the starter heuristic scores a flat 0.000 on the component-only task types: it can only ever name a pod or a node. The promotion thresholds (≥ 3 pods, ≥ 75%, ≥ 40% of the strongest) are **MEASURED** on dev-tune |
| Reason table (KPI pattern → legal reason, per level) | **PLANNED** template, **MEASURED** patterns — rewritten against the real 64 container / 59 node `kpi_name` values |
| Direction-aware votes (only a move toward *more* load votes) | **MEASURED** — a falling CPU load was voting for `container CPU load` |
| Reason score = best vote + `2·log(1 + other votes)`, not the sum | **MEASURED** — summing let a family with many KPIs (memory has ~10) outvote the injected fault |
| **Magnitude rules** (read/write MB ≥ 1000, CPU seconds ≥ 10) | **MEASURED** — every container fault drags CPU, memory, threads and fds up together because a stress process starts in the container; only absolute size separates them. The most deployment-specific rule we have, and flagged as such |
| **Damage vs delay** (node TCP retransmissions switch call-gap votes from latency to corruption/retransmission/loss) | **MEASURED** — present in 3/3 dev-tune corruption cases, absent in the latency case. Physically: corrupted or dropped packets get retransmitted, added delay does not. Small sample, stated as such |
| Answer time = onset of the signal supporting the chosen reason, shifted −20 s | **MEASURED** — a sample stamped T reports the minute ending at T. Chosen on **slack** rather than hit count: −20 and −30 both put 25/38 time answers inside the 60 s tolerance, but −30 leaves 5 of them within 5 s of the boundary |
| Multi-failure answers need onsets > 5 min apart | **PLANNED** |
| Fact line: file · cmdb_id · KPI · baseline median · onset · peak, with raw values and epoch timestamps | **PLANNED** (the SPEC evidence example) + **OFFICIAL** ("evidence not in the data scores zero") |
| Raw values **cut, never rounded**, with a trailing `…` | **MEASURED** — a rounded value does not match a `grep` of the CSV, which is the entire point of the fact line |

## Stages 4–6 — the model, the validator, the evidence

Person 2's half (`origin/router.py`, `validate.py`, `evidence.py`, `agents/origin.py`). The gate and
escalation thresholds are **PLANNED**; the thinking-off decision, the model tiers and the
`llm.py` `reasoning` patch are **MEASURED** (`docs/model-findings.md`). The scoring rules the
validator protects against — exact count, key order, exact strings, 60 s tolerance — are **OFFICIAL**
(`docs/scoring.md`, "the evaluator's sharp edges").

## The dataset and the evaluator

`Market-cloudbed-1` and `score.py` are **OpenRCA** (ICLR 2025,
<https://github.com/microsoft/OpenRCA>); the evaluator is vendored unchanged and never edited, so our
numbers and the published ones are produced by the same code. The published baselines we compare
against (RCA-Agent on Claude 3.5 Sonnet: 11.34% strict / 17.31% partial) are from `docs/scoring.md`'s
own table, measured on all 335 OpenRCA cases across three systems — **not like-for-like** with our
49 Market cases, and we say so wherever we quote it.
