"""Turning a model's pick into the answer, and deciding how much to trust it.

The model chose a candidate ID and a reason. Everything else in the answer is
filled in here, from the data: the component name comes from the candidate, the
timestamp from the onset of the signal that actually votes for the chosen reason.
A model never writes a name or a number (NON-NEGOTIABLE RULE 1), so it cannot
invent a component that does not exist or a time that nothing supports.

Confidence is not the model's own confidence -- models are famously bad at that,
and the CP1 spike had them answering "high" while getting the JSON shape wrong.
It is computed from things we can check: how far clear the top candidate was, how
many independent signals it had, whether a model overruled the engine, and
whether anything failed along the way.
"""
from __future__ import annotations

import os

from origin.config import ESCALATE_MARGIN, GATE_MARGIN, GATE_SUPPORT
from origin.contract import Analysis, fmt_ts, legal_reasons


def _onset_for(a: Analysis, cand, reason: str) -> float:
    """When the thing we are blaming started.

    The best signal that actually votes for the chosen reason, not the candidate's
    loudest signal: if we say "read I/O load", the time must come from the read
    I/O series, or the answer and its evidence disagree with each other.
    """
    voting = [a.signals[s] for s in cand.signal_ids
              if s in a.signals and reason in (a.signals[s].reason_votes or {})]
    voting = [s for s in voting if s.onset_ts is not None]
    if voting:
        best = max(voting, key=lambda s: (s.reason_votes.get(reason, 0.0), s.score))
        return best.onset_ts
    onsets = [a.signals[s].onset_ts for s in cand.signal_ids
              if s in a.signals and a.signals[s].onset_ts is not None]
    if onsets:
        return min(onsets)
    return cand.onset_ts if cand.onset_ts is not None else a.case.lo_ts


def _answer_from(a: Analysis, cand, reason: str) -> dict:
    return {"datetime": fmt_ts(_onset_for(a, cand, reason)),
            "component": cand.component,
            "reason": reason,
            "cid": cand.cid,
            "signal_ids": list(cand.signal_ids)}


def _confidence(a: Analysis, d: dict, answers: list[dict], notes: list[str]) -> tuple[str, str]:
    route = d.get("route", "fallback")
    engine_top = a.engine_answers[0]["component"] if a.engine_answers else (
        a.candidates[0].component if a.candidates else None)
    final_top = answers[0]["component"] if answers else None
    support = a.candidates[0].support if a.candidates else 0
    model_called = route in ("flash", "strong")

    if route == "fallback":
        return "Low", "the route fell back to the engine after an error, so no model confirmed this."
    if not a.candidates:
        return "Low", "no component crossed the anomaly threshold; this is a guess from the window alone."
    if d.get("errors"):
        return "Low", f"a stage failed ({d['errors'][0]}), so this is the engine's answer, not a confirmed one."
    if a.margin < ESCALATE_MARGIN:
        return "Low", (f"the top two candidates are {a.margin:.0%} apart, which is not a "
                       f"separation -- the runner-up is nearly as good an explanation.")
    if model_called and engine_top and final_top != engine_top:
        return "Low", (f"the model overruled the engine (engine said {engine_top}, "
                       f"final answer is {final_top}); two methods disagreeing is a reason to doubt both.")
    if a.margin >= GATE_MARGIN and support >= GATE_SUPPORT and (
            not model_called or final_top == engine_top):
        agree = "the model agreed" if model_called else "no model was needed"
        return "High", (f"the top candidate is {a.margin:.0%} clear of the next one on "
                        f"{support} independent signals, and {agree}.")
    return "Medium", (f"the top candidate is {a.margin:.0%} clear of the next one on "
                      f"{support} signal(s) -- enough to prefer it, not enough to be sure.")


