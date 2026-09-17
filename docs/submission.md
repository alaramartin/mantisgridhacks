# What you submit

A git repository with a Dockerfile at its root. We build it and run it — you don't
send us results.

```
submission/
├── Dockerfile      builds an image whose working directory contains run.py
├── run.py          the entry point, exactly as below
├── REPORT.md       your writeup: the eval, the model comparison, where it fails
└── eval/           your harness and its results
```

`starter/` is already this shape — Dockerfile, `run.py`, an example agent — so start
from it. Keep `run.py`'s command line as it is; change the agent.

**Put the Dockerfile at the repository root.** If your project lives in a subfolder,
that is the only Dockerfile in the repository and we will find it — but a repository
with two of them is ambiguous and we may build the wrong one.

## Handing it in

**One form, before September 17, 2026, 3:00pm PDT** — the moment the event ends.
Late submissions are not judged.

**https://forms.gle/UbPSwZhKNfkovM8s5**

It asks for four things:

1. **Your team** — every member, each with their student or career status.
2. **Project title and description**, and which track you are in.
3. **The repository** — public, with keys and secrets removed. **We judge whatever
   the link shows when we open it**: the default branch, at its latest commit when we
   clone. There is no commit to nominate, so make sure the work you want judged is
   merged and pushed before the deadline. Its README must list the AI models, coding
   assistants and agent frameworks you used, and say briefly what was AI-generated and
   what the team wrote. Using AI heavily is expected here; not disclosing it is the
   problem.
4. **A presentation of around four minutes**, showing the project actually working.
   A demo is strongly encouraged — and a headless agent still has plenty to show.
   Run a case live (the reference agent takes about fifteen seconds), open the
   `evidence/` file it just wrote, and walk through what it ruled out. Then show
   your eval: the routed run against the single-model one.

In English. One project, one track — if your work draws on both, tell us which
track's judging focus to apply.

After the deadline you may fix bugs and repair a broken deployment. You may not add
features.

## How we run it

Every submission, the same way, with one command:

```bash
docker build -t your-team .
docker run --rm \
  -e FEATHERLESS_API_KEY=<our key> \
  -v <a bundle>:/data:ro \
  -v <an empty folder>:/out \
  your-team \
  python run.py --dataset /data --queries /data/query.csv --out /out
```

So your agent must:

- **Read the model key from `FEATHERLESS_API_KEY`**, and the endpoint from
  `FEATHERLESS_BASE_URL` if it's set (default `https://api.featherless.ai/v1`). Never
  hard-code a key. That's how we run you on our key — your credit isn't spent on judging.
- **Read only from `--dataset`**, and **write only into `--out`**.
- **Reach only the endpoint we give you.** During evaluation your container has no
  other route out — no package installs, no downloads, no other API. Take the host
  from `FEATHERLESS_BASE_URL`; anything that hard-codes one fails here.
- **Run unattended.** No prompts, no manual steps, no notebook.
- **Survive a model going away.** Capacity errors arrive mid-run, as
  HTTP 200 with an error body. Retry, fall back to another model in the
  family, and keep going — `docs/models.md`.
- **Choose its own models** from the GLM family, per call — see `docs/models.md`.
- **Stay within the limits:** 10 minutes and $3 per case, and **20 minutes** and $25 for
  the whole run of 20 cases (`docs/models.md`). A case that goes over scores zero and the
  run moves on; a run that reaches either total stops where it is, and the cases it didn't
  reach score zero. Twenty minutes over twenty cases is the one most likely to bind — a
  minute a case, on average.
- **Fit the machine: 2 CPUs and 8 GB, no GPU.** The dataset is far larger than that,
  so read it in pieces — the reference agent peaks under 2 GB by loading only the
  columns and days it needs. A container that asks for more is killed and the cases it
  had not reached score zero.

## What it must write

**`predictions.csv`** — columns `row_id` and `prediction`, one row per row of
`query.csv`, matched on `row_id` (order and extra columns don't matter). `prediction`
holds one JSON object per failure, in time order, numbered from 1:

```json
{
    "1": {
        "root cause occurrence datetime": "2022-03-20 09:09:06",
        "root cause component": "shippingservice-1",
        "root cause reason": "container read I/O load"
    }
}
```

Keep the keys in exactly that order, emit exactly as many objects as the instruction
says there are failures, and use the component and reason names exactly as they appear
in the data — `docs/scoring.md` explains why each of those can zero a correct answer.

**`evidence/<row_id>.md`** — one file per case, named by the case's `row_id` in
`query.csv` (so `evidence/0.md`, `evidence/1.md`, ...). We may run a subset of cases, so
use `row_id`, not the row's position. This is how evidence — the largest part of the score — is judged, and
it's the same format for every team. Four sections, brief prose is fine:

```markdown
## Answer
shippingservice-1 / container read I/O load

## Confidence
Low. Three services showed correlated latency and I could not cleanly separate them.

## Evidence
metric_container.csv, 2022-03-20 09:00-09:30 — container_read_bytes on
shippingservice-1 rose from a 2.1MB/s baseline to 47MB/s at 09:09:06, four seconds
before latency moved on emailservice-0.
trace_span.csv, same window — p99 on shippingservice spans 12x baseline.

## Ruled out
node-3: node-level CPU and memory flat across the window.
emailservice-0: its I/O rise starts later and is smaller.
```

**We check the evidence against the raw files. Evidence that isn't in the data scores
zero** — worse than none, because in production it sends someone chasing nothing at 3am.

**`usage.jsonl`** — `run.py` writes this for you: one line per case, with the tokens
each model used. It's for your own eval (`python cost.py out/dev/usage.jsonl` prices it);
we don't score from it.

## How it's scored

| What | Scored by |
|---|---|
| `predictions.csv` | `starter/score.py` — the benchmark's own `evaluate.py`, unchanged; the same file `make score` runs. On cases your agent hasn't seen (`docs/scoring.md`) |
| `evidence/` | judges, checked against the raw telemetry |
| `REPORT.md` and `eval/` | judges |
| cost | dollars, from our metering of every call, priced at the table in `docs/models.md`; and wall-clock time per case and per run |

How much each is worth is in the participant agreement, which is the document that governs.

## Check it before you submit

```bash
make validate
```

Runs your agent on two dev cases and checks the output. **Run it** — a submission that
doesn't execute can't be judged. Then:

```bash
FEATHERLESS_API_KEY=<your key> make docker
```

That builds your image and runs it on two dev cases with the `docker run` command above,
exactly as we will — so if it works here, it works for us.
