"""Run one agent configuration over one split and record what it cost.

    python -m eval.run_eval --config heuristic --split dev_tune
    python -m eval.run_eval --config routed --split holdout --repeat 3

Accuracy on its own picks the wrong agent. The three numbers in SPEC's priority
order -- score, dollars per case, seconds per case -- only mean something
together, so every run appends all three, per case and per config, to
`eval/results/`. Two runs of the same config on the same split are two rows, not
one overwritten row: the models are non-deterministic and a single sample of a
routed config is not evidence.

**Holdout discipline.** `--split holdout` is for CP4 and the report. Nobody opens
holdout per-case results before then; tuning against them turns a held-out set
into a training set and the final number stops meaning anything.

run.py is driven as a subprocess rather than imported, because the judged run is
a subprocess: same argv, same environment, same import side effects.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from cost import dollars   # noqa: E402

DATASET = ROOT / "data" / "Market-cloudbed-1"
RESULTS = ROOT / "eval" / "results"
SPLITS = ROOT / "eval" / "splits"

CONFIGS: dict[str, dict] = {
    "heuristic":     {"agent": "agents.heuristic", "env": {}},
    # NOT the pristine starter: agents/routed.py calls our patched llm.py. On an
    # unpatched client this row would score ~0, because every Flash reply arrives
    # in `message.reasoning` and the starter reads only `.content`. Label it that
    # way in REPORT.md if it is ever run. (Not run as of CP4.)
    "starter-routed": {"agent": "agents.routed", "env": {}},
    "engine":        {"agent": "agents.origin", "env": {"ORIGIN_MODE": "engine"}},
    "single-flash":  {"agent": "agents.origin", "env": {"ORIGIN_MODE": "single",
                                                        "RCA_MODEL": "zai-org/GLM-4.7-Flash"}},
    "single-strong": {"agent": "agents.origin", "env": {"ORIGIN_MODE": "single",
                                                        "RCA_MODEL": "zai-org/GLM-5.2"}},
    "routed":        {"agent": "agents.origin", "env": {"ORIGIN_MODE": "routed"}},
    # the gate as designed: escalate on ambiguity only, not because the question
    # happens to ask for all three fields (which nearly every task does)
    # gate -> Flash, never escalate: the strong tier is where the accuracy went
    # the model picks the REASON only; the engine keeps the component and,
    # through it, the timestamp
    "routed-reason": {"agent": "agents.origin", "env": {"ORIGIN_MODE": "routed",
                                                        "ORIGIN_REASON_ONLY": "1"}},
    "routed-flash":  {"agent": "agents.origin", "env": {"ORIGIN_MODE": "routed",
                                                        "ORIGIN_NO_STRONG": "1"}},
    "routed-tight":  {"agent": "agents.origin", "env": {"ORIGIN_MODE": "routed",
                                                        "ORIGIN_NO_ASK3": "1"}},
}

PER_CASE_COLS = ["config", "split", "repeat", "row_id", "task_index", "difficulty",
                 "score", "dollars", "wall_s", "tokens_in", "tokens_out",
                 "route", "confidence", "n_failures", "passed", "failed"]
RUN_COLS = ["config", "split", "repeat", "n", "mean_score", "fully_solved",
            "dollars_mean", "s_per_case_mean", "s_per_case_max",
            "tokens_in_mean", "tokens_out_mean", "wall_total_s",
            "git_sha", "timestamp"]


def load_dotenv() -> None:
    """Nothing in the repo reads `.env` -- there is no python-dotenv, and the agent
    must keep taking its key from the environment the way the judges supply it. But
    an eval run that silently drops to engine-only because the key was not exported
    wastes a slot and looks like a result, so the harness loads it here."""
    f = ROOT / ".env"
    if not f.exists():
        return
    for line in f.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def needs_key(cfg: dict) -> bool:
    return cfg["agent"] in ("agents.origin", "agents.routed") and \
        cfg["env"].get("ORIGIN_MODE") != "engine"


def git_sha() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
                              capture_output=True, text=True, check=True).stdout.strip()
    except Exception:
        return "unknown"


def run_agent(cfg: dict, split_csv: Path, out: Path, limit: int) -> float:
    """Drive run.py exactly as the judges do. Returns wall seconds for the run."""
    out.mkdir(parents=True, exist_ok=True)
    env = os.environ | cfg["env"]
    if cfg["agent"] == "agents.origin":
        # the engine cache is ours, not the judges': it makes repeats affordable.
        env["ORIGIN_ENGINE_CACHE"] = str(ROOT / "cache" / "engine")
    cmd = [sys.executable, "run.py", "--dataset", str(DATASET),
           "--queries", str(split_csv), "--out", str(out), "--agent", cfg["agent"]]
    if limit:
        cmd += ["--limit", str(limit)]
    t0 = time.time()
    subprocess.run(cmd, cwd=ROOT, env=env, check=True)
    return time.time() - t0


def score_run(out: Path, split_csv: Path) -> pd.DataFrame:
    report = out / "per_case.csv"
    subprocess.run([sys.executable, "score.py", "--predictions", str(out / "predictions.csv"),
                    "--queries", str(split_csv), "--report", str(report)],
                   cwd=ROOT, check=True)
    return pd.read_csv(report)


def read_usage(out: Path) -> dict[int, dict]:
    """row_id -> the LAST record for it (a --resume run appends)."""
    path = out / "usage.jsonl"
    if not path.exists():
        return {}
    rows: dict[int, dict] = {}
    for line in path.read_text().splitlines():
        if line.strip():
            r = json.loads(line)
            rows[int(r["row_id"])] = r
    return rows


def read_trace(out: Path) -> dict[str, dict]:
    """sha1(instruction) -> trace record. run.py does not pass row_id to agents,
    so the instruction hash is the only join key we have (PLAN §4)."""
    path = out / "origin_trace.jsonl"
    if not path.exists():
        return {}
    rows: dict[str, dict] = {}
    for line in path.read_text().splitlines():
        if line.strip():
            r = json.loads(line)
            rows[r["instruction_sha1"]] = r
    return rows


def case_seconds(usage_rec: dict, trace_rec: dict) -> float:
    """Wall seconds for a case, made honest about the engine cache.

    A cached engine read costs ~0 s here but will cost its cold seconds in the
    judged run, which has no cache. When the agent records what the cold read
    cost (`seconds.engine_cold`), we bill that instead. REPORT.md says so.
    """
    wall = float(usage_rec.get("wall_s", 0.0))
    secs = (trace_rec or {}).get("seconds") or {}
    cold, warm = secs.get("engine_cold"), secs.get("engine")
    if cold is not None and warm is not None and cold > warm:
        wall += cold - warm
    return wall


def upsert(path: Path, rows: list[dict], cols: list[str]) -> None:
    """Replace any existing rows for this (config, split, repeat), then append.

    A blind append meant re-collecting a run left the old rows beside the new ones
    and every mean was quietly wrong.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fresh = pd.DataFrame(rows, columns=cols)
    if path.exists():
        # Configs are run in parallel terminals (they are independent processes),
        # so two of them can land here at once. A half-written file must not kill a
        # run that has already paid for its API calls -- every row is re-derivable
        # from out/ with --collect-only, so on a bad read we just write our own.
        try:
            old = pd.read_csv(path)
        except Exception:
            old = pd.DataFrame(columns=cols)
        if list(old.columns) == cols and len(old):
            key = ["config", "split", "repeat"]
            tags = set(map(tuple, fresh[key].drop_duplicates().to_numpy().tolist()))
            keep = [t not in tags for t in map(tuple, old[key].to_numpy().tolist())]
            fresh = pd.concat([old[keep], fresh], ignore_index=True)
        elif len(old):
            raise SystemExit(f"{path} has columns {list(old.columns)} but this run "
                             f"writes {cols}. Move it aside and re-collect.")
    tmp = path.with_suffix(".csv.tmp")          # atomic: never leave a torn file
    fresh.to_csv(tmp, index=False)
    os.replace(tmp, path)


