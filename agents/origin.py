"""ORIGIN -- the agent run.py loads. Entry point, budget and the never-empty guarantee.

The shape of a case:

    analyze()        Person 1's engine: window -> signals -> ranked candidates
    route()          spend a model only where the engine is unsure (origin/router.py)
    validate()       force the answer back inside the legal vocabulary (origin/validate.py)
    build_evidence() the markdown a human reads (origin/evidence.py)

Three things this file is responsible for and nothing else is:

  * **The budget.** A per-case soft deadline, and a run-level average: if the run
    is drifting over RUN_AVG_LIMIT_S a case at a time, later cases go engine-only
    rather than letting the judged run hit its wall clock and lose the tail.
  * **One LLM client for the whole run**, so the circuit breaker in llm.py
    remembers a dead model across cases instead of rediscovering it 70 times.
  * **Never an empty prediction.** `score.py` needs exactly `n` JSON objects; an
    exception that escapes here scores zero for the case. Every failure path
    still emits `n` objects and says in the evidence that it is guessing.

`ORIGIN_MODE` = routed (default) | engine | single. `ORIGIN_FIXTURE=1` swaps the
engine for `origin/fixture.py` (PLACEHOLDER, until CP3).
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from run import Solution, format_prediction   # noqa: E402
from origin.config import (                   # noqa: E402
    CASE_SOFT_DEADLINE_S, RUN_AVG_LIMIT_S,
)
from origin.contract import fmt_ts            # noqa: E402

# One client and one set of running totals for the whole run. run.py imports this
# module once and calls solve() per case, so module state is exactly run state.
_RUN: dict = {"start": None, "cases": 0, "seconds": 0.0}
_LLM = None
_LLM_TRIED = False


def get_llm():
    """The run's single LLM client, or None when there is no key (engine-only)."""
    global _LLM, _LLM_TRIED
    if not _LLM_TRIED:
        _LLM_TRIED = True
        try:
            from llm import LLM
            _LLM = LLM(retries=1, backoff=1.0, breaker=2)
        except RuntimeError:            # FEATHERLESS_API_KEY not set
            _LLM = None
    return _LLM


def analyze(instruction: str, dataset_dir: Path, deadline: float):
    """Person 1's engine, or the fixture while the engine is still being built."""
    if os.environ.get("ORIGIN_FIXTURE") == "1":
        from origin.fixture import make_analysis, make_clear_analysis
        # alternate, so a fixture run exercises both the gate and the model path
        maker = make_clear_analysis if _RUN["cases"] % 2 else make_analysis
        a = maker()
        a.case.instruction = instruction
        return a
    from origin.engine import analyze as engine_analyze
    return engine_analyze(instruction, dataset_dir, deadline)


# --- Phase 3 modules. Until they land, degrade to the engine's own answer. -----

def _route(a, llm, mode: str, deadline: float) -> dict:
    try:
        from origin.router import route
    except ImportError:
        return {"route": "engine_only", "answers": list(a.engine_answers),
                "notes": ["PLACEHOLDER: origin/router.py lands in Phase 3"],
                "seconds": {"flash": 0.0, "strong": 0.0},
                "flash_pick": None, "strong_pick": None}
    return route(a, llm, mode, deadline)


def _validate(a, decision: dict):
    try:
        from origin.validate import validate
    except ImportError:
        answers = decision.get("answers") or list(a.engine_answers)
        return answers, "Medium", ["PLACEHOLDER: origin/validate.py lands in Phase 3"]
    return validate(a, decision)


def _evidence(a, answers, decision, confidence, notes, seconds) -> str:
    # build_evidence is Analysis-shaped by design. If the engine died before there
    # was an Analysis, using it would bury the real cause under an AttributeError
    # from the evidence code -- and the evidence file is 35% of the grade.
    if a is None:
        return _stub_evidence(a, answers, decision, confidence, notes, seconds)
    try:
        from origin.evidence import build_evidence
    except ImportError:
        return _stub_evidence(a, answers, decision, confidence, notes, seconds)
    return build_evidence(a, answers, decision, confidence, notes, seconds)


def _stub_evidence(a, answers, decision, confidence, notes, seconds) -> str:
    """PLACEHOLDER evidence until origin/evidence.py lands in Phase 3."""
    out = ["# ORIGIN (skeleton evidence -- origin/evidence.py lands at CP3)\n",
           f"**Route:** `{decision.get('route')}`  ",
           f"**Confidence:** {confidence}  ",
           f"**Seconds:** {seconds:.1f}\n"]
    if a is not None:
        out.append(f"**Failures asked for:** {a.case.n_failures}  ")
        out.append(f"**Margin:** {a.margin:.2f}\n")
        out.append("## Candidates\n")
        out.append("| cid | component | level | score | support | best reason |")
        out.append("|---|---|---|---|---|---|")
        for c in a.candidates[:8]:
            reason = c.reasons[0][0] if c.reasons else "--"
            out.append(f"| {c.cid} | `{c.component}` | {c.level} | {c.score:.1f} "
                       f"| {c.support} | {reason} |")
    out.append("\n## Answer\n")
    for i, x in enumerate(answers, 1):
        out.append(f"{i}. `{x.get('component')}` — {x.get('reason')} — {x.get('datetime')}")
    if notes:
        out.append("\n## Notes\n")
        out.extend(f"- {n}" for n in notes)
    return "\n".join(out) + "\n"


