"""Where ORIGIN decides whether a model is worth calling, and which one.

The engine already ranks candidates. A model earns its cost only when that
ranking is genuinely ambiguous, so the route is:

    gate     the engine is clear (big margin, several independent signals,
             one failure) -> answer for free, call nothing
    flash    ambiguous -> GLM-4.7-Flash, ~4 K in / ~90 out, a few cents a hundred
    strong   Flash disagreed with the engine, or the case is hard (two failures,
             a tiny margin, all three fields asked) -> GLM-5.2 decides independently

The model never writes a timestamp, a component name or a free-text reason
(NON-NEGOTIABLE RULE 1). It returns candidate IDs and reasons from the legal
list; `origin/validate.py` turns those into the answer and code fills in every
number. That is what keeps a confident, fluent, wrong model from inventing an
answer that looks grep-able and isn't.

Everything here is bounded: one call per stage, a hard per-call timeout, and an
escalation that is skipped outright when the case's own deadline is too close.
A model that is down is the llm.py breaker's problem, not ours.
"""
from __future__ import annotations

import json
import os
import re
import time

from origin.config import (
    CALL_TIMEOUT_S, CANDIDATES_SHOWN, CHEAP, CHEAP_MAX_TOKENS, ESCALATE_MARGIN,
    FACTS_MAX, GATE_MARGIN, GATE_SUPPORT, STRONG, STRONG_MAX_TOKENS,
    STRONG_MIN_REMAINING_S, THINKING_OFF,
)
from origin.contract import (
    Analysis, NODE_REASONS, POD_REASONS, fmt_ts, legal_reasons,
)

PROMPT = """You are diagnosing a microservice incident. The loudest component is often a victim.
Prefer the component whose anomaly started first and whose dependencies (its node, the pods it calls) were normal.
Network faults show up as call-gap facts on trace edges. Pick exactly {n} root cause(s).
Reply with JSON only, no prose:
{{"answers": [{{"candidate": "C<number>", "reason": "<one legal reason for that component's level>", "fact_ids": ["F<number>", ...]}}],
 "confidence": "low" | "medium" | "high",
 "why": "at most 3 sentences; refer to facts by ID; do not write any number that is not in the facts"}}"""

SECOND_OPINION = ("\nA fast model picked: {picks}. The engine's top candidate is C1. "
                  "Decide independently.")

# Measured on the holdout: the models match the engine on REASON (55.6% vs 55.6%)
# but are worse at COMPONENT (44-48% vs 55.6%), and the time collapse (33% vs 53%)
# is downstream of that, because the timestamp is derived from the chosen
# component's signals. So give them only the half they are good at.
REASON_ONLY = ('\nThe component is already decided: {cid} {component}. Do NOT choose a '
               'different one -- answer with "candidate": "{cid}" every time. Your only '
               'job is to pick the single most likely reason for {component} from the '
               'legal list above.')


# --- the fact sheet -----------------------------------------------------------

def _render_fact(sig) -> str:
    """P1's `origin.facts.render_fact`, with a local stand-in until it lands.

    Every number here is copied from a raw row so a judge can grep for it
    (NON-NEGOTIABLE RULE 2); derived numbers say what they are.
    """
    try:
        from origin.facts import render_fact
        return render_fact(sig)
    except ImportError:
        pass
    when = fmt_ts(sig.onset_ts) if sig.onset_ts else "no sustained onset"
    first = "n/a" if sig.first_value is None else f"{sig.first_value:g}"
    return (f"- {sig.id} `{sig.component}` {sig.kpi} {sig.direction} "
            f"from a baseline median of {sig.base_median:g} (median of {sig.base_n} samples) "
            f"to {first} at {when}; peak {sig.peak_value:g} at {fmt_ts(sig.peak_ts)}; "
            f"{sig.breach_samples} samples out of range; score {sig.score:.1f} "
            f"[{sig.source} cmdb_id={sig.cmdb_id} epoch={int(sig.peak_ts)}]")


def _node_of(a: Analysis, cand) -> str | None:
    """A pod's node, read off the container cmdb_id (`<node>.<pod>`)."""
    if cand.level != "pod":
        return None
    for sid in cand.signal_ids:
        sig = a.signals.get(sid)
        if sig and "." in sig.cmdb_id and sig.cmdb_id.endswith(sig.component):
            return sig.cmdb_id.split(".", 1)[0]
    return None


