"""The deterministic engine: parse -> load -> signals -> candidates -> engine answers. No LLM.

    python -m origin.engine --row 0                  # one dev case: candidates, answers, facts
    python -m origin.engine --split dev_tune --score # engine-only score on dev-tune (refuses the holdout)

`analyze()` always returns an Analysis: a failed stage is caught, noted, and the answer falls back
to a level-default guess, so the agent can still emit exactly n answers.
Set ORIGIN_ENGINE_CACHE=<dir> to pickle each Analysis by sha1(instruction) (used by the eval).
"""
from __future__ import annotations

import argparse
import hashlib
import os
import pickle
import time
import traceback
from pathlib import Path

from origin.candidates import LEVEL_DEFAULT, engine_answers, rank
from origin.case import parse_instruction
from origin.contract import Analysis, Case, fmt_ts
from origin.facts import render_fact, render_ruled_out
from origin.load import load_window
from origin.signals import build_signals

ROOT = Path(__file__).resolve().parent.parent


def _fallback_case(instruction: str) -> Case:
    return Case(instruction=instruction, n_failures=1, asks={"datetime": True, "component": True, "reason": True},
                lo_ts=0.0, hi_ts=0.0, days=[], notes=["instruction could not be parsed"])


def analyze(instruction: str, dataset_dir: Path, deadline_ts: float | None = None) -> Analysis:
    cache_dir = os.environ.get("ORIGIN_ENGINE_CACHE")
    key = hashlib.sha1(instruction.encode()).hexdigest()
    if cache_dir:
        path = Path(cache_dir) / f"{key}.pkl"
        if path.exists():
            with path.open("rb") as fh:
                return pickle.load(fh)

    t0 = time.time()
    notes: list[str] = []
    timings = {"load_s": 0.0, "signals_s": 0.0, "candidates_s": 0.0, "total_s": 0.0}
    signals, cands, margin, stats, w = {}, [], 0.0, {}, None
    try:
        case = parse_instruction(instruction)
        notes += case.notes
    except Exception as e:                                     # noqa: BLE001 - never crash the case
        case = _fallback_case(instruction)
        notes.append(f"parse failed: {e!r}")
    try:
        if case.hi_ts:
            t = time.time()
            w = load_window(case, Path(dataset_dir), deadline_ts)
            timings["load_s"] = round(time.time() - t, 3)
            stats = dict(w.stats)
            stats["pod_node"] = dict(w.pod_node)
            notes += w.stats.get("notes", [])
    except Exception as e:                                     # noqa: BLE001
        notes.append(f"load failed: {e!r}")
        stats["error"] = traceback.format_exc(limit=3)
    if w is not None:
        try:
            t = time.time()
            signals = build_signals(w, deadline_ts, notes)
            timings["signals_s"] = round(time.time() - t, 3)
        except Exception as e:                                 # noqa: BLE001
            notes.append(f"signals failed: {e!r}")
        try:
            t = time.time()
            cands, margin = rank(w, signals, notes)
            timings["candidates_s"] = round(time.time() - t, 3)
        except Exception as e:                                 # noqa: BLE001
            notes.append(f"candidates failed: {e!r}")
    answers = engine_answers(case, cands, signals)
    if any(not a["component"] for a in answers):               # nothing anomalous at all: still guess
        guess = sorted(w.nodes)[0] if w is not None and w.nodes else "unknown"
        for a in answers:
            if not a["component"]:
                a["component"], a["reason"] = guess, LEVEL_DEFAULT["node"]
        notes.append(f"no anomalous component found; guessed {guess} with the node default reason")
    timings["total_s"] = round(time.time() - t0, 3)
    a = Analysis(case=case, signals=signals, candidates=cands, margin=round(margin, 4), engine_answers=answers,
                 window_stats=stats, timings=timings, notes=notes)
    if cache_dir:
        Path(cache_dir).mkdir(parents=True, exist_ok=True)
        with (Path(cache_dir) / f"{key}.pkl").open("wb") as fh:
            pickle.dump(a, fh)
    return a