# --- the never-empty guarantee ------------------------------------------------

# run.py writes evidence with `Path.write_text(...)` and no encoding, so on Windows
# it encodes as cp1252 -- and that call sits OUTSIDE its per-case try/except, so one
# unencodable character kills the whole run rather than one case. Contract §2 puts
# "caller → callee" in every edge cmdb_id, and U+2192 is not in cp1252. Judges run
# Linux (UTF-8) where this is moot, but `make dev` on Person 2's machine is not.
# Folding here fixes it for whatever P1's render_fact emits, without touching run.py.
_ASCII = str.maketrans({
    "→": "->", "←": "<-", "—": "--", "–": "-", "…": "...",
    "‘": "'", "’": "'", "“": '"', "”": '"', " ": " ",
    "·": "-", "≥": ">=", "≤": "<=", "×": "x", "τ": "tau",
})


def _ascii(text: str) -> str:
    return text.translate(_ASCII).encode("ascii", "replace").decode("ascii")


def _fallback_answers(a, n: int, instruction: str) -> list[dict]:
    """`n` answers when everything upstream failed. Honest, but never empty:
    an empty prediction is a guaranteed zero, a guess is only probably one."""
    if a is not None and a.candidates:
        out = []
        for c in a.candidates[:n]:
            out.append({"datetime": fmt_ts(c.onset_ts or a.case.lo_ts),
                        "component": c.component,
                        "reason": (c.reasons[0][0] if c.reasons
                                   else ("node CPU load" if c.level == "node"
                                         else "container CPU load"))})
        while len(out) < n:             # fewer candidates than failures asked for
            out.append(dict(out[-1]) if out else {})
        return out
    # Nothing to rank. The window start is the one thing we actually know, so give
    # that and leave the rest blank -- an invented component name scores exactly
    # what a blank one does, and blank does not put a fabrication in the evidence.
    when = fmt_ts(a.case.lo_ts) if a is not None else ""
    return [{"datetime": when, "component": "", "reason": ""}
            for _ in range(max(1, n))]


def _n_failures(a, instruction: str) -> int:
    if a is not None:
        return max(1, a.case.n_failures)
    from agents.heuristic import failure_count
    return failure_count(instruction)


def _for_asks(answers: list[dict], asks: dict[str, bool]) -> list[dict]:
    """Drop the fields this case did not ask for. A case whose `asks` came back
    empty means the parser failed -- then send all three rather than nothing."""
    if not any(asks.values()):
        asks = {"datetime": True, "component": True, "reason": True}
    return [{k: v for k, v in x.items() if asks.get(k)} for x in answers]


def write_trace(out_dir, instruction: str, a, decision: dict, answers: list[dict],
                confidence: str, mode: str, errors: list[str], seconds: dict) -> None:
    """One JSONL line per case for the eval harness (PLAN §4). Only inside --out."""
    try:
        rec = {
            "instruction_sha1": hashlib.sha1(instruction.encode()).hexdigest(),
            "mode": mode,
            "route": decision.get("route", "fallback"),
            "n_failures": a.case.n_failures if a is not None else None,
            "asks": a.case.asks if a is not None else {},
            "engine_top": ([a.engine_answers[0].get("component"),
                            a.engine_answers[0].get("reason")]
                           if a is not None and a.engine_answers else None),
            "margin": round(a.margin, 4) if a is not None else None,
            "flash_pick": decision.get("flash_pick"),
            "strong_pick": decision.get("strong_pick"),
            "final": [[x.get("datetime"), x.get("component"), x.get("reason")]
                      for x in answers],
            "confidence": confidence,
            # the model's own claim, recorded and never acted on -- so it can be
            # checked against outcomes afterwards instead of taken on trust
            "confidence_model": decision.get("confidence_model"),
            "support": (a.candidates[0].support if a is not None and a.candidates else None),
            "n_candidates": (len(a.candidates) if a is not None else None),
            "grounding_dropped": bool(decision.get("grounding_dropped", False)),
            # Both levels: `errors` is what escaped solve(), decision["errors"] is
            # what each model stage recorded. Tracing only the first made a failed
            # model call look clean -- P1 hit exactly that at CP3, where an openai
            # 3.x TypeError produced route="fallback" with an empty errors list.
            "errors": list(errors) + list((decision or {}).get("errors", [])),
            "seconds": seconds,
        }
        with (Path(out_dir) / "origin_trace.jsonl").open("a") as fh:
            fh.write(json.dumps(rec) + "\n")
    except Exception:
        pass        # the trace is diagnostics; it must never cost a case