def _asked(a: Analysis) -> str:
    names = {"datetime": "the time it started", "component": "the component",
             "reason": "the reason"}
    want = [names[k] for k in ("datetime", "component", "reason") if a.case.asks.get(k)]
    return ", ".join(want) if want else "the component, the reason"


def fact_sheet(a: Analysis) -> str:
    """The only thing a model ever sees. Structure is byte-stable so that two
    runs differ in their numbers, not their layout -- which is what makes the
    grounding check in origin/evidence.py meaningful."""
    lines = [
        f"CASE: {a.case.n_failures} failure(s) between {fmt_ts(a.case.lo_ts)} and "
        f"{fmt_ts(a.case.hi_ts)} (UTC+8). The answer needs: {_asked(a)}.",
        "LEGAL REASONS",
        "  For node components (names like node-N): " + "; ".join(NODE_REASONS),
        "  For pods and services: " + "; ".join(POD_REASONS),
        "CANDIDATES (engine ranking; score = how many normal ranges away, "
        "after checking what each depends on)",
    ]
    shown, fact_ids = a.candidates[:CANDIDATES_SHOWN], []
    for c in shown:
        node = _node_of(a, c)
        where = f"{c.level}, on {node}" if node else c.level
        started = fmt_ts(c.onset_ts) if c.onset_ts else "no sustained onset"
        reason = c.reasons[0][0] if c.reasons else "no legal reason from its KPIs"
        line = (f"{c.cid} {c.component} ({where}) score {c.score:.1f}; "
                f"first went wrong {started}; engine reason: {reason}; "
                f"facts {', '.join(c.signal_ids)}")
        if c.demoted_by:
            line += f"; DEMOTED: {c.demoted_by}"
        lines.append(line)
        fact_ids += [s for s in c.signal_ids if s not in fact_ids]

    lines.append("FACTS")
    for sid in fact_ids[:FACTS_MAX]:
        sig = a.signals.get(sid)
        if sig is not None:
            lines.append(_render_fact(sig))
    if a.notes:
        lines.append("NOTES")
        lines += [f"- {n}" for n in a.notes]
    return "\n".join(lines)


# --- parsing a reply ----------------------------------------------------------

def parse_reply(text: str, a: Analysis) -> tuple[list[dict] | None, str | None, str | None, str | None]:
    """-> (picks, confidence, why, error). picks is None when the reply is unusable.

    A reply is only accepted whole: a partly-valid answer set is a model that did
    not understand the question, and half-trusting it is worse than not calling it.
    """
    if not text or not text.strip():
        return None, None, None, "empty reply"
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return None, None, None, "no JSON object in the reply"
    try:
        obj = json.loads(m.group(0))
    except json.JSONDecodeError as e:
        return None, None, None, f"JSON parse failed: {e}"
    if not isinstance(obj, dict):
        return None, None, None, "reply JSON is not an object"

    answers = obj.get("answers")
    if not isinstance(answers, list) or len(answers) != a.case.n_failures:
        return None, None, None, (f"expected {a.case.n_failures} answer(s), "
                                  f"got {len(answers) if isinstance(answers, list) else 'none'}")

    known = {c.cid: c for c in a.candidates}
    picks = []
    for item in answers:
        if not isinstance(item, dict):
            return None, None, None, "an answer is not an object"
        cid = str(item.get("candidate", "")).strip().upper()
        if cid not in known:
            return None, None, None, f"unknown candidate {cid!r}"
        reason = str(item.get("reason", "")).strip()
        if reason not in legal_reasons(known[cid].level):
            return None, None, None, f"illegal reason {reason!r} for a {known[cid].level}"
        fact_ids = item.get("fact_ids") or []
        fact_ids = [f for f in map(str, fact_ids) if f in a.signals] if isinstance(fact_ids, list) else []
        picks.append({"cid": cid, "reason": reason, "fact_ids": fact_ids})

    confidence = str(obj.get("confidence", "")).strip().lower() or None
    why = obj.get("why")
    why = str(why).strip() if isinstance(why, str) else None
    return picks, confidence, why, None