def validate(a: Analysis, d: dict) -> tuple[list[dict], str, list[str]]:
    """-> (answers, confidence, notes). Exactly `n_failures` answers, always."""
    notes: list[str] = []
    n = max(1, a.case.n_failures)
    known = {c.cid: c for c in a.candidates}
    answers: list[dict] = []

    picks = d.get("picks")
    if picks and os.environ.get("ORIGIN_REASON_ONLY") and a.candidates:
        # Asking the model to keep the engine's component is not enough; one that
        # names a different one anyway must not get it. Measured on the holdout,
        # the models match the engine on reason (55.6%) and lose on component
        # (44-48% vs 55.6%) -- so the engine keeps the component, the model keeps
        # the reason, and the timestamp (derived from the component's signals)
        # stays on the engine's side of the line too.
        from origin.router import pinned_cids
        pins = pinned_cids(a)
        for i, pk in enumerate(picks[:n]):
            # Every slot, not just the first. Two of the six holdout losses were
            # multi-failure cases where the model kept answer 1 and wrecked
            # answer 2 (row 48: it replaced a correct `checkoutservice` with
            # `node-6`), so pinning only the top answer would have missed them.
            if i < len(pins) and pk.get("cid") != pins[i]:
                was, now = known.get(pk.get("cid")), known.get(pins[i])
                notes.append(
                    f"reason-only mode: answer {i + 1} kept the engine's "
                    f"{now.component if now else pins[i]} over the model's "
                    f"{was.component if was else pk.get('cid')}; took only its reason")
                pk["cid"] = pins[i]
    if picks:
        used: set[str] = set()
        for p in picks[:n]:
            cand = known.get(p.get("cid"))
            if cand is None:                      # the router checked this; belt and braces
                notes.append(f"dropped an unknown candidate {p.get('cid')!r}")
                continue
            reason = p.get("reason")
            if reason not in legal_reasons(cand.level):
                fallback = cand.reasons[0][0] if cand.reasons else None
                notes.append(f"{cand.cid}: {reason!r} is not legal for a {cand.level}; "
                             f"used the engine's {fallback!r}")
                reason = fallback
            if reason is None:
                notes.append(f"{cand.cid}: no legal reason available; fell back to the engine answer")
                continue
            if cand.component in used:
                notes.append(f"the model named {cand.component} twice; "
                             "took the next engine answer instead")
                continue
            used.add(cand.component)
            answers.append(_answer_from(a, cand, reason))

    # top up from the engine, then from the ranking, so the count always matches
    if len(answers) < n:
        have = {x["component"] for x in answers}
        for eng in a.engine_answers:
            if len(answers) >= n:
                break
            if eng.get("component") not in have:
                answers.append(dict(eng))
                have.add(eng.get("component"))
    if len(answers) < n:
        have = {x["component"] for x in answers}
        for cand in a.candidates:
            if len(answers) >= n:
                break
            if cand.component in have:
                continue
            reason = cand.reasons[0][0] if cand.reasons else (
                "node CPU load" if cand.level == "node" else "container CPU load")
            if not cand.reasons:
                notes.append(f"{cand.cid}: no KPI voted for a legal reason; used {reason!r}")
            answers.append(_answer_from(a, cand, reason))
            have.add(cand.component)

    answers = answers[:n]
    if len(answers) < n:
        notes.append(f"only {len(answers)} candidate(s) for {n} failure(s); "
                     "padded so the count matches (a wrong count scores zero)")
        while len(answers) < n:
            if answers:
                answers.append(dict(answers[-1]))
            else:
                # Nothing crossed the threshold. Give the window start and leave
                # the component and reason EMPTY rather than inventing a name: a
                # wrong guess scores exactly what a blank does, and a fabricated
                # component in an evidence file is the thing we most want not to do.
                notes.append("no candidate at all: answering with the window start "
                             "and no component -- this case is unsolved, not guessed")
                answers.append({"datetime": fmt_ts(a.case.lo_ts), "component": "",
                                "reason": "", "cid": None, "signal_ids": []})

    # The evaluator permutes, so order does not score -- but chronological order is
    # what a human reading the evidence expects of a multi-failure answer.
    answers.sort(key=lambda x: x.get("datetime") or "")

    confidence, why = _confidence(a, d, answers, notes)
    # evidence reads the sentence from the decision, so it is not buried in notes
    d["confidence_why"] = why
    return answers, confidence, notes
