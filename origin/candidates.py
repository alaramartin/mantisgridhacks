"""Stage 3a: group signals into ranked candidates (node / pod / service), apply the causal filter,
pick legal reasons, and form the engine's answer. No LLM, no component names in code.

`rank()` only needs the window's topology (`pod_node`, `pod_service`); edges come from the
edge signals' "caller → callee" cmdb_id, so it also runs on cached signals.
"""
from __future__ import annotations

import math
from collections import defaultdict

from origin.config import (CAUSAL_DEMOTE, CAUSAL_EARLIER_S, MAX_CANDIDATES, MULTI_FAILURE_SEP_S,
                           NODE_PROMOTE_MEMBER_FRAC, NODE_PROMOTE_MIN_PODS, NODE_PROMOTE_WINDOW_S,
                           NODE_SINGLE_POD_FRAC, ONSET_MIN_FRAC, ONSET_SHIFT_S,
                           REASON_REST_WEIGHT, SERVICE_MEMBER_FRAC, SERVICE_PROMOTE_FRAC,
                           SERVICE_PROMOTE_MIN_PODS, SHARED_CALLEE_BONUS, SIGNAL_MIN_FACTOR)
from origin.contract import Candidate, Case, Signal, fmt_ts, legal_reasons

EDGE_KINDS = ("edge_gap", "edge_errors")
LEVEL_DEFAULT = {"node": "node CPU load", "pod": "container CPU load", "service": "container CPU load"}
# a pod whose signals vote for nothing legal: the reason of its strongest signal's family
KIND_DEFAULT = {"disappear": "container process termination", "edge_gap": "container network latency",
                "edge_errors": "container packet loss", "pod_errors": "container packet loss"}


def _mins(s: float) -> str:
    m = s / 60
    return f"{m:.0f} min" if m >= 1 else f"{s:.0f} s"


def _factor(s: Signal) -> float:
    """How much a signal counts toward ranking: its best reason weight, clipped to [SIGNAL_MIN_FACTOR, 1].
    A noisy kpi that votes for nothing (or weakly) can't make a component the top suspect on its own."""
    return min(1.0, max([SIGNAL_MIN_FACTOR, *s.reason_votes.values()]))


def _onset(sigs: list[Signal]) -> float | None:
    """Earliest onset among the candidate's strong signals (score >= ONSET_MIN_FRAC of its best)."""
    top = max(s.score for s in sigs)
    ons = [s.onset_ts for s in sigs if s.onset_ts is not None and s.score >= ONSET_MIN_FRAC * top]
    return min(ons) if ons else None


def _reasons(level: str, sigs: list[Signal]) -> list[tuple[str, float]]:
    """Per legal reason: its best vote (score × weight) + REASON_REST_WEIGHT × log(1 + other votes)."""
    votes: dict[str, list[float]] = defaultdict(list)
    legal = legal_reasons(level)
    for s in sigs:
        for r, wt in s.reason_votes.items():
            if r in legal and wt > 0:
                votes[r].append(s.score * wt)
    out = [(r, max(v) + REASON_REST_WEIGHT * math.log1p(len(v) - 1)) for r, v in votes.items()]
    return sorted(out, key=lambda x: (-x[1], x[0]))


def _make(component: str, level: str, sigs: list[Signal], notes: list[str]) -> Candidate:
    sigs = sorted(sigs, key=lambda s: (-s.score, s.onset_ts or 0, s.id))
    support = len({(s.cmdb_id, s.kpi) for s in sigs})
    reasons = _reasons(level, sigs)
    if not reasons:
        default = KIND_DEFAULT.get(sigs[0].kind) if level != "node" else None
        reasons = [(default or LEVEL_DEFAULT[level], 0.0)]      # score 0.0 marks a default (noted in rank)
    raw = max(s.score * _factor(s) for s in sigs) + 2 * math.log1p(support)
    return Candidate(cid="", component=component, level=level, score=raw, raw_score=raw, onset_ts=_onset(sigs),
                     support=support, reasons=reasons, signal_ids=[s.id for s in sigs], demoted_by=None,
                     promoted_over=[])


def _demote(c: Candidate, why: str) -> None:
    if c.demoted_by is None:
        c.score = c.raw_score * CAUSAL_DEMOTE
        c.demoted_by = why