def _pick_pairs(picks, a: Analysis) -> list[list[str]] | None:
    """picks -> [[component, reason], ...] for the trace (PLAN §4)."""
    if not picks:
        return None
    known = {c.cid: c for c in a.candidates}
    return [[known[p["cid"]].component, p["reason"]] for p in picks]


def _models_for(tier: list[str]) -> list[str]:
    return [os.environ["RCA_MODEL"]] if os.environ.get("RCA_MODEL") else list(tier)


def _reason_only_suffix(a: Analysis) -> str:
    if not os.environ.get("ORIGIN_REASON_ONLY") or not a.candidates:
        return ""
    top = a.candidates[0]
    return REASON_ONLY.format(cid=top.cid, component=top.component)


def _call(llm, models, sheet: str, suffix: str, a: Analysis, max_tokens: int,
          thinking_off: bool) -> tuple[str, float]:
    prompt = (sheet + "\n\n" + PROMPT.format(n=a.case.n_failures)
              + _reason_only_suffix(a) + suffix)
    kwargs = {"max_tokens": max_tokens, "temperature": 0, "timeout": CALL_TIMEOUT_S}
    if thinking_off:
        kwargs["extra_body"] = THINKING_OFF
    t0 = time.time()
    text = llm.ask(models, prompt, **kwargs)
    return text, time.time() - t0


# --- the route ----------------------------------------------------------------

