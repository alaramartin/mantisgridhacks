"""Engine-only agent (Person 1's dev harness, no model calls).

It exists so the engine can be run through `run.py` / `make validate` / `make docker` before
Person 2's `agents/origin.py` lands, and as the emergency fallback if no model is reachable
(SPEC "Emergency ladder" 4). Person 2's agent owns routing, confidence and evidence assembly;
the evidence written here is the engine's own rendering of the same facts.

    python run.py --dataset data/Market-cloudbed-1 --queries data/Market-cloudbed-1/dev/query_dev.csv \
        --out out/engine --agent agents.p1_engine_only
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from origin.candidates import answer_time                       # noqa: E402
from origin.contract import Analysis                            # noqa: E402
from origin.engine import analyze                               # noqa: E402
from origin.facts import render_fact, render_ruled_out          # noqa: E402
from run import Solution, format_prediction                     # noqa: E402

CASE_SOFT_DEADLINE_S = 45          # SPEC "Operating constraints"; Person 2's agent owns the real budget
FACTS_PER_ANSWER = 6


def evidence(a: Analysis) -> str:
    asks = a.case.asks
    lines = ["## Answer"]
    for x in a.engine_answers:
        parts = [f"{x['datetime']}{'' if asks.get('datetime') else ' (not asked)'}",
                 f"{x['component']}{'' if asks.get('component') else ' (not asked)'}",
                 f"{x['reason']}{'' if asks.get('reason') else ' (not asked)'}"]
        lines.append(f"- {' / '.join(parts)}")
    top = a.candidates[0] if a.candidates else None
    conf = "High" if a.margin >= 0.35 and top and top.support >= 2 else ("Low" if a.margin < 0.15 else "Medium")
    why = (f"Engine only, no model was called. The top suspect leads the next by {a.margin:.0%} of its score"
           f"{f' with {top.support} independent signals' if top else ''}.")
    lines += ["", "## Confidence", f"{conf}. {why}", "", "## Evidence"]
    for x in a.engine_answers:
        lines.append(f"**{x['component']} — {x['reason']} — {x['datetime']} ({x['cid']})**")
        lines += [render_fact(a.signals[i]) for i in x["signal_ids"][:FACTS_PER_ANSWER] if i in a.signals]
    lines += ["", "## Ruled out"] + (render_ruled_out(a, [x["component"] for x in a.engine_answers])
                                     or ["- nothing else was anomalous in this window."])
    files = a.window_stats.get("files", {})
    lines += ["", "## How this was produced",
              "Deterministic engine only (no model call, no tokens): the case window plus a 60 min baseline was "
              "read from " + f"{len(files)} file slice(s); " + f"{len(a.signals)} facts and "
              f"{len(a.candidates)} candidates; times are UTC+8 with the epoch seconds beside them.",
              f"Timings: {a.timings}. Engine answer kept (no model was asked)."]
    if a.notes:
        lines += ["", "Notes: " + "; ".join(a.notes[:12])]
    return "\n".join(lines) + "\n"


def solve(instruction: str, dataset_dir: Path, ctx: dict) -> Solution:
    a = analyze(instruction, Path(dataset_dir), deadline_ts=time.time() + CASE_SOFT_DEADLINE_S)
    asks = a.case.asks
    pred = format_prediction([{k: (x[k] if asks.get(k) else None) for k in ("datetime", "component", "reason")}
                              for x in a.engine_answers])
    return Solution(prediction=pred, evidence=evidence(a), usage={})


__all__ = ["solve", "evidence", "answer_time"]
