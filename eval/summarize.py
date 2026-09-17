"""Turn eval/results/*.csv into the tables REPORT.md quotes.

    python -m eval.summarize            # -> eval/results/summary.md, and stdout

Reads only the committed results files, so the tables can be regenerated from a
fresh clone without the dataset, a key, or a single model call.

Three things this file refuses to do, because each would flatter us:

  * **Average across repeats without showing the spread.** The models are
    non-deterministic; a single routed number is an anecdote. Every mean over
    repeats carries its standard deviation, and n=1 is labelled as such.
  * **Present dev_tune next to holdout without a warning.** Parameters were tuned
    on dev_tune, so its score is optimistic by construction. It gets its own table
    with that said in the heading.
  * **Write a headline it has not computed.** The sentences at the end are
    generated from the numbers, so if the strong model is not better, the sentence
    says the strong model is not better.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from origin.contract import NODE_REASONS, POD_REASONS   # noqa: E402

RESULTS = ROOT / "eval" / "results"
OUT = RESULTS / "summary.md"
REASONS = set(NODE_REASONS) | set(POD_REASONS)
TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$")
ORDER = ["heuristic", "starter-routed", "engine", "single-flash", "single-strong", "routed"]


def f(x, nd=3, dash="--"):
    return dash if pd.isna(x) else f"{x:.{nd}f}"


def table(rows: list[list], header: list[str]) -> list[str]:
    out = ["| " + " | ".join(header) + " |",
           "|" + "|".join("---" for _ in header) + "|"]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return out


def by_config(runs: pd.DataFrame, cases: pd.DataFrame, split: str) -> list[str]:
    """One row per config: accuracy, dollars, seconds, tokens -- together."""
    r, c = runs[runs.split == split], cases[cases.split == split]
    if r.empty:
        return ["_no runs on this split yet._"]
    rows = []
    for name in [n for n in ORDER if n in set(r.config)]:
        g, gc = r[r.config == name], c[c.config == name]
        reps = len(g)
        spread = f"{g.mean_score.mean():.3f}" + (
            f" ± {g.mean_score.std():.3f}" if reps > 1 else " (n=1)")
        solved = f"{g.fully_solved.mean():.1f}/{int(g.n.iloc[0])}"
        dollars = gc.dollars.mean()
        correct = gc.score.sum()
        rows.append([
            f"`{name}`", reps, spread, solved,
            f(gc[gc.difficulty == "easy"].score.mean()),
            f(gc[gc.difficulty == "middle"].score.mean()),
            f(gc[gc.difficulty == "hard"].score.mean()),
            f"${dollars:.4f}",
            f"${dollars * len(gc) / correct:.4f}" if correct else "--",
            f"{gc.wall_s.mean():.1f} / {gc.wall_s.max():.1f}",
            f"{gc.tokens_in.mean():,.0f} / {gc.tokens_out.mean():,.0f}",
        ])
    return table(rows, ["config", "runs", "mean score", "fully solved",
                        "easy", "middle", "hard", "$/case", "$/correct*",
                        "s/case mean/max", "tok in/out"])


def per_task(cases: pd.DataFrame, split: str) -> list[str]:
    c = cases[(cases.split == split) & cases.config.isin(
        ["engine", "single-flash", "single-strong", "routed"])]
    if c.empty:
        return ["_not enough configs yet._"]
    piv = c.pivot_table(index="task_index", columns="config", values="score", aggfunc="mean")
    cols = [x for x in ORDER if x in piv.columns]
    rows = [[t] + [f(piv.loc[t, x]) for x in cols] for t in sorted(piv.index)]
    return table(rows, ["task"] + [f"`{x}`" for x in cols])


def routing(cases: pd.DataFrame) -> list[str]:
    c = cases[(cases.config == "routed") & cases.route.notna()]
    if c.empty:
        return ["_no routed run recorded yet._"]
    rows = []
    for route, g in c.groupby("route"):
        rows.append([f"`{route}`", len(g), f"{len(g) / len(c):.0%}",
                     f(g.score.mean()), f"${g.dollars.mean():.4f}",
                     f"{g.wall_s.mean():.1f}"])
    return table(sorted(rows, key=lambda r: -r[1]),
                 ["route", "cases", "share", "mean score", "$/case", "s/case"])


def calibration(cases: pd.DataFrame) -> list[str]:
    c = cases[cases.config.isin(["routed", "single-strong", "single-flash", "engine"])
              & cases.confidence.notna()]
    if c.empty:
        return ["_no confidence recorded yet._"]
    rows = []
    for level in ("High", "Medium", "Low"):
        g = c[c.confidence == level]
        if len(g):
            rows.append([level, len(g), f"{len(g) / len(c):.0%}", f(g.score.mean()),
                         f"{(g.score == 1.0).sum()}/{len(g)}"])
    out = table(rows, ["confidence", "cases", "share", "mean score", "fully solved"])
    hi, lo = c[c.confidence == "High"], c[c.confidence == "Low"]
    if len(hi) and len(lo):
        verdict = ("calibrated: High scores above Low"
                   if hi.score.mean() > lo.score.mean()
                   else "**NOT calibrated: High does no better than Low.** "
                        "Reported as a negative result rather than quietly dropped")
        out += ["", f"_{verdict} ({f(hi.score.mean())} vs {f(lo.score.mean())})._"]
    return out


def bucket(failed: str) -> str:
    if TIMESTAMP.match(failed.strip()):
        return "time wrong (> 60 s off)"
    if failed.strip() in REASONS:
        return "reason wrong"
    return "component wrong"


def taxonomy(cases: pd.DataFrame) -> list[str]:
    c = cases[cases.config.isin(["routed", "engine", "single-strong"])]
    if c.empty:
        return ["_nothing to classify yet._"]
    counts: dict[tuple[str, str], int] = {}
    for r in c.itertuples(index=False):
        if not isinstance(r.failed, str) or not r.failed.strip():
            continue
        for item in r.failed.split(";"):
            if item.strip():
                counts[(r.config, bucket(item))] = counts.get((r.config, bucket(item)), 0) + 1
    if not counts:
        return ["_every scoring point passed -- nothing to classify._"]
    configs = sorted({k[0] for k in counts}, key=lambda x: ORDER.index(x))
    buckets = sorted({k[1] for k in counts})
    rows = [[b] + [counts.get((cf, b), 0) for cf in configs] for b in buckets]
    rows.append(["**total missed**"] + [sum(v for k, v in counts.items() if k[0] == cf)
                                        for cf in configs])
    return table(rows, ["first thing wrong"] + [f"`{c}`" for c in configs])


def headlines(runs: pd.DataFrame, cases: pd.DataFrame, split: str) -> list[str]:
    r, c = runs[runs.split == split], cases[cases.split == split]
    out = []

    def stat(name):
        g, gc = r[r.config == name], c[c.config == name]
        if g.empty:
            return None
        return {"score": g.mean_score.mean(), "dollars": gc.dollars.mean(),
                "secs": gc.wall_s.mean()}

    routed, strong, flash, eng, heur = (stat(x) for x in
                                        ("routed", "single-strong", "single-flash",
                                         "engine", "heuristic"))
    if routed and strong:
        pct = routed["score"] / strong["score"] if strong["score"] else float("nan")
        cost = routed["dollars"] / strong["dollars"] if strong["dollars"] else float("nan")
        secs = routed["secs"] / strong["secs"] if strong["secs"] else float("nan")
        out.append(f"- **Routing:** routed reached **{pct:.0%}** of single-strong's score "
                   f"at **{cost:.0%}** of its cost and **{secs:.0%}** of its time "
                   f"({f(routed['score'])} vs {f(strong['score'])}, "
                   f"${routed['dollars']:.4f} vs ${strong['dollars']:.4f}).")
        if routed["score"] >= strong["score"]:
            out.append("  Routing lost no accuracy: the gate only fires where the engine "
                       "was already clear.")
    if strong and flash:
        d = strong["score"] - flash["score"]
        x = strong["dollars"] / flash["dollars"] if flash["dollars"] else float("nan")
        verb = f"bought **+{d:.3f}**" if d > 0 else f"**cost us {d:.3f}**"
        out.append(f"- **Is the big model worth it?** GLM-5.2 {verb} over GLM-4.7-Flash "
                   f"for **{x:.0f}x** the dollars"
                   + ("." if d > 0 else " — a negative result, reported as one."))
    if eng and routed:
        d = routed["score"] - eng["score"]
        if d > 0:
            out.append(f"- **Do the models add anything over the engine?** Yes: "
                       f"+{d:.3f} ({f(eng['score'])} -> {f(routed['score'])}) "
                       f"for ${routed['dollars']:.4f} a case.")
        else:
            out.append(f"- **Do the models add anything over the engine?** "
                       f"**No** ({f(eng['score'])} engine vs {f(routed['score'])} routed). "
                       f"The deterministic engine is the product; the models are not "
                       f"paying for themselves. Reported as a negative result.")
    if eng and heur:
        out.append(f"- **Engine vs the free baseline:** {f(eng['score'])} vs "
                   f"{f(heur['score'])}, at $0.00 either way.")
    return out or ["_not enough configs to compute a headline yet._"]


def main() -> None:
    runs = pd.read_csv(RESULTS / "runs.csv")
    cases = pd.read_csv(RESULTS / "per_case.csv")

    md = ["# ORIGIN — evaluation summary", "",
          "_Generated by `python -m eval.summarize` from `eval/results/*.csv`. "
          "Every number here is reproducible from the committed CSVs._", ""]

    md += ["## 1. Holdout (21 cases, never tuned on)", ""]
    md += by_config(runs, cases, "holdout")
    md += ["", "\\* `$/correct` is noisy at n=21 — one case moves it a lot. "
               "Quoted for completeness, not for ranking.", ""]

    md += ["## 2. dev_tune (49 cases) — **tuned on these, so optimistic**", ""]
    md += by_config(runs, cases, "dev_tune")
    md += [""]

    md += ["## 3. Score by task type (holdout)", ""]
    md += per_task(cases, "holdout")
    md += [""]

    md += ["## 4. Where the routing went (`routed`, all splits)", ""]
    md += routing(cases)
    md += [""]

    md += ["## 5. Knowing when it doesn't know (all model configs, splits pooled)", ""]
    md += calibration(cases)
    md += [""]

    md += ["## 6. Failure taxonomy — the first thing wrong, per missed scoring point", ""]
    md += taxonomy(cases)
    md += [""]

    md += ["## 7. Headlines", ""]
    md += headlines(runs, cases, "holdout")
    md += ["", "_Holdout numbers. n=21: a difference of one or two cases is a tie._", ""]

    text = "\n".join(md)
    OUT.write_text(text, encoding="utf-8")
    print(text)
    print(f"\n-> {OUT}")


if __name__ == "__main__":
    main()