def route(a: Analysis, llm, mode: str, deadline: float) -> dict:
    d: dict = {"route": "engine_only", "picks": None, "confidence_model": None,
               "why": None, "flash": None, "strong": None, "errors": [], "notes": [],
               "seconds": {"flash": 0.0, "strong": 0.0},
               "flash_pick": None, "strong_pick": None, "sheet": ""}

    if not a.candidates:
        d["notes"].append("no candidates: nothing to ask a model about")
        return d
    if mode == "engine" or llm is None:
        d["notes"].append("engine mode" if mode == "engine" else "no LLM client")
        return d

    n = a.case.n_failures
    d["sheet"] = sheet = fact_sheet(a)

    # --- single-model ablation: one call, no gate, no escalation --------------
    if mode == "single":
        models = _models_for(CHEAP)
        is_flash = all("Flash" in m for m in models)
        try:
            text, secs = _call(llm, models, sheet, "", a,
                               CHEAP_MAX_TOKENS if is_flash else STRONG_MAX_TOKENS,
                               thinking_off=True)
            d["seconds"]["flash"] = secs
            picks, conf, why, err = parse_reply(text, a)
            d["flash"] = {"models": models, "seconds": secs, "error": err}
            if picks:
                d.update(route="flash", picks=picks, confidence_model=conf, why=why,
                         flash_pick=_pick_pairs(picks, a))
            else:
                d["route"] = "fallback"
                d["errors"].append(f"single: {err}")
        except Exception as e:
            d["route"] = "fallback"
            d["errors"].append(f"single: {type(e).__name__}: {e}")
        return d

    # --- gate: the engine is clear enough that a model cannot help ------------
    top = a.candidates[0]
    if a.margin >= GATE_MARGIN and top.support >= GATE_SUPPORT and n == 1:
        d["route"] = "gate"
        d["notes"].append(f"gated: margin {a.margin:.2f} >= {GATE_MARGIN} and "
                          f"{top.support} independent signals on {top.cid}")
        return d

    # --- flash ----------------------------------------------------------------
    flash_picks = None
    try:
        text, secs = _call(llm, CHEAP, sheet, "", a, CHEAP_MAX_TOKENS, thinking_off=True)
        d["seconds"]["flash"] = secs
        flash_picks, conf, why, err = parse_reply(text, a)
        d["flash"] = {"models": list(CHEAP), "seconds": secs, "error": err}
        if flash_picks:
            d.update(route="flash", picks=flash_picks, confidence_model=conf, why=why,
                     flash_pick=_pick_pairs(flash_picks, a))
        else:
            d["errors"].append(f"flash: {err}")
    except Exception as e:
        d["flash"] = {"models": list(CHEAP), "seconds": d["seconds"]["flash"],
                      "error": f"{type(e).__name__}: {e}"}
        d["errors"].append(f"flash: {type(e).__name__}: {e}")

    # --- escalate? -------------------------------------------------------------
    why_escalate = []
    if flash_picks is None:
        why_escalate.append("Flash gave no usable answer")
    else:
        known = {c.cid: c for c in a.candidates}
        if known[flash_picks[0]["cid"]].component != a.candidates[0].component:
            why_escalate.append("Flash disagreed with the engine's top candidate")
    if a.margin < ESCALATE_MARGIN:
        why_escalate.append(f"margin {a.margin:.2f} below {ESCALATE_MARGIN}")
    if n >= 2:
        why_escalate.append(f"{n} failures to separate")
    # "The question asks for all three fields" was meant to catch hard cases, but
    # nearly every task asks all three, so on the holdout it sent 86% of cases to
    # GLM-5.2 on its own -- the gate barely fired and `routed` collapsed into
    # `single-strong`. ORIGIN_NO_ASK3=1 drops the trigger so escalation is decided
    # by ambiguity alone; measured as the `routed-tight` config.
    if (all(a.case.asks.get(k) for k in ("datetime", "component", "reason"))
            and not os.environ.get("ORIGIN_NO_ASK3")):
        why_escalate.append("all three fields asked")

    if not why_escalate:
        if flash_picks is None:
            d["route"] = "fallback"
        return d

    if os.environ.get("ORIGIN_NO_STRONG"):
        # Measured on dev_tune: the strong tier is the whole of the accuracy loss
        # (30 escalated cases, engine 0.447 -> 0.325), while Flash never changed an
        # answer either way. ORIGIN_NO_STRONG=1 keeps the gate and the cheap tier
        # and stops there; measured as the `routed-flash` config.
        d["notes"].append("escalation disabled (ORIGIN_NO_STRONG)")
        if flash_picks is None:
            d["route"] = "fallback"
        return d

    remaining = deadline - time.time()
    if remaining < STRONG_MIN_REMAINING_S:
        d["notes"].append(f"escalation skipped: {remaining:.0f}s left, "
                          f"under the {STRONG_MIN_REMAINING_S}s a strong call needs")
        if flash_picks is None:
            d["route"] = "fallback"
        return d

    d["notes"].append("escalated: " + "; ".join(why_escalate))
    suffix = SECOND_OPINION.format(
        picks=_pick_pairs(flash_picks, a)) if flash_picks else \
        "\nA fast model failed to answer. The engine's top candidate is C1. Decide independently."
    try:
        # Thinking OFF here too. PLAN Phase 3 said to leave it on for the strong
        # tier, which contradicts the CP1 decision ("thinking OFF on every call").
        # Measured on GLM-5.2 with this exact prompt, 3 calls each:
        #   ON : 2/3 parsed, 9.5-28.7 s, 506-700 out tok (one hit the cap, no JSON)
        #   OFF: 3/3 parsed, 2.4-10.7 s, 146-163 out tok
        # ON is worse on all three of SPEC's axes, and 2/3 of those calls exceeded
        # CALL_TIMEOUT_S anyway -- which would trip llm.py's breaker and silently
        # demote us to GLM-5.1 for the rest of the run. Logged in PLAN at CP3.
        text, secs = _call(llm, STRONG, sheet, suffix, a, STRONG_MAX_TOKENS,
                           thinking_off=True)
        d["seconds"]["strong"] = secs
        picks, conf, why, err = parse_reply(text, a)
        d["strong"] = {"models": list(STRONG), "seconds": secs, "error": err}
        if picks:
            d.update(route="strong", picks=picks, confidence_model=conf, why=why,
                     strong_pick=_pick_pairs(picks, a))
        else:
            d["errors"].append(f"strong: {err}")
            if flash_picks is None:
                d["route"] = "fallback"
    except Exception as e:
        d["strong"] = {"models": list(STRONG), "seconds": d["seconds"]["strong"],
                       "error": f"{type(e).__name__}: {e}"}
        d["errors"].append(f"strong: {type(e).__name__}: {e}")
        if flash_picks is None:
            d["route"] = "fallback"
    return d