def rank(w, signals: dict[str, Signal], notes: list[str] | None = None) -> tuple[list[Candidate], float]:
    """Candidates in rank order (≤ MAX_CANDIDATES, C1…) and the margin (s1 − s2) / s1."""
    notes = notes if notes is not None else []
    by: dict[tuple[str, str], list[Signal]] = defaultdict(list)
    for s in signals.values():
        by[(s.component, s.level)].append(s)
    cands = {comp: _make(comp, lv, sigs, notes) for (comp, lv), sigs in by.items()}
    pod_node, pod_service = w.pod_node, w.pod_service

    # services: most of a service's pods went wrong together -> the service is the suspect
    pods_of: dict[str, list[str]] = defaultdict(list)
    for p, svc in pod_service.items():
        pods_of[svc].append(p)
    for svc, pods in pods_of.items():
        bad = [cands[p] for p in pods if p in cands and cands[p].level == "pod" and cands[p].onset_ts is not None]
        top = max((c.raw_score for c in bad), default=0.0)
        bad = [c for c in bad if c.raw_score >= SERVICE_MEMBER_FRAC * top]
        if len(bad) < SERVICE_PROMOTE_MIN_PODS or len(bad) < SERVICE_PROMOTE_FRAC * len(pods):
            continue
        first = min(c.onset_ts for c in bad)
        bad = [c for c in bad if c.onset_ts - first <= NODE_PROMOTE_WINDOW_S]
        if len(bad) < SERVICE_PROMOTE_MIN_PODS or len(bad) < SERVICE_PROMOTE_FRAC * len(pods):
            continue
        member_sigs = [signals[i] for c in bad for i in c.signal_ids] + by.get((svc, "service"), [])
        sc = _make(svc, "service", member_sigs, notes)
        sc.raw_score = sc.score = max(c.raw_score for c in bad) + 2 * math.log1p(len(bad))
        sc.onset_ts = min(c.onset_ts for c in bad)
        sc.promoted_over = sorted(c.component for c in bad)
        cands[svc] = sc
        for c in bad:
            _demote(c, f"{len(bad)} of {len(pods)} pods of {svc} went wrong within "
                       f"{_mins(NODE_PROMOTE_WINDOW_S)} of each other, so the service is the suspect")

    # nodes: several of a node's pods went wrong around the node's own onset -> the node is the suspect.
    # Exactly one -> the other way round: one pod's own load is what the node metrics are showing.
    promoted_nodes = set()
    for n, nc in list(cands.items()):
        if nc.level != "node" or nc.onset_ts is None:
            continue
        pods = [cands[p] for p, node in pod_node.items() if node == n and p in cands and cands[p].onset_ts is not None
                and abs(cands[p].onset_ts - nc.onset_ts) <= NODE_PROMOTE_WINDOW_S]
        strongest = max((p.raw_score for p in pods), default=0.0)
        pods = [p for p in pods if p.raw_score >= NODE_PROMOTE_MEMBER_FRAC * strongest]   # ignore bystanders
        if len(pods) >= NODE_PROMOTE_MIN_PODS:
            promoted_nodes.add(n)
            nc.score = max(nc.score, max(p.raw_score for p in pods))
            nc.promoted_over = sorted(p.component for p in pods)
            for p in pods:
                _demote(p, f"{len(pods)} pods on {n} went wrong within {_mins(NODE_PROMOTE_WINDOW_S)} of {n} "
                           f"({nc.signal_ids[0]}), so the node is the suspect")
        elif len(pods) == 1 and pods[0].raw_score >= NODE_SINGLE_POD_FRAC * nc.raw_score:
            _demote(nc, f"only one pod on {n} went wrong ({pods[0].component}, {pods[0].signal_ids[0]}), within "
                        f"{_mins(NODE_PROMOTE_WINDOW_S)} of {n}: what {n}'s metrics show is that pod's own load")

    # causal filter: a pod whose node, or a pod it calls, went wrong clearly earlier
    edge_pairs = defaultdict(set)   # callee -> callers with an anomalous edge
    for s in signals.values():
        if s.kind in EDGE_KINDS:
            caller, _, callee = s.cmdb_id.partition(" → ")
            edge_pairs[callee].add(caller)
    for p, c in cands.items():
        if c.level != "pod" or c.onset_ts is None:
            continue
        node = cands.get(pod_node.get(p, ""))
        if node is not None and node.demoted_by and node.component not in promoted_nodes:
            node = None          # the node is itself a symptom of one pod, so it can't demote anything
        if node and node.onset_ts is not None and node.onset_ts < c.onset_ts - CAUSAL_EARLIER_S:
            _demote(c, f"{node.component} (its node) went wrong {_mins(c.onset_ts - node.onset_ts)} earlier "
                       f"({node.signal_ids[0]})")
            continue
        for callee, callers in edge_pairs.items():
            cc = cands.get(callee)
            if p in callers and cc and cc.onset_ts is not None and cc.onset_ts < c.onset_ts - CAUSAL_EARLIER_S:
                _demote(c, f"{callee}, which it calls, went wrong {_mins(c.onset_ts - cc.onset_ts)} earlier "
                           f"({cc.signal_ids[0]})")
                break
    # a callee slowed down on calls from several callers is the network suspect
    for callee, callers in edge_pairs.items():
        if len(callers) >= 2 and callee in cands:
            cands[callee].score += SHARED_CALLEE_BONUS

    out = sorted(cands.values(), key=lambda c: (-c.score, c.onset_ts if c.onset_ts is not None else float("inf"),
                                                c.component))[:MAX_CANDIDATES]
    for i, c in enumerate(out, 1):
        c.cid = f"C{i}"
        if i <= 3 and c.reasons[0][1] == 0.0:
            notes.append(f"{c.cid} {c.component}: no signal voted for a legal reason; "
                         f"used the default '{c.reasons[0][0]}'")
    if not out:
        margin = 0.0
    elif len(out) == 1 or out[0].score <= 0:
        margin = 1.0 if len(out) == 1 else 0.0
    else:
        margin = max(0.0, (out[0].score - out[1].score) / out[0].score)
    return out, margin


