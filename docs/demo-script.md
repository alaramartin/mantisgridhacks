# ORIGIN — the engine in plain terms, and the 4-minute demo script

Two parts: **A** is what the engine actually does, written so either of us can explain it cold.
**B** is the minute-by-minute script — what is on screen, what to type, what to say.

---

# Part A — what the engine does, method by method

The engine is stages 0–3: deterministic Python, no AI. It turns "something broke between 09:00 and
09:30" into a ranked list of suspects, each with a reason, a time, and facts you can grep. Six methods.

## 1. Read only the window

**What:** the case gives a 30-minute window. We read that window plus the 60 minutes before it (the
baseline) and nothing else — out of 12 GB per day.

**How:** the files are too big to load. `trace_span.csv` is 1.3 GB/day and turned out to be **~10
concatenated time-sorted shards**, so we find the shard boundaries and binary-search inside each,
reading only the matching byte ranges (a 90-minute slice: 0.4 s). The metric files are grouped by
series rather than by time, so seeking cannot work — those we read once per day and cache in memory.
`log_proxy.csv` (2.9 GB/day) is never read at all.

**Two traps, fixed once at load:** every time in the instructions and answers is **UTC+8**, and
**traces are milliseconds while everything else is seconds** (trace `duration` is microseconds).

**One sentence:** *"It reads half an hour out of twelve gigabytes, by seeking to the right bytes."*

## 2. Decide what "went wrong" means

**What:** for every (component, KPI) series — and every trace edge — decide whether it left its
normal range inside the window, and **when**.

**How:** the baseline hour gives "normal": its **median** as the centre and its **IQR** as the spread
(both robust, so the fault itself can't inflate the scale it's measured against). A sample is a
breach if it's ≥ 3 spreads from the median, and it only counts if **sustained for 2 consecutive
samples** — one blip is noise. The **onset** is the first sample of that run.

**Two guards we added after measuring** (the first version reported 92–181 "anomalies" per case):
1. **Baseline range** — the breach must also leave the [min, max] the series held all baseline hour.
2. **Same time of day** — it doesn't count if the same departure happened 30 or 60 minutes earlier.
   Every case window starts at :00 or :30 and the shop runs jobs exactly there.

**One sentence:** *"Unusual for this metric, and unusual for this time of day, and it has to last."*

## 3. Rebuild the topology from the names

**What:** who runs where, and who calls whom — with no config file and no service registry.

**How:** `metric_container.cmdb_id` is literally `node-6.productcatalogservice-0`, so **pod → node**
is a string split, and stripping a trailing `-<digits>` gives **pod → service**. For calls, each
trace span is joined to its `parent_span` in the same trace; where the two pods differ, that's an
edge, and `gap_ms = parent duration − child duration` is the time the caller spent waiting that the
callee did not spend working. **That is the only place a network fault shows up**, and network faults
are about a quarter of the answers.

**One sentence:** *"The topology is in the names, and the call graph is in the traces."*

## 4. Rank the suspects, and get the direction of causality right

**What:** turn anomalies into a ranked shortlist C1, C2, C3…

**How:** each component scores by its strongest signal (weighted by how diagnostic that KPI is) plus
a bonus for how many independent things moved. Then four structural rules:

- **A service is the suspect** when most of its pods broke together — important, because **24 of 54
  answer components are bare service names**.
- **A node is the suspect** when two or more of its pods broke around the node's own onset.
- **A node with exactly one broken pod is that pod's symptom** — one pod's disk-read storm drags the
  node's I/O metrics to the cap. Before this rule, the node beat the true pod on the very first case.
- **Anything whose dependency broke first is demoted** — its node, or a pod it calls — and the
  demotion sentence appears in "Ruled out".

**margin** = how far C1 leads C2. That single number drives the routing gate later.

**One sentence:** *"The loudest component is usually a victim; we only believe a suspect if what it
depends on looked normal first."*

## 5. Say why — the reason table

**What:** pick one of the **15 legal reasons**, and only ones legal for that level (node reasons for
nodes, container reasons for pods and services).

**How:** a fixed KPI-pattern → reason table, and a signal only votes if it moved in the direction
that means *more* load. Two additions from the data:

- **Magnitude rules.** Every container fault drags CPU, memory, threads and file descriptors up
  together, because a stress process starts inside the container. Only absolute size identifies the
  injected one: read-I/O faults push read-MB into the thousands, CPU faults push CPU-seconds past 10.
- **Damage vs delay.** A slow call can't tell added latency from corrupted packets — but **TCP
  retransmissions at the node** can, because corrupted or dropped packets get retransmitted and pure
  delay doesn't. Present in 3/3 corruption cases on dev-tune, absent in the latency case.

**One sentence:** *"A fixed table from metric name to cause, plus two rules we only found by looking
at the data."*

## 6. Write facts that cannot lie

**What:** every anomaly becomes a numbered fact (F1, F2…) carrying its **source file, cmdb_id, KPI,
baseline median, onset and peak — with raw values and epoch timestamps**.

**How, and the detail that matters:** long raw values are **cut, not rounded** (with a trailing `…`),
so the digits printed stay a prefix of the text in the CSV and a judge's `grep` still matches. A
rounded number would not. `tests/test_engine.py` re-greps every metric fact behind every answer
against the raw file, so a rendering change can't quietly break it.

**One sentence:** *"Every number in the explanation is copied from a row you can go and look at."*

