#!/usr/bin/env python3
"""Check a submission before submitting it.

    python scripts/validate_submission.py --submission <dir> \
        --dataset data/Market-cloudbed-1 --queries data/Market-cloudbed-1/dev/query_dev.csv

Runs your agent on 2 cases and checks the SHAPE of what comes out. It does not
check whether you are right -- `score.py` does that. It checks the things that
make a submission unjudgeable, which is a far worse outcome than a low score.
"""
from __future__ import annotations

import argparse
import json
import re
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pandas as pd

OK, WARN, BAD = "  ok  ", " warn ", " FAIL "
issues, warnings = 0, 0


def say(level: str, msg: str) -> None:
    global issues, warnings
    print(f"{level}  {msg}")
    if level == BAD:
        issues += 1
    elif level == WARN:
        warnings += 1


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--submission", required=True, help="dir containing run.py")
    p.add_argument("--dataset", required=True)
    p.add_argument("--queries", required=True)
    p.add_argument("--cases", type=int, default=2)
    p.add_argument("--timeout", type=int, default=1800)
    args = p.parse_args()

    sub = Path(args.submission).resolve()
    if not (sub / "run.py").exists():
        say(BAD, f"no run.py in {sub}")
        raise SystemExit(1)
    say(OK, "run.py present")

    q = pd.read_csv(args.queries)
    out = Path(tempfile.mkdtemp(prefix="t1validate-"))

    cmd = [sys.executable, "run.py", "--dataset", str(Path(args.dataset).resolve()),
           "--queries", str(Path(args.queries).resolve()), "--out", str(out),
           "--limit", str(args.cases), "--agent", os.environ.get("VAL_AGENT","agents.heuristic")]
    print(f"\n$ {' '.join(cmd)}\n")
    try:
        r = subprocess.run(cmd, cwd=sub, timeout=args.timeout,
                           capture_output=True, text=True)
    except subprocess.TimeoutExpired:
        say(BAD, f"run.py did not finish {args.cases} cases in {args.timeout}s")
        raise SystemExit(1)
    if r.returncode != 0:
        say(BAD, f"run.py exited {r.returncode}")
        print(r.stdout[-2000:]); print(r.stderr[-2000:])
        raise SystemExit(1)
    say(OK, f"run.py completed {args.cases} case(s)")

    pred_file = out / "predictions.csv"
    if not pred_file.exists():
        say(BAD, "no predictions.csv"); raise SystemExit(1)
    pred = pd.read_csv(pred_file)
    for col in ("row_id", "prediction"):
        say(OK if col in pred.columns else BAD, f"predictions.csv has `{col}`")
    if len(pred) != args.cases:
        say(BAD, f"predictions.csv has {len(pred)} rows, expected {args.cases}")
    else:
        say(OK, f"predictions.csv has {len(pred)} rows")

    # the trap: the evaluator's regex is order-sensitive and fails silently
    order = re.compile(
        r'{\s*(?:"root cause occurrence datetime":\s*"(.*?)")?,?\s*'
        r'(?:"root cause component":\s*"(.*?)")?,?\s*'
        r'(?:"root cause reason":\s*"(.*?)")?\s*}')
    parsed_any = False
    for r_ in pred.itertuples(index=False):
        txt = str(r_.prediction)
        hits = [h for h in order.findall(txt) if any(h)]
        if hits:
            parsed_any = True
        elif txt.strip() in ("", "nan"):
            say(WARN, f"row {r_.row_id}: empty prediction. Blank and wrong both "
                      "score zero, so a guess is free upside")
        else:
            say(BAD, f"row {r_.row_id}: prediction present but the evaluator's regex "
                     "matches nothing in it")
            keys = re.findall(r'"root cause ([a-z ]+)"', txt)
            if keys:
                say(WARN, f"    keys found in this order: {keys[:3]} — required order "
                          "is datetime, component, reason")
    say(OK if parsed_any else BAD, "at least one prediction parses")

    ev = out / "evidence"
    if not ev.is_dir():
        say(BAD, "no evidence/ directory")
    else:
        files = {f.stem for f in ev.glob("*.md")}
        missing = [int(x) for x in pred.row_id if str(x) not in files]
        if missing:
            say(BAD, f"evidence/ missing for row_id(s) {missing}")
        else:
            say(OK, f"evidence/ has one .md per case ({len(files)})")
        thin = [f.name for f in ev.glob("*.md") if len(f.read_text().strip()) < 200]
        if thin:
            say(WARN, f"very short evidence files: {thin} — evidence is 35% of your "
                      "grade, more than accuracy")

    print()
    if issues:
        print(f"{issues} blocking issue(s), {warnings} warning(s). Fix the blockers.")
        raise SystemExit(1)
    print(f"Submission shape is valid. {warnings} warning(s) worth reading.")


if __name__ == "__main__":
    main()
