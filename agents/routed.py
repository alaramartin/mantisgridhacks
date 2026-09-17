"""An example agent that routes across the GLM family.

A starting point, not a good agent: it shows the plumbing -- calling Featherless,
sending each call to the model it needs, counting tokens per model -- on top of
the baseline's analysis. Every call has a job:

  1. no model     the baseline's analysis: the window, and components ranked by
                  their strongest anomaly (agents/heuristic.py)
  2. CHEAP        read the question: how many failures it says occurred, as a
                  check on the parser -- a wrong count scores the whole case zero
  3. STRONG       decide: pick the root cause from the ranked candidates, with a
                  reason from the legal list
  4. no model     check the pick names a candidate and a legal reason; otherwise
                  keep the baseline's answer for that failure
  5. CHEAP        write the evidence file from the decision and the data

    python run.py ... --agent agents.routed
    RCA_MODEL=zai-org/GLM-5.2 python run.py ... --agent agents.routed

The second line runs every call on one model -- the single-model configuration
to compare your routing against. `python cost.py <out>/usage.jsonl` prices both.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from llm import LLM                                        # noqa: E402
from run import Solution, format_prediction               # noqa: E402
from agents.heuristic import (NODE_REASONS, POD_REASONS,  # noqa: E402
                              Analysis, analyse, answer_for, solve as baseline)

# Preference order per tier, not one model. A busy provider is a normal event and
# llm.ask() walks down the list -- see "When a model is unavailable" in
# docs/models.md. Picking the second name is a real decision: it should be close in
# capability to the first, or the fallback quietly changes what your agent is.
CHEAP = ["zai-org/GLM-4.7-Flash", "zai-org/GLM-5.3-Flash"]
STRONG = ["zai-org/GLM-5.2", "zai-org/GLM-5.1"]
CANDIDATES = 10          # components shown to the strong model
KPIS_EACH = 3            # strongest KPIs shown per component


def _model(tier: list[str]) -> list[str]:
    """RCA_MODEL pins one model for an ablation; otherwise the tier's own order."""
    return [os.environ["RCA_MODEL"]] if os.environ.get("RCA_MODEL") else tier


def _json(text: str) -> dict:
    """The first {...} in a reply; models like to wrap JSON in prose or fences."""
    m = re.search(r"\{.*\}", text, re.S)
    return json.loads(m.group(0)) if m else {}


def _candidates(a: Analysis) -> str:
    lines = []
    for comp, z in a.ranked.head(CANDIDATES).items():
        kpis = a.j[a.j.component == comp].head(KPIS_EACH)
        shown = ", ".join(f"{k.kpi_name} z={k.z:.1f}" for k in kpis.itertuples())
        lines.append(f"- {comp} (peak z {z:.1f}): {shown}")
    return "\n".join(lines)


def solve(instruction: str, dataset_dir: Path, ctx: dict) -> Solution:
    a = analyse(instruction, dataset_dir)
    if not isinstance(a, Analysis):
        return a                               # nothing to rank; the baseline explains why
    llm = LLM()
    fallback = [answer_for(a, c) for c in a.ranked.head(a.n).index]
    notes = []

    try:
        # 2. CHEAP: read the question
        q = _json(llm.ask(_model(CHEAP),
            "Read this root-cause-analysis question. Reply with JSON only: "
            '{"failures": <number of failures it says occurred>}\n\n' + instruction))
        if q.get("failures") != a.n:
            notes.append(f"The question-reading call said {q.get('failures')} failure(s); "
                         f"the parser said {a.n}. Kept the parser's count.")

        # 3. STRONG: decide
        legal = sorted(set(NODE_REASONS.values()) | set(POD_REASONS.values()))
        d = _json(llm.ask(_model(STRONG),
            f"A microservice system had {a.n} failure(s) between {a.lo:%Y-%m-%d %H:%M} "
            f"and {a.hi:%H:%M} UTC. These components had the strongest anomalies in that "
            f"window, as robust z-scores against the rest of the day:\n\n{_candidates(a)}\n\n"
            "Anomalies spread: the loudest component is often a victim, not the cause. "
            f"Pick the {a.n} root-cause component(s), each with one reason from this list "
            f"(node-* components take node reasons):\n{json.dumps(legal)}\n\n"
            'Reply with JSON only: {"answers": [{"component": ..., "reason": ...}], '
            '"confidence": "low" | "medium" | "high", "why": "two or three sentences"}'))
    except Exception as e:                     # an API error must not cost the answer
        notes.append(f"A model call failed ({type(e).__name__}: {e}); "
                     "this is the baseline's answer.")
        sol = baseline(instruction, dataset_dir, ctx)
        sol.evidence += "\n" + "\n".join(notes) + "\n"
        sol.usage = llm.usage
        return sol

    # 4. check the decision against the data
    answers = []
    picks = d.get("answers") or []
    for i in range(a.n):
        p = picks[i] if i < len(picks) and isinstance(picks[i], dict) else {}
        comp, reason = p.get("component"), p.get("reason")
        if comp not in a.ranked.index:
            if comp:
                notes.append(f"The model named {comp!r}, which is not a candidate; "
                             "kept the baseline's pick.")
            answers.append(fallback[i])
            continue
        x = answer_for(a, comp)                # time: that component's peak
        table = NODE_REASONS if comp.startswith("node-") else POD_REASONS
        if reason in table.values():
            x["reason"] = reason
        elif reason:
            notes.append(f"{reason!r} is not a legal reason for {comp}; kept {x['reason']!r}.")
        answers.append(x)

    # 5. CHEAP: write the evidence
    decided = "\n".join(f"{i}. {x['component']} / {x['reason']} / {x['datetime']}"
                        for i, x in enumerate(answers, 1))
    facts = (f"Answer:\n{decided}\n\nConfidence: {d.get('confidence', 'low')}\n"
             f"Reasoning: {d.get('why', '')}\n\nCandidates (z-scores):\n{_candidates(a)}")
    try:
        evidence = llm.ask(_model(CHEAP),
            "Write a short markdown evidence note for this diagnosis, with exactly these "
            "sections: ## Answer, ## Confidence, ## Evidence, ## Ruled out. Use only the "
            "facts below; do not invent numbers.\n\n" + facts)
    except Exception as e:
        notes.append(f"The evidence-writing call failed ({type(e).__name__}); "
                     "these are the raw facts.")
        evidence = "## Facts\n\n" + facts

    evidence += "\n\n## How this was produced\n\n" + "\n".join(
        f"- `{m}`: {u['calls']} call(s), {u['prompt_tokens']:,} in / "
        f"{u['completion_tokens']:,} out" for m, u in llm.usage.items())
    if notes:
        evidence += "\n\n" + "\n".join(f"- {n}" for n in notes)
    return Solution(prediction=format_prediction(answers), evidence=evidence + "\n",
                    usage=llm.usage)