## Then the model, in one paragraph

The engine hands the model **≤ 8 candidates and ≤ 40 facts — about 7 K tokens, against 474 K to read
the window**. The model's whole job is to pick a candidate by its ID and a reason from the legal
list. It never writes a timestamp, a number, a component name or an illegal reason; the validator
enforces that and the answer time always comes from the engine's onset. If the engine's margin is
wide, no model is called at all.

---

# Part B — the 4-minute demo script

**Before you start** (do this while the previous team presents):

```sh
cd ~/Projects/mantisgridhacks
set -a; . ./.env; set +a                      # the key must be in the shell
python run.py --dataset data/Market-cloudbed-1 --queries eval/splits/demo.csv --out out/demo
```

That pre-generates the demo case so a hung API call can never sink the beat. **Then delete it**
(`rm -rf out/demo`) if you intend to run it live — but keep a second terminal tab with
`cat out/demo/evidence/38.md` ready from the pre-run, as the fallback.

**Setup:** terminal font ≥ 18 pt, window maximised, three tabs — **(1)** the repo for the live run,
**(2)** the pre-generated evidence file, **(3)** the raw CSV for the grep. Slides on screen 2.

| Time | On screen | Who | What to say / do |
|---|---|---|---|
| **0:00–0:25** | Slide 1 | P1 | "When one component fails, everything downstream looks broken — the loudest thing is usually a victim, not the cause. The best published agent on this benchmark solves about one case in nine. We're not going to beat that by reading more telemetry: it's twelve gigabytes a day, forty-two pods, nine million spans. Nobody reads that at three in the morning." |
| **0:25–0:55** | Slide 2 (`pipeline.png`) | P1 | "ORIGIN reads only the half-hour in question. A deterministic engine rebuilds who runs where and who calls whom, ranks the legal suspects, and writes down the facts behind each one. **Then** — and only if it isn't sure — it pays a model to choose between them. The model never sees telemetry; it sees forty facts, about seven thousand tokens, against four hundred and seventy-four thousand to read the window." |
| **0:55–1:45** | **Terminal, tab 1** — run it live | P1 | Type: `python run.py --dataset data/Market-cloudbed-1 --queries eval/splits/demo.csv --out out/demo`. While it runs (~16 s), narrate: "It's reading the window by byte offset, scoring every series against the hour before, rebuilding the topology from the metric ids and the call graph from trace parent-child pairs. This case is ambiguous, so it will escalate to the strong model." When it prints, read the answer: "**node-6, node disk write I/O consumption, 03:39**. The answer key says 03:39:14." |
| **1:45–2:45** | **Terminal, tab 2** — `cat out/demo/evidence/38.md` | P2 | **Never cut this beat.** "Four sections. The answer. The confidence — it says **Low**, and why: the top two suspects are seven percent apart. It was right anyway, and we'd rather it tell you when to double-check it. Then the evidence: every fact has its file, its component, its KPI, and an epoch timestamp." Scroll to F6, then **tab 3**: `awk -F, '$1==1647805140 && $2=="node-6" && $3=="system.io.w_s"' data/Market-cloudbed-1/telemetry/2022_03_21/metric/metric_node.csv` → `1647805140,node-6,system.io.w_s,502.5`. "That's the number from the explanation, in the raw file. Not paraphrased — copied." Then read one "Ruled out" line aloud: "node-4 — first went wrong two minutes after node-6." |
| **2:45–3:35** | Slide 3 (`topology.png` + table) | P2 | "Nothing in that picture is configured — pod-to-node is parsed from the metric ids, pod-to-pod from the traces. Here's the eval: a 21-case holdout we never tuned on, ⟨N⟩ configurations, repeats for variance." Then the numbers, and **the honest line**: ⟨routed vs single-strong: whichever way it fell⟩. If the strong model bought little: "GLM-5.2 is ninety-five percent of our spend and bought us ⟨X⟩ — that's a result, and we're reporting it rather than hiding it." |
| **3:35–4:00** | Slide 3 | P1 | "Where it fails: process termination is invisible in this telemetry — no series stops, no restart, no error log — so we say so instead of guessing. Node disk-space faults hide inside a metric that swings by six gigabytes an hour. And our numbers are from one deployment; yours is another, which is exactly why nothing in the engine hardcodes a component name. Thank you." |

## If something goes wrong

| Problem | Do this |
|---|---|
| The live run hangs or the API is slow | Keep talking — "it's escalating to the strong model" — and after ~25 s switch to tab 2 and the pre-generated file. Never wait in silence. |
| The run finishes with `route: engine_only` or `fallback` | Say so plainly: "no model was reachable, so that's the engine's own answer." **Never** present a fallback as the model deciding. |
| Demo case answers wrong on the day | Say it: "it got this one wrong — here's what it ruled out and why, which is the part an on-call engineer uses." Then move to the eval. That is a *better* moment than a lucky one. |
| Asked "why a model at all, if the engine is this good?" | "That's exactly what our eval measures. ⟨the number⟩. The gate means we only pay when the evidence is ambiguous, and on this case it was." |
| Asked about overfitting | "Our 21-case holdout was never tuned on — but it's the same deployment. The assumptions we'd worry about on yours are the absolute magnitude thresholds and the pods-per-service count, and both are written up in the report." |
| Out of time at 3:30 | Cut the last beat, not the evidence beat. The evidence *is* the project. |
