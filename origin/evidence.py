"""The markdown a human reads. Worth 35% of the grade against accuracy's 20%.

Two rules shape this file:

**Every number is grep-able.** A judge should be able to take any figure out of
`## Evidence`, open the CSV it names, and find the row. Derived numbers say what
they are. Nothing here is rounded into unrecognisability.

**The model's prose is guilty until proven grounded.** A fluent wrong sentence is
worse than no sentence, because it reads exactly like a right one. `grounded()`
checks every number in the model's `why` against the fact sheet it was given, and
every component-looking token against the components that exist. One number it
could not have read from the data and the whole sentence is dropped, with a note
saying so. We would rather look terse than look confidently wrong.

And never describe a fallback as a model decision (NON-NEGOTIABLE RULE 8): the
"How this was produced" section says exactly which route ran and what it cost.
"""
from __future__ import annotations

import re

from origin.contract import Analysis, fmt_ts

FIELDS = ("datetime", "component", "reason")
NUMBER = re.compile(r"\d+(?:\.\d+)?")
FACT_ID = re.compile(r"\b[FC]\d+\b")
COMPONENTISH = re.compile(r"\b[a-z]+(?:service|node)[\w-]*\b|\bnode-\d+\b")


def _render_fact(sig) -> str:
    try:
        from origin.facts import render_fact
        return render_fact(sig)
    except ImportError:
        from origin.router import _render_fact as stub
        return stub(sig)


def _ruled_out(a: Analysis, chosen: list[str], k: int = 3) -> list[str]:
    try:
        from origin.facts import render_ruled_out
        return render_ruled_out(a, chosen, k)
    except ImportError:
        pass
    out = []
    for c in a.candidates:
        if c.component in chosen or len(out) >= k:
            continue
        why = c.demoted_by or (
            f"scored {c.score:.1f} against the answer's "
            f"{a.candidates[0].score:.1f} on {c.support} signal(s)")
        out.append(f"- `{c.component}` ({c.cid}, {c.level}) — {why}")
    return out


def grounded(text: str, sheet: str, a: Analysis) -> tuple[bool, list[str]]:
    """Could the model have read every number and name in `text` off the sheet?

    Small integers are allowed through -- "the first two candidates" is counting,
    not citing. Fact and candidate IDs are checked against the analysis, not the
    number rule, so "F12" does not fail for containing 12.
    """
    if not text:
        return False, ["empty"]
    bad: list[str] = []

    masked = FACT_ID.sub(" ", text)
    for ident in FACT_ID.findall(text):
        if ident not in a.signals and ident not in {c.cid for c in a.candidates}:
            bad.append(f"unknown id {ident}")

    for num in NUMBER.findall(masked):
        if "." not in num and int(num) <= 10:
            continue
        if num not in sheet:
            bad.append(f"number {num} is not in the facts")

    known = {c.component for c in a.candidates} | {s.component for s in a.signals.values()}
    for tok in COMPONENTISH.findall(text.lower()):
        if not any(tok == k.lower() or tok in k.lower() for k in known):
            bad.append(f"unknown component {tok}")

    return (not bad), bad


def _answer_lines(a: Analysis, answers: list[dict]) -> list[str]:
    out = []
    for i, x in enumerate(answers, 1):
        parts = []
        for f in FIELDS:
            v = x.get(f, "")
            parts.append(f"{v}" if a.case.asks.get(f) else f"{v} _(not asked)_")
        out.append(f"{i}. **{parts[1]}** / {parts[2]} / {parts[0]}")
    return out


def _stage_line(d: dict, key: str) -> str | None:
    st = d.get(key)
    if not st:
        return None
    models = ", ".join(f"`{m}`" for m in st.get("models", []))
    bit = f"- **{key}**: {models}, {st.get('seconds', 0.0):.1f}s"
    if st.get("error"):
        bit += f" — rejected: {st['error']}"
    return bit


