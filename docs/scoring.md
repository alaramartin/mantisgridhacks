# How it's scored

What we evaluate:

- **Accuracy** on cases your agent hasn't seen
- **Evidence and explainability** — can you show why?
- **Evaluation quality** — your harness and your comparisons
- **Cost efficiency** — dollars spent per case, alongside accuracy

How much each is worth is in the participant agreement, which is the document that governs.

Ties go to evidence, then to how honestly you state uncertainty.

**There's no interface dimension.** Your agent runs headless and writes files; nobody
watches it work. (Track 2 is the visualization track.)

## Accuracy vs cost

Neither wins on its own. **Aim for a defensible point on the accuracy-vs-cost curve**:
an agent that gets most of the accuracy for a fraction of the cost is worth more than one
that buys an extra point at any price. A difference of one or two correct cases is
treated as a tie. And an agent that's cheap because it answers nothing scores zero on
accuracy and can't score above 2/5 on cost.

## How good is good?

The published results on this benchmark, all 335 cases:

| Method | Model | Strict | Partial |
|---|---|---|---|
| **RCA-Agent** | **Claude 3.5 Sonnet** | **11.34%** | **17.31%** |
| RCA-Agent | GPT-4o | 8.96% | 17.91% |
| Prompting (Oracle) | Gemini 1.5 Pro | 7.16% | 23.58% |
| Prompting (Balanced) | Gemini 1.5 Pro | 6.27% | 24.18% |
| RCA-Agent | Gemini 1.5 Pro | 2.69% | 6.87% |

**The state of the art gets about one case in nine.** Most of your answers will be
wrong, so build for that. The *Oracle* rows were handed the relevant metrics and still
scored 7% — knowing where to look isn't the hard part; reasoning about what you find is.

That 11.34% is Claude 3.5 Sonnet; the same agent on Llama 3.1 scored 3.28%. Today's open
models are far stronger than 2025's, but nobody yet knows where GLM lands here.

## How accuracy is measured

On **20 cases**, the same 20 for every team, from a different deployment of the same
system — one you do not have. They cover every task type, and include every hard case
that deployment has. We don't say which cases, or how many of each kind, until
afterwards. Scored with the benchmark's own `main/evaluate.py`,
unchanged, reported as **strict** and **partial**, and per task type. It has sharp edges, and each of these gives you zero on
a correct diagnosis:

- **Wrong number of failures → the whole case scores zero.** The instruction states how
  many failures are in the window. Emit exactly that many objects.
- **Keys out of order → zero.** The evaluator reads your answer with a regex, not a JSON
  parser, and expects datetime, then component, then reason. No newlines in values.
- **Exact string match.** `shippingservice-1`, not `shippingservice` or
  `pod/shippingservice-1`; `container read I/O load`, exactly. Constrain your output to
  the names in the data (`docs/data.md` lists the reasons).
- **Timestamps are UTC+8, with a 60-second tolerance.** Parse in your local timezone and
  every answer is hours off.

Multiple failures can be listed in any order — the evaluator tries every ordering. Only
the count will sink you.

## Never abstain in the answer. Always be honest in the explanation.

**Always emit a best guess.** A wrong answer and a blank one both score zero, so
guessing strictly dominates — and `reason` is effectively multiple choice, so a narrowed
guess has real odds.

**Then say how sure you are.** Evidence is worth more than accuracy, and *"I'm not sure,
and here's exactly why"* scores full marks there:

> `shippingservice-1` — but this is weak. Three services showed correlated latency and I
> couldn't separate them; I picked this one because its I/O moved first by ~4s. If that
> ordering is sampling noise, `emailservice-0` is equally likely. Node metrics were flat,
> so I ruled out the node layer.

We score **calibration**: confidently wrong is penalised harder than uncertain and close.
A shot in the dark and a narrowed hypothesis are different — say which is which.

## How cost is measured

**In dollars and in time.** Both are ours to measure — nothing for you to report.

**Dollars** are metered on every call your agent makes, priced at the table in
`docs/models.md`. We look at dollars per case (the main number), dollars per correct
answer, and the spread — one case costing 40× the median usually means an agent with
no stopping condition.

**Time** is wall-clock, per case and across the run. An answer that takes an hour is a
different product from the same answer in five minutes, and on-call is where this
track's work would actually land. The 10-minute limit is a floor on acceptable, not the
thing being measured.

The two usually move together, and for the same reason: output tokens on an expensive
model are both the priciest and the slowest thing an agent does, because they are
generated one at a time. An agent that sends its long generation — writing up the
evidence, say — to a cheap model while keeping the expensive one for the short
reasoning step pays less *and* finishes sooner. That is one decision buying both.

What moves you up: **routing that measurably saves money and time without losing
accuracy**, compared against running everything on one model. So do caching of the parts that repeat
every case (schema, tool definitions, scaffolding), cheap triage before expensive
reasoning, and stopping early when the evidence is conclusive — each with before-and-after
numbers, not an assertion.

Report seconds alongside dollars in your own eval. If a change saved money and cost
time, say so — we would rather read that trade-off than not see it.

## Your eval

At least **two configurations compared** — and with routing, the natural pair is **your
routed agent against the same agent on a single model**. For each: accuracy, dollars per
case, time per case, and the variance across repeat runs. If the top model is no better
than the cheapest, say so and show it — a negative result you can defend is worth more
here than a positive one you can't.

Worth doing, none required:

- **Where it fails.** Group your errors. Worse on node faults than pod faults? Blind to
  network faults? An honest failure taxonomy is worth more than two points of accuracy.
- **Knowing when it doesn't know.** Report it as a result — *"above confidence T we'd
  abstain on 40% of cases, and accuracy on the rest is 3×"* — not by leaving answers blank.

## Score yourself

`make validate` checks the output shape. `make dev` then `make score` runs your agent over
all 70 cases and scores them with the same evaluator (`make dev N=20` for the first 20, at
a fraction of the cost). We score you on a different deployment of the same system, so
your number here is an estimate — the gap between it and ours is worth reporting.

## The answers are public — here's what we do about it

OpenRCA is on GitHub and its answers are a download away. So:

- **You submit an agent, not predictions.** We run it.
- **We score you on a deployment you don't have**, and we don't say which of its cases
  until afterwards. The failures are the same kinds, the components are not the same
  components, and the answers to *these* cases are not in the bundle you downloaded.
- **We run your agent more than once, under conditions we don't describe**, to
  establish that your score came from reading the telemetry rather than from anything
  carried in. If it did, you will never notice this happening. We publish what we find
  and we accuse nobody — a gap can also mean an agent leaned on a naming convention,
  which is a real finding about the agent rather than about the team.
- **Your run is sandboxed.** No answer files on the machine, and no route out of the
  container except the model endpoint in `FEATHERLESS_BASE_URL`.

And accuracy is only 20%. A lookup table can't explain itself or show an eval — it fails
the other 80% on its own.
