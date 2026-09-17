#!/usr/bin/env python3
"""Stratified holdout split of the 70 dev cases (PLAN.md, Person 2 Phase 1).

Run once; its output is committed. The rule is deterministic and written into
eval/splits/split.json so anyone can re-derive the same split:

    per task_index, sort that task's row_ids by md5(str(row_id)) and take the
    first min(3, count) as holdout.

    python eval/split.py [--queries data/Market-cloudbed-1/dev/query_dev.csv]

HOLDOUT DISCIPLINE: nothing is tuned on the holdout cases. Tuning happens on
dev_tune only; the holdout is opened once, at CP4.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd

RULE = ("per task_index, sort that task's row_ids by md5(str(row_id)).hexdigest() "
        "and take the first min(3, count) as holdout; the rest is dev_tune")
PER_TASK = 3


def _key(row_id) -> str:
    return hashlib.md5(str(row_id).encode()).hexdigest()


def split(queries: pd.DataFrame, per_task: int = PER_TASK) -> tuple[list[int], list[int]]:
    """-> (holdout row_ids, dev_tune row_ids), both sorted ascending."""
    holdout: list[int] = []
    for _, grp in queries.groupby("task_index", sort=True):
        ids = sorted(grp.row_id.astype(int).tolist(), key=_key)
        holdout.extend(ids[:min(per_task, len(ids))])
    hold = set(holdout)
    dev_tune = [int(r) for r in queries.row_id.astype(int) if int(r) not in hold]
    return sorted(hold), sorted(dev_tune)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--queries", default="data/Market-cloudbed-1/dev/query_dev.csv")
    p.add_argument("--out", default="eval/splits")
    p.add_argument("--per-task", type=int, default=PER_TASK)
    args = p.parse_args()

    queries = pd.read_csv(args.queries)
    hold, tune = split(queries, args.per_task)

    outdir = Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)
    q = queries.set_index(queries.row_id.astype(int))
    q.loc[hold].to_csv(outdir / "holdout.csv", index=False)
    q.loc[tune].to_csv(outdir / "dev_tune.csv", index=False)
    (outdir / "split.json").write_text(json.dumps(
        {"holdout": hold, "dev_tune": tune, "rule": RULE,
         "per_task": args.per_task, "queries": args.queries}, indent=2) + "\n")

    print(f"{len(queries)} cases -> holdout {len(hold)}, dev_tune {len(tune)}")
    print(f"{'task_index':>12}  {'total':>5}  {'holdout':>7}  {'dev_tune':>8}")
    for task, grp in queries.groupby("task_index", sort=True):
        ids = set(grp.row_id.astype(int))
        h = len(ids & set(hold))
        print(f"{str(task):>12}  {len(ids):>5}  {h:>7}  {len(ids) - h:>8}")
    print(f"\nwrote {outdir}/holdout.csv, dev_tune.csv, split.json")


if __name__ == "__main__":
    main()
