#!/usr/bin/env python3
"""Turn tokens per model into dollars.

    python cost.py ../out/dev/usage.jsonl

run.py writes usage.jsonl: one line per case, with the tokens each model used
under "models". This prices them at PRICES, the table in docs/models.md, which is
also what your judged run is priced at. Featherless publishes its live prices at
https://api.featherless.ai/v1/models.

From your own eval harness:

    from cost import dollars
    dollars({"zai-org/GLM-5.2": {"prompt_tokens": 400_000, "completion_tokens": 30_000}})
"""
from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path

# $ per million tokens: (input, output)
PRICES = {
    "zai-org/GLM-4.7-Flash": (0.065, 0.40),
    "zai-org/GLM-5.3-Flash": (0.15, 0.50),
    "zai-org/GLM-4.6":       (0.55, 2.20),
    "zai-org/GLM-4.7":       (0.55, 2.20),
    "zai-org/GLM-5":         (0.95, 3.15),
    "zai-org/GLM-5.1":       (1.30, 4.30),
    "zai-org/GLM-5.2":       (1.40, 4.40),
}


def by_model(models: dict) -> dict[str, float]:
    """{model: {"prompt_tokens", "completion_tokens"}} -> {model: dollars}."""
    out = {}
    for m, u in models.items():
        if m not in PRICES:
            raise KeyError(f"no price for {m!r} -- the GLM family is: {', '.join(PRICES)}")
        p_in, p_out = PRICES[m]
        out[m] = (u.get("prompt_tokens", 0) * p_in + u.get("completion_tokens", 0) * p_out) / 1e6
    return out


def dollars(models: dict) -> float:
    return sum(by_model(models).values())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("usage", type=Path, help="usage.jsonl from run.py")
    args = ap.parse_args()

    cases = {}   # row_id -> record; a re-run appends, so the last line for a case wins
    for line in args.usage.read_text().splitlines():
        if line.strip():
            r = json.loads(line)
            cases[r["row_id"]] = r
    if not cases:
        print("no cases in", args.usage)
        return

    per_case, per_model = {}, {}
    for rid, r in sorted(cases.items()):
        c = by_model(r.get("models", {}))
        per_case[rid] = sum(c.values())
        for m, d in c.items():
            per_model[m] = per_model.get(m, 0.0) + d

    print(f"{'row':>5}  {'dollars':>9}")
    for rid, d in per_case.items():
        print(f"{rid:>5}  {d:>9.4f}")
    total = sum(per_case.values())
    vals = list(per_case.values())
    print(f"\n{len(vals)} case(s): total ${total:.4f}, mean ${statistics.mean(vals):.4f}, "
          f"median ${statistics.median(vals):.4f}, max ${max(vals):.4f} per case")
    if per_model:
        print("\nby model:")
        for m, d in sorted(per_model.items(), key=lambda kv: -kv[1]):
            share = d / total if total else 0.0
            print(f"  {m:<24} ${d:>9.4f}  {share:>4.0%}")


if __name__ == "__main__":
    main()