def describe(a: Analysis, k: int = 8) -> str:
    """Human-readable dump for one case: candidates, engine answers, facts, ruled out, notes."""
    c = a.case
    lines = [f"window {fmt_ts(c.lo_ts)} – {fmt_ts(c.hi_ts)[11:]} UTC+8 · n={c.n_failures} · asks "
             f"{[x for x, v in c.asks.items() if v]} · {len(a.signals)} facts · margin {a.margin:.2f} · "
             f"timings {a.timings}", "", "CANDIDATES"]
    for cd in a.candidates[:k]:
        on = fmt_ts(cd.onset_ts)[11:] if cd.onset_ts is not None else "-"
        dem = f" · DEMOTED: {cd.demoted_by}" if cd.demoted_by else ""
        pro = f" · over {', '.join(cd.promoted_over)}" if cd.promoted_over else ""
        lines.append(f"  {cd.cid:>3} {cd.component:<26} {cd.level:<7} score {cd.score:5.1f} (raw {cd.raw_score:5.1f}) "
                     f"onset {on} support {cd.support:>3} reason {cd.reasons[0][0]} "
                     f"facts {','.join(cd.signal_ids[:4])}{dem}{pro}")
    lines += ["", "ENGINE ANSWERS"]
    lines += [f"  {x['datetime']} · {x['component']} · {x['reason']} ({x['cid']}; {', '.join(x['signal_ids'][:3])})"
              for x in a.engine_answers]
    shown = [i for x in a.engine_answers for i in x["signal_ids"][:4]]
    lines += ["", "FACTS (answers)"] + [render_fact(a.signals[i]) for i in dict.fromkeys(shown) if i in a.signals]
    lines += ["", "RULED OUT"] + render_ruled_out(a, [x["component"] for x in a.engine_answers])
    lines += ["", "NOTES"] + [f"  {n}" for n in a.notes]
    return "\n".join(lines)


def main() -> None:
    import pandas as pd

    p = argparse.ArgumentParser()
    p.add_argument("--dataset", default=str(ROOT / "data" / "Market-cloudbed-1"))
    p.add_argument("--row", type=int, help="a dev row_id to describe")
    p.add_argument("--split", choices=["dev_tune", "holdout", "all"], help="run every case of a split")
    p.add_argument("--score", action="store_true", help="score engine answers (dev_tune only)")
    p.add_argument("--out", default=str(ROOT / "out" / "engine"))
    args = p.parse_args()
    q = pd.read_csv(Path(args.dataset) / "dev" / "query_dev.csv")

    if args.row is not None:
        r = q[q.row_id == args.row].iloc[0]
        print(f"row {args.row} · {r.task_index}\n")
        print(describe(analyze(r.instruction, Path(args.dataset))))
        return
    if not args.split:
        p.error("give --row or --split")
    if args.score and args.split != "dev_tune":
        p.error("--score is dev_tune only: holdout per-case results stay closed until CP4 (PLAN rule 7)")
    if args.split != "all":
        ids = set(pd.read_csv(ROOT / "eval" / "splits" / f"{args.split}.csv").row_id)
        q = q[q.row_id.isin(ids)]

    from run import format_prediction
    from score import evaluate
    rows = []
    for r in q.itertuples(index=False):
        a = analyze(r.instruction, Path(args.dataset))
        pred = format_prediction([{k: (x[k] if a.case.asks.get(k) else None) for k in ("datetime", "component", "reason")}
                                  for x in a.engine_answers])
        rec = {"row_id": r.row_id, "task_index": r.task_index, "seconds": a.timings["total_s"],
               "margin": a.margin, "prediction": pred}
        if args.score:
            passed, failed, sc = evaluate(pred, r.scoring_points)
            rec.update(score=sc, passed="; ".join(passed), failed="; ".join(failed))
        rows.append(rec)
        print(f"  row {r.row_id:>3} {a.timings['total_s']:5.1f}s " + (f"score {rec['score']:.2f} " if args.score else "")
              + " | ".join(f"{x['datetime'][11:]} {x['component']} {x['reason']}" for x in a.engine_answers), flush=True)
    d = pd.DataFrame(rows)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    d.to_csv(out / f"engine_{args.split}_per_case.csv", index=False)
    print(f"\n{len(d)} cases · seconds mean {d.seconds.mean():.1f} max {d.seconds.max():.1f}")
    if args.score:
        print(f"engine {args.split}: mean {d.score.mean():.3f} · fully solved {(d.score == 1).sum()}/{len(d)}")
        print(d.groupby("task_index").score.mean().round(3).to_string())
    print(f"per case -> {out / f'engine_{args.split}_per_case.csv'}")


if __name__ == "__main__":
    main()