def answer_time(c: Candidate, reason: str, signals: dict[str, Signal], case: Case) -> tuple[float, str | None]:
    """Onset of the strongest signal voting for `reason` (else the candidate onset, else the window start)."""
    voting = [signals[i] for i in c.signal_ids if i in signals and reason in signals[i].reason_votes
              and signals[i].onset_ts is not None]
    if voting:
        best = max(voting, key=lambda s: s.score * s.reason_votes[reason])
        return best.onset_ts + ONSET_SHIFT_S, best.id
    if c.onset_ts is not None:
        return c.onset_ts + ONSET_SHIFT_S, None
    return case.lo_ts, None


def engine_answers(case: Case, cands: list[Candidate], signals: dict[str, Signal]) -> list[dict]:
    """Exactly case.n_failures answers, chronological: {"datetime","component","reason","cid","signal_ids"}."""
    n = max(1, case.n_failures)
    chosen: list[Candidate] = []
    for c in cands:
        if len(chosen) >= n:
            break
        if not chosen:
            chosen.append(c)
            continue
        if c.onset_ts is not None and all(o.onset_ts is None or abs(c.onset_ts - o.onset_ts) >= MULTI_FAILURE_SEP_S
                                          for o in chosen):
            chosen.append(c)
    for c in sorted(cands, key=lambda c: -c.raw_score):          # not enough separated ones: next by raw score
        if len(chosen) >= n:
            break
        if c not in chosen:
            chosen.append(c)
    answers = []
    for c in chosen:
        reason = c.reasons[0][0]
        t, _ = answer_time(c, reason, signals, case)
        voting = sorted((i for i in c.signal_ids if reason in signals[i].reason_votes),
                        key=lambda i: -signals[i].score * signals[i].reason_votes[reason])
        ids = list(dict.fromkeys(voting + c.signal_ids))[:6]      # facts for the chosen reason first
        answers.append({"datetime": fmt_ts(t), "component": c.component, "reason": reason, "cid": c.cid,
                        "signal_ids": ids, "_ts": t})
    while len(answers) < n:                                        # still short: repeat the best guess
        if answers:
            answers.append(dict(answers[0], signal_ids=list(answers[0]["signal_ids"])))
        else:
            answers.append({"datetime": fmt_ts(case.lo_ts), "component": "", "reason": LEVEL_DEFAULT["pod"],
                            "cid": None, "signal_ids": [], "_ts": case.lo_ts})
    answers.sort(key=lambda a: a["_ts"])
    for a in answers:
        del a["_ts"]
    return answers
