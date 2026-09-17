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

# Part B — how to demo it, and the 4-minute script

## How the demo works, physically

**It is a terminal demo, live on screen, plus three slides.** There is no UI — Track 1 is a headless
agent (`docs/scoring.md`: *"There's no interface dimension… Track 2 is the visualization track"*), and
`docs/submission.md` tells you what a good headless demo looks like: *"Run a case live…, open the
`evidence/` file it just wrote, and walk through what it ruled out. Then show your eval."* That is
exactly the shape below.

**Screen layout.** Slides on the projector for beats 1, 2 and 5; the terminal full-screen for beats
3 and 4. Terminal font **≥ 18 pt**, window maximised, light background if the room is bright.

**Three terminal tabs, opened and `cd`'d before you start:**

| Tab | Purpose | Pre-typed command (don't run yet) |
|---|---|---|
| **1** | the live run | `python run.py --dataset data/Market-cloudbed-1 --queries eval/splits/demo.csv --out out/demo` |
| **2** | the evidence file | `cat out/demo_backup/evidence/38.md` |
| **3** | the grep into raw telemetry | `awk -F, '$1==1647805140 && $2=="node-6" && $3=="system.io.w_s"' data/Market-cloudbed-1/telemetry/2022_03_21/metric/metric_node.csv` |

**Insurance, run once before you present:**

```sh
cd ~/Projects/mantisgridhacks
set -a; . ./.env; set +a                 # nothing reads .env for you
python run.py --dataset data/Market-cloudbed-1 --queries eval/splits/demo.csv --out out/demo
cp -r out/demo out/demo_backup           # tab 2 points at the BACKUP, so a live re-run can't destroy it
```

**Verified on the shipped configuration:** route `duel`, confidence `Low`, answer
`node-6 / node disk write I/O consumption / 2022-03-21 03:39:00` against the key's `03:39:14`,
**21 s**, 1,469 in / 140 out tokens, no errors. The evidence file is **ASCII-folded**, so fact lines
read `F6 - metric_node.csv - node-6 - system.io.w_s -- …` (a `-`, not a `·`).

## The script

| Time | On screen | Who | What to say / do |
|---|---|---|---|
| **0:00–0:25** | Slide 1 | P1 | "When one component fails, everything downstream looks broken — the loudest thing is usually a victim, not the cause. The best published agent on this benchmark fully solves about one case in nine. And it's twelve gigabytes a day, forty-two pods, nine million spans — nobody reads that at three in the morning." |
| **0:25–0:55** | Slide 2 — `pipeline.png` | P1 | "ORIGIN reads only the half-hour in question. A deterministic engine scores every metric against the hour before, rebuilds who-runs-where from the metric ids and who-calls-whom from the traces, and ranks the legal suspects. **Then**, only if it's genuinely torn, it pays a cheap model to choose between its top two. The model never sees telemetry — forty facts, about seven hundred tokens." |
| **0:55–1:45** | **Tab 1**, live | P1 | Run it. **It takes ~21 s**, so narrate: "It's seeking to the right bytes rather than loading the file, scoring each series against its own baseline, building the call graph from trace parent-child pairs. This case is ambiguous, so it will consult the model — you'll see `route: duel`." When it prints: "**node-6, node disk write I/O consumption, 03:39.** The answer key says 03:39:14, and the tolerance is sixty seconds." |
| **1:45–2:45** | **Tab 2**, then **tab 3** | P2 | **Never cut this beat — evidence outweighs accuracy in the rubric.** "Four sections. The answer. The confidence — it says **Low**, and tells you why: the top two suspects are seven percent apart. It was right anyway, and we'd rather it tell you when to double-check it. Then the evidence, where every fact carries its file, its component, its KPI and an epoch timestamp." Scroll to **F6**, then tab 3: the `awk` returns `1647805140,node-6,system.io.w_s,502.5`. "That's the number from the explanation, sitting in the raw CSV. Not paraphrased — copied. A rounded number wouldn't match, so we cut long values instead of rounding them." Then read one ruled-out line: "node-4 — first went wrong two minutes after node-6." |
| **2:45–3:35** | Slide 3 — `holdout_table.png` + `topology.png` | P2 | "Twenty-one held-out cases we never tuned on. The engine alone gets 0.52 partial, seven of twenty-one fully solved — against the starter baseline's 0.11 and one. **Now the honest part.** We *intended* the GLMs to improve on that. Full escalation to GLM-5.2 made it **worse** — 0.42, five of twenty-one, for a hundred and fifteen times the cost. So we ship the restricted version: one cheap call, top two only, only when the engine is torn. Same accuracy, thirteen hundredths of a cent for a twenty-case run." Then `topology.png`: "and none of this graph is configured — it's parsed out of the metric ids and the traces." |
| **3:35–4:00** | Slide 3 | P1 | "Two findings we didn't expect. First, we tested our *own* uncertainty signal: when the engine says it's unsure, it's barely more likely to be wrong — correlation of 0.17. So 'call a model when unsure' aims at the wrong cases, which is why escalation didn't pay. Second, an override costs three scoring points, not one, because the timestamp follows the reason. Next we'd give the model less authority rather than more context, and hunt for a trigger that actually predicts correctness. Both are in the report. Thank you." |

## If something goes wrong

| Problem | Do this |
|---|---|
| The live run hangs or the API is slow | Keep narrating — "it's consulting the model" — and at ~30 s switch to **tab 2** (the backup). Never wait in silence. |
| It prints `route: engine_only` or `gate` | Say so plainly: "this one the engine settled on its own, so no model was called — that's the gate, and it's four of twenty cases." That *is* the design, not a failure. |
| It prints `route: fallback` | "No model was reachable, so that's the engine's own answer." **Never** present a fallback as the model deciding. |
| The demo case answers wrong on the day | Say it: "it got this one wrong — here's what it ruled out and why, which is the part an on-call engineer actually uses." Then move to the eval. That is a better moment than a lucky one. |
| "Why use a model at all, if the engine is as good?" | "That's what our eval measures, and the answer is: barely. We ship the smallest amount of model involvement the evidence supports, and we report the negative result rather than hiding it. `docs/scoring.md` says a defensible negative result beats an undefendable positive one — this is ours." |
| "Isn't 33% strict suspiciously high?" | "It's 21 cases from one deployment; the published 11% is 335 cases across three systems. Not like-for-like, and one case moves us five points. The holdout was never tuned on, and it landed within 0.05 of our tuning split, which is the check we'd want." |
| "How do you know you didn't overfit?" | "Two ways. The 21 holdout cases were fixed by a hash rule before any run and never scored during tuning. And we rejected changes that moved a single case — the tuning log lists what we rejected and why." |
| Out of time at 3:30 | Cut the last beat, never the evidence beat. |

---

# Part C — the slides (3 of them) and the figures

All figures are committed in **`docs/figures/`** and regenerate with
`PYTHONPATH=. python scripts/make_figures.py --row 38`.

| Figure | File | Use |
|---|---|---|
| **Pipeline flowchart** | [`docs/figures/pipeline.png`](figures/pipeline.png) | Slide 2, full width |
| **Holdout comparison table** | [`docs/figures/holdout_table.png`](figures/holdout_table.png) | Slide 3, top |
| **All 70 cases, split by what we tuned on** | [`docs/figures/all70_table.png`](figures/all70_table.png) | Q&A: use it when another team quotes a 70-case number. Ours is **0.559 partial / 28-70 strict** for the engine, **0.524 / 26-70** for the shipped config, against the starter's **0.073 / 2-70** |
| **Topology graph** | [`docs/figures/topology.png`](figures/topology.png) | Slide 3, bottom — the graph visual |
| **Anomaly + suspects** | [`docs/figures/signal.png`](figures/signal.png) | Spare: use if asked how anomalies are detected |
| **Accuracy vs cost** | [`docs/figures/cost.png`](figures/cost.png) | Spare: alternative to the table on slide 3 |

**Keep the slides nearly empty — the talking is in Part B, not on the screen.**

### Slide 1 — title
```
ORIGIN
Root cause analysis from telemetry alone

Track 1 · [both names]
```

### Slide 2 — how it works
```
[docs/figures/pipeline.png, full width]
```
Nothing else. The caption is inside the image.

### Slide 3 — the numbers and the graph
```
[docs/figures/holdout_table.png, top two-thirds]

[docs/figures/topology.png, bottom third]
```
If both won't fit legibly, put `holdout_table.png` on slide 3 and `topology.png` on a 4th slide — the
table is the one that must be readable from the back of the room.

### One-liners worth having on the tip of your tongue
- **The pitch:** "We don't let the model make up evidence. We let it choose between suspects the data
  already supports — and only when the data is genuinely ambiguous."
- **The negative result:** "We built the routing, measured it, and it made things worse. So we shipped
  the restricted version and reported the finding."
- **The uncertainty finding:** "Our own confidence signal barely predicts whether we're right — 0.17
  correlation. That's a problem for escalation routing generally, not just for us."
- **The honesty line:** "Twenty-one cases, one deployment. The published number is 335 cases across
  three systems. Not the same comparison."
