# Track 1 — Root cause analysis

*Why did this break?* Build an agent that finds the root cause of real failures.

> You get real production telemetry from a microservice system, and a set of failures.
> **Build an agent that works out — from the telemetry alone — when each failure
> started, which component caused it, and why.**

## The twist: route across a model family

Your agent runs on the **GLM model family** on Featherless — seven models, from cheap
and fast to large and strong, roughly **18× apart in cost per case**. **Your agent
chooses the model for each call.** Cheap calls — filtering, extracting, formatting — go
to a cheap model; the reasoning that decides the answer goes to a strong one.

You're scored on accuracy *and* on dollars spent, so the goal is the best point on that
curve, not the highest accuracy at any price. `docs/models.md` has the models, prices and
the rules.

## Build three things

1. **The agent** — runs unattended over telemetry it hasn't seen and writes its answers.
   The telemetry doesn't fit in a context window; the model has to query it, not read it.
2. **The eval** — your own harness, comparing at least two configurations: at minimum,
   your routed agent against the same agent on a single model.
3. **The explanation** — for every case, the telemetry that supports the answer. Scored
   whether or not the answer is right, and worth more than accuracy.

## Get started

```bash
# 1. download the Market-cloudbed-1 bundle into data/        (see GET_DATA.md)
cd starter && pip install -r requirements.txt && cd ..
make validate          # run the starter agent on two cases
make dev && make score # run it on all 70 cases, then score them
```

`starter/` has the entry point, a baseline agent, an example that routes across the
GLM family, and the scorer.

## What you hand in

A repository with a Dockerfile. We build it and run it on our own account — your
credit is never spent on judging. Your agent reads the key from `FEATHERLESS_API_KEY`
and writes `predictions.csv` plus one `evidence/<row_id>.md` per case.

**Submit through https://forms.gle/UbPSwZhKNfkovM8s5, before September 17, 2026,
3:00pm PDT.** The form also asks for your team, your project title, and a
presentation of around four minutes showing the project working. Details:
`docs/submission.md`.

## How you're judged

What we evaluate:

- **Accuracy** on cases your agent hasn't seen
- **Evidence and explainability** — can you show why?
- **Evaluation quality** — your harness and your comparisons
- **Cost efficiency** — dollars and wall-clock, read alongside accuracy

How much each is worth is in the participant agreement, which is the document that governs.

The state of the art gets about **one case in nine**, so most answers will be wrong.
Build for that. Full detail: `docs/scoring.md`

## The guides

| | |
|---|---|
| `GET_DATA.md` | downloading the bundle |
| `docs/data.md` | what's in it, and the traps |
| `docs/models.md` | the GLM family, prices, routing and limits |
| `docs/submission.md` | exactly what we run, and what your agent must write |
| `docs/scoring.md` | how accuracy and cost are measured, and the evaluator's sharp edges |

## Questions

Ask. We'd rather explain the domain than have you lose hours to something we
could clear up in a minute.
