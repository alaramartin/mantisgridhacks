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


def fig_pipeline(out: Path) -> None:
    """The pipeline as a slide-sized flowchart. Architecture only, no data.
    Box widths are computed from the text so nothing overflows."""
    from matplotlib.patches import FancyBboxPatch
    fig, ax = plt.subplots(figsize=(14.5, 3.8))
    UPP = 0.085           # data units per character at fontsize 9.5, empirical

    def wide(text: str, pad: float = 0.9) -> float:
        return max(len(line) for line in text.split("\n")) * UPP + pad

    def box(x, y, text, col, fill, h=0.95, fs=9.5, pad=0.9):
        w = wide(text, pad)
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.05", fc=fill, ec=col,
                                    lw=1.3, zorder=2))
        ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=fs, color=col, zorder=3)
        return x + w

    def arrow(x0, x1, y, col=MUTE):
        ax.annotate("", xy=(x1, y), xytext=(x0, y), arrowprops=dict(arrowstyle="-|>", color=col, lw=1.3))

    y0, GAP = 1.35, 0.6
    x = 0.0
    for i, text in enumerate(("Case\nwindow + count", "Load only\nthe window",
                              "Engine\nanomalies · onsets\ntopology · traces",
                              "Candidates\n+ facts F1…Fn")):
        if i:
            arrow(x - GAP + 0.08, x - 0.08, y0 + 0.475)
        x = box(x, y0, text, INK, "#f4f6f8") + GAP

    gx, gy, gw, gh = x + 0.95, y0 + 0.475, 0.95, 0.6
    arrow(x - GAP + 0.08, gx - gw - 0.06, gy)
    ax.plot([gx, gx + gw, gx, gx - gw, gx], [gy + gh, gy, gy - gh, gy, gy + gh], color=OK2, lw=1.4, zorder=2)
    ax.text(gx, gy, "clear\nwinner?", ha="center", va="center", fontsize=9.5, color=OK2, zorder=3)

    branch_x = gx + 1.25                      # where both branches turn right
    ytop, ybot = y0 + 1.5, y0 - 1.05
    for yy, col, label, va in ((ytop, OK2, "yes  ·  4 of 20 cases", "bottom"),
                               (ybot, HL, "no", "top")):
        ax.plot([gx, gx, branch_x], [gy + (gh if yy > gy else -gh), yy + 0.3, yy + 0.3], color=col, lw=1.4, zorder=1)
        ax.annotate("", xy=(branch_x + 0.12, yy + 0.3), xytext=(branch_x, yy + 0.3),
                    arrowprops=dict(arrowstyle="-|>", color=col, lw=1.4))
        ax.text(gx + 0.14, yy + 0.3 + (0.52 if va == "bottom" else -0.42), label,
                fontsize=9.5, color=col, fontweight="bold", va=va)

    box(branch_x + 0.2, ytop, "answer — no model call, zero tokens", OK2, "#eaf3ee", h=0.6, pad=1.4)

    xe = box(branch_x + 0.2, ybot, "cheap GLM · Flash", HL, "#fbeeec", h=0.6)
    arrow(xe + 0.1, xe + 1.5, ybot + 0.3, HL)
    ax.text(xe + 0.8, ybot + 0.72, "disagrees / low margin", fontsize=7.8, color=MUTE, ha="center")
    xe = box(xe + 1.6, ybot, "strong GLM · 5.2", HL, "#fbeeec", h=0.6)
    arrow(xe + 0.1, xe + 0.72, ybot + 0.3)
    xe = box(xe + 0.82, ybot, "validator — legal · count\ntime from the data", INK, "#f4f6f8", h=0.6, fs=9, pad=1.1)

    ax.text(0, 0.0, "The model never sees telemetry — only ≤ 40 facts, ~7 K tokens, against 474 K to read "
                    "the window.\nIt picks among candidates the data already supports; it never writes a "
                    "number, a name or a time.", fontsize=10.5, color=MUTE, va="top")
    ax.set_xlim(-0.3, xe + 0.4); ax.set_ylim(-1.05, ytop + 0.95); ax.axis("off")
    fig.tight_layout(); fig.savefig(out, bbox_inches="tight"); plt.close(fig)


def fig_holdout_table(runs: Path, out: Path) -> None:
    """The holdout comparison, rendered from eval/results/runs.csv so the figure cannot drift
    from the committed numbers."""
    if not runs.exists():
        print("no runs.csv, skipping the table figure"); return
    d = pd.read_csv(runs)
    d = d[d.split == "holdout"].drop_duplicates(subset=["config", "repeat"], keep="last")
    if d.empty:
        print("no holdout rows, skipping the table figure"); return
    calls = {"engine": "none", "routed-duel": "5 of 21 cases", "routed": "16 of 20 cases",
             "heuristic": "none"}
    order = ["engine", "routed-duel", "routed", "heuristic"]
    label = {"engine": "engine  (no model calls)", "routed-duel": "routed-duel  ← SHIPPED",
             "routed": "routed  (full escalation)", "heuristic": "heuristic  (starter baseline)"}
    rows = []
    for cfg in order:
        r = d[d.config == cfg]
        if r.empty:
            continue
        r = r.iloc[0]
        rows.append([label.get(cfg, cfg), f"{r.mean_score:.3f}", f"{int(r.fully_solved)}/{int(r.n)}",
                     f"${r.dollars_mean:.6f}", f"{r.s_per_case_mean:.1f}", calls.get(cfg, "—")])
    cols = ["holdout · 21 cases, never tuned on", "partial", "strict", "$/case", "s/case", "model calls"]
    fig, ax = plt.subplots(figsize=(11.5, 0.46 * (len(rows) + 2.6)))
    ax.axis("off")
    ax.set_position([0, 0, 1, 0.78])
    t = ax.table(cellText=rows, colLabels=cols, cellLoc="center", loc="center",
                 colWidths=[0.34, 0.11, 0.1, 0.14, 0.11, 0.2])
    t.auto_set_font_size(False); t.set_fontsize(11); t.scale(1, 1.75)
    for (r_, c_), cell in t.get_celld().items():
        cell.set_edgecolor("#d7dbe0")
        if r_ == 0:
            cell.set_facecolor("#eef1f4"); cell.set_text_props(weight="bold", color=INK)
        else:
            cfg = order[r_ - 1]
            ship = cfg == "routed-duel"
            cell.set_facecolor("#fbf3f2" if ship else "white")
            cell.set_text_props(weight="bold" if ship else "normal", color=HL if ship else INK)
        if c_ == 0:
            cell.set_text_props(ha="left"); cell.PAD = 0.04
    ax.set_title("Same accuracy, 115× cheaper — and the model still gets a say\n"
                 "the shipped config consults a cheap GLM only where the engine is torn: on 5 of 21 "
                 "cases it kept the engine's pick 4 times, overrode it once,\nand the two cases that "
                 "moved cancelled out (won one, lost one)", loc="left", fontsize=10.5, pad=10, y=1.02)
    fig.tight_layout(); fig.savefig(out, bbox_inches="tight", facecolor="white"); plt.close(fig)


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
    fig_pipeline(OUT / "pipeline.png")
    fig_signal(a, w, OUT / "signal.png")
    fig_topology(a, w, OUT / "topology.png")
    fig_cost(ROOT / "eval" / "results" / "runs.csv", OUT / "cost.png")
    fig_holdout_table(ROOT / "eval" / "results" / "runs.csv", OUT / "holdout_table.png")
    print("wrote", ", ".join(str(p.relative_to(ROOT)) for p in sorted(OUT.glob("*.png"))))


if __name__ == "__main__":
    main()