def _via_heuristic(instruction: str, dataset_dir: Path, ctx: dict, t0: float) -> Solution:
    """PLACEHOLDER route, until `origin/engine.py` exists (PLAN Phase 3).

    Never presented as an ORIGIN answer: the evidence says at the top which agent
    actually produced it (NON-NEGOTIABLE RULE 8 in spirit -- do not claim work you
    did not do).
    """
    from agents.heuristic import solve as heuristic_solve
    sol = heuristic_solve(instruction, dataset_dir, ctx)
    banner = ("> **This is the baseline heuristic, not ORIGIN.** `origin/engine.py` was "
              "not importable, so `agents/origin.py` fell back to `agents/heuristic.py`. "
              "No engine candidates, no model call, no causal filter.\n\n")
    total = time.time() - t0
    # Still trace it: the eval harness joins on this file, and a case that silently
    # produces no line looks like a case that never ran.
    write_trace(ctx.get("out_dir", "."), instruction, None,
                {"route": "heuristic_fallback"}, [], "Low", "heuristic",
                ["origin.engine not importable"],
                {"engine": round(total, 2), "flash": 0.0, "strong": 0.0,
                 "total": round(total, 2)})
    _RUN["cases"] += 1
    _RUN["seconds"] += total
    return Solution(prediction=sol.prediction,
                    evidence=_ascii(banner + (sol.evidence or "")),
                    usage=sol.usage)


def solve(instruction: str, dataset_dir: Path, ctx: dict) -> Solution:
    t0 = time.time()
    if _RUN["start"] is None:
        _RUN["start"] = t0
    deadline = t0 + CASE_SOFT_DEADLINE_S
    mode = os.environ.get("ORIGIN_MODE", "routed")
    errors: list[str] = []
    notes: list[str] = []

    avg = _RUN["seconds"] / _RUN["cases"] if _RUN["cases"] else 0.0
    if avg > RUN_AVG_LIMIT_S and mode != "engine":
        mode = "engine"
        notes.append(f"running average {avg:.0f}s over the {RUN_AVG_LIMIT_S}s limit: "
                     "engine only for the rest of the run")

    a = None
    llm = None
    decision: dict = {"route": "fallback"}
    confidence = "Low"
    t_engine = t0
    try:
        try:
            a = analyze(instruction, Path(dataset_dir), deadline)
        except ImportError:
            # Person 1's engine has not landed yet. The heuristic is weak but real,
            # and a real weak answer beats a blank one -- so borrow it and say so.
            return _via_heuristic(instruction, dataset_dir, ctx, t0)
        t_engine = time.time()

        if mode != "engine":
            llm = get_llm()
            if llm is None:
                notes.append("FEATHERLESS_API_KEY not set: engine only")
            else:
                llm.usage = {}          # usage is per case, not per run
        decision = _route(a, llm, mode, deadline)
        decision["usage"] = dict(llm.usage) if llm else {}   # evidence reports it
        answers, confidence, vnotes = _validate(a, decision)
        notes += list(decision.get("notes", [])) + list(vnotes)
        if not answers:
            raise ValueError("no answers after validation")
    except Exception:
        errors.append(traceback.format_exc(limit=3).strip().splitlines()[-1])
        notes.append("ORIGIN fell back: " + errors[-1])
        decision.setdefault("route", "fallback")
        decision["route"] = "fallback"
        answers = _fallback_answers(a, _n_failures(a, instruction), instruction)
        confidence = "Low"

    n = _n_failures(a, instruction)
    answers = answers[:n] if len(answers) > n else answers
    while len(answers) < n:             # the count must match or the case scores 0
        answers.append(dict(answers[-1]) if answers
                       else _fallback_answers(a, 1, instruction)[0])

    total = time.time() - t0
    seconds = {"engine": round(t_engine - t0, 2),
               "flash": round(decision.get("seconds", {}).get("flash", 0.0), 2),
               "strong": round(decision.get("seconds", {}).get("strong", 0.0), 2),
               "total": round(total, 2)}

    try:
        evidence = _evidence(a, answers, decision, confidence, notes, total)
    except Exception:
        # Keep what we know (the answer, the route, the notes) and add the
        # assembly failure to it, rather than replacing everything with a traceback.
        evidence = (_stub_evidence(a, answers, decision, confidence, notes, total)
                    + "\n### Evidence assembly failed\n\n```\n"
                    + traceback.format_exc() + "```\n")
    evidence = _ascii(evidence)

    asks = a.case.asks if a is not None else {}
    prediction = format_prediction(_for_asks(answers, asks))
    write_trace(ctx.get("out_dir", "."), instruction, a, decision, answers,
                confidence, mode, errors, seconds)

    _RUN["cases"] += 1
    _RUN["seconds"] += total
    return Solution(prediction=prediction, evidence=evidence,
                    usage=(llm.usage if llm else {}))
