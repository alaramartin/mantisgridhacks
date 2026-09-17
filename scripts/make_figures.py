#!/usr/bin/env python3
"""Presentation / REPORT figures. Run OUTSIDE Docker (matplotlib is not in requirements.txt):

    python scripts/make_figures.py --row 38

Writes PNGs into docs/figures/. Every number plotted comes from the same engine the agent runs,
and the series panels are raw rows from the CSVs, so a figure cannot claim more than the evidence.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.patches import FancyArrowPatch

from origin.case import parse_instruction
from origin.contract import fmt_ts
from origin.engine import analyze
from origin.load import load_window

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "figures"
INK, MUTE, HL, OK2 = "#22272e", "#8b949e", "#c0392b", "#2f6f4f"
plt.rcParams.update({"figure.dpi": 160, "font.size": 9, "axes.edgecolor": MUTE,
                     "axes.labelcolor": INK, "text.color": INK, "xtick.color": MUTE,
                     "ytick.color": MUTE, "axes.titlesize": 10, "axes.titleweight": "bold",
                     "axes.spines.top": False, "axes.spines.right": False})


def _hhmm(ax):
    ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: fmt_ts(v)[11:16]))


def fig_signal(a, w, out: Path) -> None:
    """Panel 1: what 'outside its normal range' means, on the fact behind the answer."""
    ans = a.engine_answers[0]
    sig = a.signals[ans["signal_ids"][0]]
    m = w.metrics
    g = m[(m.cmdb_id == sig.cmdb_id) & (m.kpi == sig.kpi)].sort_values("ts")
    base = g[(g.ts >= w.base_lo_ts) & (g.ts < w.base_hi_ts)]
    fig, (ax, ax2) = plt.subplots(1, 2, figsize=(10.5, 3.4), gridspec_kw={"width_ratios": [1.45, 1]})

    ax.axvspan(w.base_lo_ts, w.base_hi_ts, color="#f0f2f5", zorder=0)
    ax.axhspan(base.value.min(), base.value.max(), color=OK2, alpha=0.10, zorder=1,
               label="range it held all baseline hour")
    ax.plot(g.ts, g.value, color=INK, lw=1.2, zorder=3)
    ax.axvline(a.case.lo_ts, color=MUTE, ls=":", lw=1)
    ax.axvline(sig.onset_ts, color=HL, lw=1.4, zorder=4)
    ax.annotate(f"first went wrong\n{fmt_ts(sig.onset_ts)[11:]}  (ts {int(sig.onset_ts)})",
                xy=(sig.onset_ts, sig.first_value or base.value.median()),
                xytext=(14, -26), textcoords="offset points", color=HL, fontsize=8,
                arrowprops=dict(arrowstyle="->", color=HL, lw=0.9))
    ax.scatter([sig.peak_ts], [sig.peak_value], color=HL, s=22, zorder=5)
    ax.annotate(f"peak {sig.peak_value:g}", xy=(sig.peak_ts, sig.peak_value), xytext=(10, 14),
                textcoords="offset points", color=HL, fontsize=8,
                arrowprops=dict(arrowstyle="-", color=HL, lw=0.7))
    ax.text(w.base_lo_ts + 300, ax.get_ylim()[1] * 0.96, "baseline: the hour before", color=MUTE, fontsize=8, va="top")
    ax.text(a.case.lo_ts + 120, ax.get_ylim()[1] * 0.96, "the 30-minute case window", color=MUTE, fontsize=8, va="top")
    ax.set_title(f"{sig.cmdb_id} · {sig.kpi}", loc="left")
    ax.set_ylabel(sig.kpi.split(".")[-1])
    ax.legend(loc="upper left", frameon=False, fontsize=7.5, bbox_to_anchor=(0, 0.88))
    _hhmm(ax)

    # onsets of the top candidates: the ordering argument, in one strip
    cands = [c for c in a.candidates[:6] if c.onset_ts]
    for i, c in enumerate(cands):
        chosen = c.component == ans["component"]
        col = HL if chosen else (MUTE if c.demoted_by else INK)
        ax2.plot([c.onset_ts], [c.score], "o", ms=8 if chosen else 5, color=col)
        ax2.annotate(f"{c.component}{'  ← answer' if chosen else ('  (demoted)' if c.demoted_by else '')}",
                     (c.onset_ts, c.score), textcoords="offset points",
                     xytext=(9, 4 if i % 2 == 0 else -11), fontsize=7.5, color=col)
    ax2.set_xlim(a.case.lo_ts - 90, a.case.hi_ts + 240)
    ax2.axvline(a.case.lo_ts, color=MUTE, ls=":", lw=1)
    ax2.set_ylabel("engine score (how far outside normal,\nafter checking what it depends on)", fontsize=7.5)
    ax2.set_title("every suspect: when it broke, and how strong", loc="left")
    _hhmm(ax2)
    fig.tight_layout(); fig.savefig(out, bbox_inches="tight"); plt.close(fig)


def fig_topology(a, w, out: Path) -> None:
    """Panel 2: the topology is in the names, and it is lopsided in this bundle -- only two of the six
    nodes host application pods (36 on one, 6 on the other), which is exactly why a node looks anomalous
    whenever any of its pods is. Shows the components this case actually touched, not the full inventory."""
    ans = {x["component"] for x in a.engine_answers}
    anom = {c.component for c in a.candidates}
    edges = w.edges
    pairs = (edges.groupby(["caller", "callee"], observed=True).size().sort_values(ascending=False)
             if len(edges) else pd.Series(dtype=int))
    top_pairs = [pr for pr in pairs.index[:8]]
    show = {p for pr in top_pairs for p in pr} | (anom & set(w.pods)) | (ans & set(w.pods))
    show = set(sorted(show)[:14])
    nodes = sorted(w.nodes)
    hosts = {n: [p for p in sorted(show) if w.pod_node.get(p) == n] for n in nodes}
    fig, ax = plt.subplots(figsize=(11, 4.6))
    pos: dict[str, tuple[float, float]] = {}
    x = 0.0
    for n in nodes:
        pods = hosts[n]
        span = max(len(pods), 1)
        for j, pod in enumerate(pods):
            pos[pod] = (x + j * 1.35, 1.0)
        cx = x + (span - 1) * 1.35 / 2
        ax.plot([cx], [0], "o", ms=17, color=HL if n in ans else (INK if n in anom else "#ccd2d8"), zorder=4)
        ax.text(cx, -0.16, n, ha="center", va="top", fontsize=9.5, color=HL if n in ans else INK,
                fontweight="bold" if n in ans else "normal")
        if not pods:
            ax.text(cx, -0.30, "(no pods)", ha="center", va="top", fontsize=7, color=MUTE)
        for pod in pods:
            ax.plot([cx, pos[pod][0]], [0.09, 0.93], color="#e4e8ec", lw=0.9, zorder=1)
        x += span * 1.35 + 0.9
    for caller, callee in top_pairs:
        if caller in pos and callee in pos:
            hot = callee in ans or caller in ans or (caller in anom and callee in anom)
            ax.add_patch(FancyArrowPatch(pos[caller], pos[callee], connectionstyle="arc3,rad=0.3",
                                         arrowstyle="-|>", mutation_scale=9, lw=1.5 if hot else 0.8,
                                         color=HL if hot else "#aeb6bf", alpha=0.9, zorder=2,
                                         shrinkA=8, shrinkB=10))
    for pod, (px_, py_) in pos.items():
        c = HL if pod in ans else (INK if pod in anom else "#9aa4af")
        ax.plot([px_], [py_], "s", ms=8, color=c, zorder=3)
        ax.text(px_, py_ + 0.07, pod, fontsize=7.2, rotation=32, ha="left", va="bottom", color=c,
                fontweight="bold" if pod in ans else "normal")
    ax.text(-1.1, 0, "nodes", fontsize=9, color=MUTE, ha="right", va="center")
    ax.text(-1.1, 1.0, "pods", fontsize=9, color=MUTE, ha="right", va="center")
    ax.text(-1.1, 1.34, "calls\n(traces)", fontsize=8, color=MUTE, ha="right", va="center")
    ax.set_xlim(-4.0, x + 0.4); ax.set_ylim(-0.75, 1.95); ax.axis("off")
    ax.set_title("topology rebuilt from the telemetry alone: pod \u2192 node from the metric ids, "
                 "pod \u2192 pod from trace parent/child pairs\n"
                 f"red = the answer \u00b7 dark = anomalous in this window \u00b7 grey = normal \u2014 "
                 f"showing the {len(show)} components this case touched of {len(w.pods)} pods on "
                 f"{len(w.nodes)} nodes, and {len(top_pairs)} of {len(pairs)} call edges",
                 loc="left", fontsize=9)
    fig.tight_layout(); fig.savefig(out, bbox_inches="tight"); plt.close(fig)


def fig_cost(runs: Path, out: Path) -> None:
    """Panel 3: the accuracy-vs-cost curve, from eval/results/runs.csv (holdout rows if present)."""
    if not runs.exists():
        print("no runs.csv yet, skipping the cost figure"); return
    d = pd.read_csv(runs)
    d = d[d.split == "holdout"] if (d.split == "holdout").any() else d[d.split == "dev_tune"]
    if d.empty:
        print("no rows to plot"); return
    split = d.split.iloc[0]
    g = d.groupby("config").agg(score=("mean_score", "mean"), sd=("mean_score", "std"),
                                dollars=("dollars_mean", "mean"), secs=("s_per_case_mean", "mean")).reset_index()
    fig, ax = plt.subplots(figsize=(6.4, 4))
    for r in g.itertuples():
        hot = r.config == "routed"
        ax.errorbar(max(r.dollars, 1e-5), r.score, yerr=(0 if pd.isna(r.sd) else r.sd),
                    fmt="o", ms=9 if hot else 6, color=HL if hot else INK, capsize=3, lw=1)
        ax.annotate(f"{r.config}\n{r.score:.3f} · ${r.dollars:.4f}/case · {r.secs:.0f}s",
                    (max(r.dollars, 1e-5), r.score), textcoords="offset points",
                    xytext=(10, -2), fontsize=7.5, color=HL if hot else INK)
    ax.set_xscale("log"); ax.set_xlabel("$ per case (log scale; free configs pinned at 1e-5)")
    ax.set_ylabel("mean score")
    ax.set_title(f"accuracy vs cost — {split} ({int(d.n.iloc[0])} cases)", loc="left")
    fig.tight_layout(); fig.savefig(out, bbox_inches="tight"); plt.close(fig)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--row", type=int, default=38, help="dev row_id for the case figures")
    p.add_argument("--dataset", default=str(ROOT / "data" / "Market-cloudbed-1"))
    args = p.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    q = pd.read_csv(Path(args.dataset) / "dev" / "query_dev.csv")
    instr = q[q.row_id == args.row].instruction.iloc[0]
    a = analyze(instr, Path(args.dataset))
    w = load_window(parse_instruction(instr), Path(args.dataset))
    fig_signal(a, w, OUT / "signal.png")
    fig_topology(a, w, OUT / "topology.png")
    fig_cost(ROOT / "eval" / "results" / "runs.csv", OUT / "cost.png")
    print("wrote", ", ".join(str(p.relative_to(ROOT)) for p in sorted(OUT.glob("*.png"))))


if __name__ == "__main__":
    main()
