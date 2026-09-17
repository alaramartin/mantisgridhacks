# Track 1 starter

The submission requirements, a baseline that runs for free, an example that calls
the models, and a scorer. Read `run.py` — it's short, and it's exactly what we
execute.

```
run.py          the submission requirements. Replace the agent, not this file
score.py        score yourself against the dev split
llm.py          a Featherless client that counts tokens per model
cost.py         turns those token counts into dollars
Dockerfile      how we build your submission
agents/
  heuristic.py  a baseline with no model in it. Beat this on day one
  routed.py     an example that routes calls across the GLM family
```

## Five minutes to a scored run

```bash
python run.py --dataset ../data/Market-cloudbed-1 \
              --queries ../data/Market-cloudbed-1/dev/query_dev.csv \
              --out ../out/dev

python score.py --predictions ../out/dev/predictions.csv \
                --queries ../data/Market-cloudbed-1/dev/query_dev.csv
```

That costs nothing and takes under a minute. It is the floor.

## What you submit

```
predictions.csv        row_id, prediction
evidence/<row_id>.md   one per case
```

`predictions.csv` goes to OpenRCA's own evaluator, unchanged. `evidence/` is read
by humans and is worth **35% of your grade against accuracy's 20%** — an
explained wrong answer beats a bare right one.

### The key-order trap

The evaluator's regex requires the keys in this order — datetime, component,
reason. Reorder them and it matches nothing and scores zero **silently**:

```json
{"1": {"root cause occurrence datetime": "...",
       "root cause component": "...",
       "root cause reason": "..."}}
```

Use `format_prediction()` in `run.py` and this cannot happen to you. Run
`scripts/validate_submission.py` before you submit; it checks for exactly this.

### Two more rules that cost whole cases

**Get the failure count right.** The instruction tells you how many failures are
in the window. If your JSON has a different number of objects, the case scores
zero however good each answer is.

**Always guess.** Blank and wrong both score zero, so a guess is free upside.
Abstain in your *evidence*, not in your prediction — "I could not separate these
two candidates, here is why" is worth marks. An empty prediction is not.

## Writing an agent

Any module exposing `solve(instruction, dataset_dir, ctx) -> Solution`:

```python
from run import Solution, format_prediction

def solve(instruction, dataset_dir, ctx):
    ...
    return Solution(
        prediction=format_prediction([
            {"datetime": "2022-03-20 09:02:00",
             "component": "adservice-0",
             "reason": "container CPU load"}]),
        evidence="## What I looked at\n...",
        usage=llm.usage)       # tokens per model, from llm.LLM
```

Then `--agent agents.yours` — and when it's your submission, make it `run.py`'s
default `--agent`, because we run `run.py` without the flag. `run.py` writes after every case, so a run that dies
at case 60 keeps the first 59, and `--resume` picks up where it stopped.

## The routed example

`agents/routed.py` shows the plumbing, not a good agent. On top of the baseline's
ranking it makes three calls per case: a cheap model reads the question, a strong one
picks the root cause from the ranked candidates, and a cheap one writes the evidence
file. Each tier names a fallback model, so a busy provider does not end the run.
It checks the pick against the data and keeps the baseline's answer if a call fails.

```bash
export FEATHERLESS_API_KEY=<your key>
make dev AGENT=agents.routed                           # routed
RCA_MODEL=zai-org/GLM-5.2 make dev AGENT=agents.routed # every call on one model
make cost                                              # dollars per case and per model
```

That pair — routed against a single model — is the minimum comparison your eval
needs. `run.py` writes the tokens each model used to `out/dev/usage.jsonl`; `cost.py`
prices them at the table in `docs/models.md`, which is the table we price your judged
run at.

## The baseline, and why it is bad

`agents/heuristic.py` has no model in it. It parses the time window, computes a
robust z-score for every `(component, kpi)` series against the rest of the day,
ranks components by their strongest anomaly, and keyword-matches the winning KPI
to a reason.

On all 70 cases of `Market/cloudbed-1`:

```
mean score   0.073
fully solved 2 / 70
easy  0.083   middle 0.060   hard 0.075
```

**It solves almost nothing outright.** It exists so you know what free looks like. Where
it is obviously weak, and none of this is subtle:

- **It never opens a log or a trace.** Roughly half the signal, untouched.
- **It has no notion of causality.** Twelve components go anomalous together and
  it takes the loudest, which is usually a symptom rather than the cause.
- **The reason is a keyword match**, not an inference.
- **The time is the peak of one series** — when the symptom was largest, not when
  the fault began.

If your agent cannot beat 0.073, the model is not adding value and you want to
know that on day one.

## Scoring honestly

All 70 cases come with answers, and we score you on a different deployment of the
same system. **Tune against all 70 and your number here is optimistic** — hold some
back, or say in your writeup that it's optimistic.

`score.py` breaks results down by difficulty and task type. Report it that way.
An agent that only localises in time looks nothing like one that closes `task_7`,
and a single mean hides the difference.
