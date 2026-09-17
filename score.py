#!/usr/bin/env python3
"""Score predictions against a dev split that still has `scoring_points`.

    python score.py --predictions out/predictions.csv --queries <dev/query_dev.csv>

The scoring logic is OpenRCA's `main.evaluate`, vendored unchanged (MIT) so the
starter is self-contained. We score your submission with the same code.

Two rules that cost people real marks:

  * Wrong failure COUNT scores zero for the whole case, however right the rest is.
    The number of objects in your JSON must match the number of failures.
  * A case is scored on only the elements its scoring points mention. Extra
    fields are harmless; missing ones are not.
"""
from __future__ import annotations

import argparse
import itertools
import re
from datetime import datetime

import pandas as pd

DIFFICULTY = {"task_1": "easy", "task_2": "easy", "task_3": "easy",
              "task_4": "middle", "task_5": "middle", "task_6": "middle",
              "task_7": "hard"}


def evaluate(prediction: str, scoring_points: str):
    predict_pattern = (
        r'{\s*'
        r'(?:"root cause occurrence datetime":\s*"(.*?)")?,?\s*'
        r'(?:"root cause component":\s*"(.*?)")?,?\s*'
        r'(?:"root cause reason":\s*"(.*?)")?\s*}'
    )
    predict_results = [
        {"root cause occurrence datetime": d, "root cause component": c,
         "root cause reason": r}
        for d, c, r in re.findall(predict_pattern, str(prediction))
    ]
    prediction_length = len(predict_results)

    components = re.findall(
        r"The (?:\d+-th|only) predicted root cause component is ([^\n]+)", scoring_points)
    reasons = re.findall(
        r"The (?:\d+-th|only) predicted root cause reason is ([^\n]+)", scoring_points)
    times = re.findall(
        r"The (?:\d+-th|only) root cause occurrence time is within 1 minutes "
        r"\(i.e., <=1min\) of ([^\n]+)", scoring_points)

    scoringpoints_length = max(len(components), len(reasons), len(times))
    scores_num = len(components) + len(reasons) + len(times)

    def close_enough(a: str, b: str) -> bool:
        try:
            t1 = datetime.strptime(a, "%Y-%m-%d %H:%M:%S")
            t2 = datetime.strptime(b, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return False
        return abs((t1 - t2).total_seconds()) <= 60

    best, passing = -1, []
    if scoringpoints_length == prediction_length:
        for perm in itertools.permutations(predict_results):
            cur, cur_pass = 0, []
            for i in range(scoringpoints_length):
                if len(components) == scoringpoints_length and \
                        perm[i]["root cause component"] == components[i]:
                    cur += 1; cur_pass.append(components[i])
                if len(reasons) == scoringpoints_length and \
                        perm[i]["root cause reason"] == reasons[i]:
                    cur += 1; cur_pass.append(reasons[i])
                if len(times) == scoringpoints_length and \
                        close_enough(times[i], perm[i]["root cause occurrence datetime"]):
                    cur += 1; cur_pass.append(times[i])
            if cur > best:
                best, passing = cur, cur_pass
    scores_get = max(best, 0)
    failing = list(set(components + reasons + times) - set(passing))
    return passing, failing, round(scores_get / scores_num, 2) if scores_num else 0.0


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--predictions", required=True)
    p.add_argument("--queries", required=True, help="a split WITH scoring_points")
    p.add_argument("--report", default="")
    args = p.parse_args()

    pred = pd.read_csv(args.predictions)
    q = pd.read_csv(args.queries)
    if "scoring_points" not in q.columns:
        raise SystemExit("that query file has no scoring_points -- use the dev split")

    q = q[q.row_id.isin(set(pred.row_id))] if "row_id" in q.columns else q
    m = pred.merge(q, on="row_id", suffixes=("", "_q"))

    rows = []
    for r in m.itertuples(index=False):
        passed, failed, sc = evaluate(r.prediction, r.scoring_points)
        rows.append({"row_id": r.row_id, "task_index": r.task_index,
                     "difficulty": DIFFICULTY.get(r.task_index, "?"),
                     "score": sc, "passed": "; ".join(passed),
                     "failed": "; ".join(failed)})
    d = pd.DataFrame(rows)

    print(f"\ncases scored: {len(d)}")
    print(f"mean score  : {d.score.mean():.3f}")
    print(f"fully solved: {(d.score == 1.0).sum()} / {len(d)}"
          f"  ({(d.score == 1.0).mean():.1%})")
    print("\nby difficulty")
    g = d.groupby("difficulty").score.agg(["size", "mean"])
    for k in ("easy", "middle", "hard"):
        if k in g.index:
            print(f"  {k:<7}{int(g.loc[k, 'size']):>4} cases   mean {g.loc[k, 'mean']:.3f}")
    print("\nby task")
    for t, sub in d.groupby("task_index"):
        print(f"  {t}  {len(sub):>3} cases   mean {sub.score.mean():.3f}")
    if args.report:
        d.to_csv(args.report, index=False)
        print(f"\nper-case detail -> {args.report}")


if __name__ == "__main__":
    main()
