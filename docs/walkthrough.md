# CP4 mutual walkthrough — Person 1's half

Agreement §5: being unable to explain your own code costs Technical Execution marks, and judges ask
both people. This is P1's half written out, in the SPEC's plain-language register, plus the questions
P2 should fire at P1 (and the ones P1 will ask P2). **Read the "say" column out loud, not the "don't
say" one.**

| Don't say | Say |
|---|---|
| robust z-score with an IQR floor | how far outside its normal range a metric went |
| onset | when it first went wrong |
| causal filter | a component is only a suspect if what it depends on looked normal first |
| baseline-range / periodic guard | it has to be unusual *for that time of day*, not just unusual |
| candidate promotion | when every pod of a service breaks together, the service is the suspect, not one pod |

**Say which score you mean.** *Partial* = fraction of a case's scoring points; *strict* = the whole
case right. Engine on dev-tune: **partial 0.5747, strict 21/49 = 42.9%**. Published state of the art
(`docs/scoring.md`): **11.34% strict / 17.31% partial** over 335 cases on three systems — quote it as
"not like-for-like" every time, or a professor judge will do it for you.

## The six things P1 must be able to explain cold

1. **UTC+8.** Every time in the instructions and the answers is shop-local (UTC+8); the telemetry is
   epoch seconds. We parse the window with `tzinfo=UTC+8` and convert once. Proof it is right: all 55
   dev answer times land inside their window under that reading, and the answer component's metrics
   move at that moment, while the same reading ±8 h shows only noise. The starter heuristic reads the
   window as UTC and looks at the wrong half-hour — that is part of why it scores 0.073 partial (1/49 strict on dev-tune).
2. **Milliseconds vs seconds.** Traces are milliseconds and their `duration` is *microseconds*
   (verified: under that reading 99.9% of child spans start within their parent's span, and 100% of
   child durations are shorter than their parent's). Everything else is seconds. We divide once, at
   load, and a test asserts no `ts > 1e11` ever reaches the engine.
3. **Why we only read a sliver.** 12 GB per bundle, 1.3 GB of traces per day. We read the 30-minute
   window plus a 60-minute baseline. `trace_span.csv` turned out to be ~10 concatenated time-sorted
   shards, not one sorted file, so we find the shard boundaries and binary-search inside each: a
   90-minute slice costs 0.4 s. The metric files are grouped by series, not time, so they are read
   once per day and cached. Result: 3.8 s/case, 1.74 GiB peak in the judged container.
4. **What counts as broken.** Median and IQR for the normal range (so the fault cannot inflate the
   scale it is measured against), sustained over two consecutive samples (so a blip never counts),
   plus two guards we added after the first version flagged 92–181 "anomalies" per case: it must leave
   the range the metric held all hour, and it must not be the same thing that happened at the same
   clock time 30 or 60 minutes earlier — every window starts at :00 or :30, and the shop runs jobs
   right there.
5. **Who is the suspect.** Rank by strongest signal × that signal's own reason weight, plus a bonus
   for how many independent things moved. Then: a service whose pods all broke together beats any one
   pod; a node with two or more broken pods beats those pods; **a node with exactly one broken pod is
   that pod's symptom** (one pod's disk-read storm shows up as node I/O, and before that rule the node
   beat the true pod); anything whose dependency broke first is demoted and says so in "Ruled out".
6. **Why, and how the evidence cannot lie.** A fixed KPI-pattern → reason table per level, direction
   aware. Every number in the evidence is copied from a raw row with its file, `cmdb_id`, KPI and
   epoch timestamp, and long values are cut rather than rounded so a grep still matches.
   `tests/test_engine.py` re-greps every metric fact behind every answer against the raw CSV.

## Questions P2 should ask P1

- Why is the baseline the hour *before* the window, and what happens at midnight when that folder
  does not exist? (Answer: fall back to the hour after and note it in the evidence.)
- Why does a metric that doubles not necessarily become a signal? (Baseline range + same-time-of-day
  guards.)
- Why are the answer times shifted 20 seconds earlier, and why not 30? (Slack vs hit count — both
  score 25/38, −30 leaves 5 answers within 5 s of the tolerance boundary, −20 leaves 2.)
- Where does a network fault show up, and what tells corruption from plain latency? (Trace call-gap;
  node TCP retransmissions — 3/3 corruption cases, absent in the latency case.)
- What is the engine blind to? (Process termination, node disk space, the same component twice.)
- Show me one fact and grep it. (See the demo case below.)

## Questions P1 will ask P2

- What exactly does the gate test, and what did it buy in dollars and seconds on the holdout?
- When the strong model disagrees with the engine, who wins, and what does the validator enforce?
- Show me a case where the grounding check dropped model prose, and what the evidence says instead.
- Why thinking OFF on the strong tier, and what is the measured evidence?
- What is the holdout's variance across repeats, and is the routed-vs-single-strong gap bigger than it?
- What happens if the API is down mid-run — what does the evidence file say then?

## Demo case: **row 38** (dev-tune, not holdout)

`task_7` (hard — all three fields asked), and the routed agent gets **all three right**:
`node-6 / node disk write I/O consumption / 2022-03-21 03:39:00` against the answer
`node-6 / node disk write I/O consumption / 2022-03-21 03:39:14`.

Why this one:
- **It escalates** (`route: strong`), so the live run shows the whole pipeline including both model
  tiers, in ~16 s.
- **The confidence is honestly Low** (the top two suspects are 7% apart) *and the answer is right* —
  which is the calibration story in one case: "it tells you when to double-check it, and here it was
  right anyway."
- **Its facts grep cleanly** on one line:
  ```
  awk -F, '$1==1647805140 && $2=="node-6" && $3=="system.io.w_s"' \
    data/Market-cloudbed-1/telemetry/2022_03_21/metric/metric_node.csv
  # -> 1647805140,node-6,system.io.w_s,502.5
  ```
  and the evidence line says `value 502.5` at `ts 1647805140`.
- **"Ruled out" reads like a human wrote it:** "node-4 — first went wrong at 03:41:00 (F3), 2 min
  after node-6."

Backup demo, if the API is slow on the day: **row 25** (`task_7`, all three fields right, answered by
the **gate** with no model call at all, in 2.5 s, High confidence). That one makes the "we only pay
for reasoning when the data is ambiguous" point concretely — zero tokens spent.

Run either with:
```sh
set -a; . ./.env; set +a
python -c "import pandas as pd; q=pd.read_csv('eval/splits/dev_tune.csv'); q[q.row_id==38].to_csv('eval/splits/demo.csv', index=False)"
python run.py --dataset data/Market-cloudbed-1 --queries eval/splits/demo.csv --out out/demo
cat out/demo/evidence/38.md
```

## One finding for P2 before the holdout runs

On row 0 the **engine alone is right** (`shippingservice-1 / container read I/O load`) and the
**routed agent is wrong**: the strong model overrode the engine on a low-margin case (margin 0.06) and
picked `emailservice2-0 / container network latency`, scoring 0. The validator allowed it because the
pick was a legal candidate with a legal reason. Worth checking on the holdout whether "model overruled
the engine below `ESCALATE_MARGIN`" is a net loss — if it is, the fix is a validator rule, not a
prompt change, and the confidence rule already flags exactly those cases as Low.