def one_run(config: str, split: str, repeat: int, limit: int,
            collect_only: bool = False) -> dict:
    cfg = CONFIGS[config]
    split_csv = SPLITS / f"{split}.csv"
    if not split_csv.exists():
        raise SystemExit(f"no split at {split_csv} -- run eval/split.py first")
    out = ROOT / "out" / "eval" / config / split / f"r{repeat}"
    if not collect_only:
        for stale in ("predictions.csv", "usage.jsonl", "origin_trace.jsonl"):
            (out / stale).unlink(missing_ok=True)   # appended files must not accumulate

    wall_total = 0.0 if collect_only else run_agent(cfg, split_csv, out, limit)
    if collect_only and not (out / "predictions.csv").exists():
        raise SystemExit(f"--collect-only but nothing at {out}")
    scored = score_run(out, split_csv)
    usage = read_usage(out)
    trace = read_trace(out)
    queries = pd.read_csv(split_csv).set_index("row_id")

    rows = []
    for r in scored.itertuples(index=False):
        rid = int(r.row_id)
        u = usage.get(rid, {})
        instruction = str(queries.loc[rid, "instruction"])
        t = trace.get(hashlib.sha1(instruction.encode()).hexdigest(), {})
        rows.append({
            "config": config, "split": split, "repeat": repeat, "row_id": rid,
            "task_index": r.task_index, "score": float(r.score),
            "difficulty": r.difficulty,
            "dollars": round(dollars(u.get("models", {})), 6),
            "wall_s": round(case_seconds(u, t), 2),
            "tokens_in": int(u.get("prompt_tokens", 0) or 0),
            "tokens_out": int(u.get("completion_tokens", 0) or 0),
            "route": t.get("route", ""), "confidence": t.get("confidence", ""),
            "n_failures": t.get("n_failures", ""),
            "passed": r.passed if isinstance(r.passed, str) else "",
            "failed": r.failed if isinstance(r.failed, str) else "",
        })
    upsert(RESULTS / "per_case.csv", rows, PER_CASE_COLS)

    d = pd.DataFrame(rows)
    summary = {
        "config": config, "split": split, "repeat": repeat, "n": len(d),
        "mean_score": round(d.score.mean(), 4),
        "fully_solved": int((d.score == 1.0).sum()),
        "dollars_mean": round(d.dollars.mean(), 6),
        "s_per_case_mean": round(d.wall_s.mean(), 2),
        "s_per_case_max": round(d.wall_s.max(), 2),
        "tokens_in_mean": int(d.tokens_in.mean()),
        "tokens_out_mean": int(d.tokens_out.mean()),
        "wall_total_s": round(wall_total, 1),
        "git_sha": git_sha(),
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    upsert(RESULTS / "runs.csv", [summary], RUN_COLS)
    return summary


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--config", required=True, choices=sorted(CONFIGS))
    p.add_argument("--split", required=True, choices=["holdout", "dev_tune"])
    p.add_argument("--repeat", type=int, default=1, help="run it R times (models vary)")
    p.add_argument("--limit", type=int, default=0, help="first N cases of the split")
    p.add_argument("--collect-only", action="store_true",
                   help="re-derive the results rows from an existing out/ dir, "
                        "without re-running the agent (or paying for it again)")
    args = p.parse_args()

    load_dotenv()
    if needs_key(CONFIGS[args.config]) and not os.environ.get("FEATHERLESS_API_KEY"):
        # P1 lost a routed run to this at CP3: with no key every case quietly took
        # route=engine_only and the summary looked like a real measurement.
        raise SystemExit(f"{args.config!r} calls models but FEATHERLESS_API_KEY is not "
                         f"set and no .env supplied it. Every case would silently fall "
                         f"back to engine-only and the row would be a lie.")

    if args.split == "holdout":
        print("!! HOLDOUT. Summary only until CP4 -- do not open per-case results.\n")
    if os.environ.get("ORIGIN_FIXTURE") == "1":
        # A fixture run answers the same hand-written case every time, and on dev
        # case 0 it happens to be right. Recording that would put a meaningless
        # 0.40 next to the real numbers in eval/results/.
        raise SystemExit("refusing to record a run with ORIGIN_FIXTURE=1 -- the "
                         "fixture is not the engine and its score means nothing")

    summaries = [one_run(args.config, args.split, r, args.limit, args.collect_only)
                 for r in range(1, args.repeat + 1)]

    print("\n" + " ".join(f"{c}" for c in RUN_COLS))
    for s in summaries:
        print("  ".join(str(s[c]) for c in RUN_COLS))
    print(f"\n-> {RESULTS / 'runs.csv'}")


if __name__ == "__main__":
    main()