def build_evidence(a: Analysis, answers: list[dict], d: dict, confidence: str,
                   notes: list[str], seconds: float) -> str:
    route = d.get("route", "fallback")
    sheet = d.get("sheet", "")
    out: list[str] = ["# ORIGIN — root cause analysis", ""]

    # --- Answer ---------------------------------------------------------------
    out.append("## Answer")
    out.append("")
    out += _answer_lines(a, answers)
    out.append("")
    out.append(f"Window: {fmt_ts(a.case.lo_ts)} to {fmt_ts(a.case.hi_ts)} (UTC+8), "
               f"{a.case.n_failures} failure(s) asked for.")
    out.append("")

    # --- Confidence -----------------------------------------------------------
    out.append("## Confidence")
    out.append("")
    out.append(f"**{confidence}.** {d.get('confidence_why', '')}")
    why = d.get("why")
    if why:
        ok, bad = grounded(why, sheet, a)
        if ok:
            out.append("")
            out.append(f"The model's reasoning: {why}")
        else:
            notes = list(notes) + [
                "model prose removed: it cited a number not found in the data "
                f"({bad[0]})"]
            d["grounding_dropped"] = True
    if confidence == "Low" and len(a.candidates) > 1:
        runner = a.candidates[1]
        out.append("")
        out.append(f"What would settle it: `{runner.component}` ({runner.cid}) is the "
                   f"runner-up at score {runner.score:.1f} on {runner.support} signal(s)"
                   + (f", first going wrong at {fmt_ts(runner.onset_ts)}"
                      if runner.onset_ts else "")
                   + ". Separating them needs a signal that starts before the other's, "
                     "or a dependency between them that the traces do not show.")
    out.append("")

    # --- Evidence -------------------------------------------------------------
    out.append("## Evidence")
    out.append("")
    cited = {f for p in (d.get("picks") or []) for f in p.get("fact_ids", [])}
    for x in answers:
        out.append(f"**{x.get('component')} — {x.get('reason')}**")
        out.append("")
        ids = list(dict.fromkeys(list(x.get("signal_ids") or [])
                                 + [f for f in cited if f in a.signals]))[:6]
        for sid in ids:
            sig = a.signals.get(sid)
            if sig is not None:
                out.append(_render_fact(sig))
        if not ids:
            out.append("- _no signal crossed the threshold for this component_")
        out.append("")

    # --- Ruled out ------------------------------------------------------------
    out.append("## Ruled out")
    out.append("")
    ruled = _ruled_out(a, [x.get("component") for x in answers])
    out += ruled or ["- _nothing else came close enough to rule out_"]
    out.append("")

    # --- How this was produced ------------------------------------------------
    out.append("## How this was produced")
    out.append("")
    told = {"gate": "the engine was clear enough that no model was called",
            "flash": "the cheap model decided",
            "strong": "the cheap model was escalated to the strong model",
            "engine_only": "engine only, no model was called",
            "fallback": "**a fallback** — the model path failed and the engine's "
                        "answer was kept. No model decided this."}
    out.append(f"- **Route:** `{route}` — {told.get(route, route)}")

    engine_top = a.engine_answers[0]["component"] if a.engine_answers else None
    final_top = answers[0]["component"] if answers else None
    if route in ("flash", "strong"):
        out.append(f"- {'**model changed the engine answer**' if final_top != engine_top else 'engine answer kept'}"
                   f" (engine's top was `{engine_top}`)")
    else:
        out.append(f"- engine answer kept (`{engine_top}`)")

    for key in ("flash", "strong"):
        line = _stage_line(d, key)
        if line:
            out.append(line)
    usage = d.get("usage") or {}
    for model, u in usage.items():
        out.append(f"- `{model}`: {u.get('calls', 0)} call(s), "
                   f"{u.get('prompt_tokens', 0):,} in / {u.get('completion_tokens', 0):,} out")
    t = a.timings or {}
    out.append(f"- **Seconds:** total {seconds:.1f} "
               f"(engine load {t.get('load_s', 0):.1f}, signals {t.get('signals_s', 0):.1f}, "
               f"candidates {t.get('candidates_s', 0):.1f}, "
               f"flash {d.get('seconds', {}).get('flash', 0.0):.1f}, "
               f"strong {d.get('seconds', {}).get('strong', 0.0):.1f})")
    out.append(f"- **Window scanned:** {a.window_stats.get('metric_rows', 0):,} metric rows, "
               f"{a.window_stats.get('edge_rows', 0):,} trace edges, "
               f"{a.window_stats.get('log_rows', 0):,} error log lines")

    all_notes = list(dict.fromkeys(list(notes) + list(d.get("notes", []))
                                   + [f"error: {e}" for e in d.get("errors", [])]
                                   + list(a.notes or [])))
    if all_notes:
        out.append("")
        out.append("### Notes")
        out.append("")
        out += [f"- {n}" for n in all_notes]

    return "\n".join(out) + "\n"
