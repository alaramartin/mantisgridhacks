# REPORT.md — engine sections (Person 1, paste-ready)

Person 2 owns `REPORT.md`; these are the sections PLAN assigns to Person 1, written to be pasted in
whole. The working log with the full sweep detail is `docs/engine-tuning.md` (canonical if the two
ever disagree). Every number here is dev-tune (49 cases) or a timing measurement — **no holdout
result is quoted**, because the holdout is scored once, by Person 2, at CP4.

**Two numbers, never mixed.** `score.py` reports a **partial** score — the fraction of a case's scoring points you got (one point per asked field per failure) — and **strict**, the share of cases where *every* point was right. The published baselines in `docs/scoring.md` are quoted both ways (RCA-Agent on Claude 3.5 Sonnet: **11.34% strict / 17.31% partial**, across all 335 OpenRCA cases on three systems, which is not like-for-like with our 49 Market cases). Every number below says which it is.


---

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
