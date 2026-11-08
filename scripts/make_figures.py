#!/usr/bin/env python3
"""Figures from committed results (Section 9.3). Every figure is rebuilt from results/runs/*.

  pareto_inner_cv   event-F1 against estimated LUTs for every LUT-native run on the inner folds
                    (DWN sizes, other LUT-native families, Tier-2 methods), with the Pareto front and the
                    best tree model and the INT8 MLP as reference lines (their cost is not in LUTs)

Usage:  python scripts/make_figures.py
Output: results/figures/<name>.pdf and .png, copied to paper/figures/
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
from make_tables import load_runs  # noqa: E402

# reference palette (validated: first three categorical slots pass all-pairs CVD/normal-vision checks)
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
INK, INK2, MUTED, GRID = "#0b0b0b", "#52514e", "#898781", "#e1e0d9"
OTHER_LUT = {"lgn": ("LGN", "s"), "logicnet": ("LogicNets-style", "D"), "treelut": ("TreeLUT", "^")}


def short(cfg: str) -> str:
    """Readable point label: 'TreeLUT w5', 'N1 stateful', 'L200 b8'."""
    for k, (lab, _) in OTHER_LUT.items():
        if cfg.startswith(k):
            rest = cfg[len(k):].strip("_").replace("_mi40", "")
            return f"{lab} {rest}".strip()
    if cfg.startswith("n"):
        parts = [w for w in cfg.split("_")[1:] if w not in ("s16", "mi40")]
        return cfg.split("_")[0].upper() + " " + " ".join(parts)
    return cfg.replace("dwn_l", "L").replace("dwn_L", "L").replace("_learn", "").replace("_mi40", "").replace("_", " ")


def family(cfg: str):
    if cfg.startswith("dwn_"):
        return "dwn"
    if cfg.startswith(("n1_", "n2_", "n4_", "n5_", "n6_")):
        return "tier2"
    for k in OTHER_LUT:
        if cfg.startswith(k):
            return k
    return None


def pareto_inner_cv(out: Path) -> list[Path]:
    latest = {}
    for name, j in load_runs():
        latest[j["name"]] = j
    pts = []
    for cfg, j in latest.items():
        fam = family(cfg)
        luts = j.get("cost_median", {}).get("total_luts")
        if fam and luts:
            pts.append((cfg, fam, float(luts), j["operating_points"]["best_f1"]["f1"]))
    if not pts:
        return []
    plt.rcParams.update({"font.size": 7, "axes.edgecolor": MUTED, "axes.labelcolor": INK2, "xtick.color": MUTED,
                         "ytick.color": MUTED, "font.family": "serif"})
    fig, ax = plt.subplots(figsize=(3.45, 2.5))
    ax.grid(True, color=GRID, linewidth=0.5)
    ax.set_axisbelow(True)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    for cfg, fam, x, y in pts:
        if fam == "dwn":
            hollow = "_rando" in cfg
            ax.scatter(x, y, s=16, marker="o", facecolors="none" if hollow else BLUE, edgecolors=BLUE, linewidths=1.0,
                       zorder=3)
        elif fam == "tier2":
            ax.scatter(x, y, s=18, marker="P", color=AQUA, edgecolors="white", linewidths=0.6, zorder=3)
            ax.annotate(short(cfg), (x, y), xytext=(4, 3), textcoords="offset points", color=INK2, fontsize=5.5)
        else:
            ax.scatter(x, y, s=18, marker=OTHER_LUT[fam][1], color=ORANGE, edgecolors="white", linewidths=0.6, zorder=3)
            ax.annotate(short(cfg), (x, y), xytext=(4, 3), textcoords="offset points", color=INK2, fontsize=5.5)
    # Pareto front: no other point has fewer LUTs and a higher F1
    srt = sorted(pts, key=lambda p: (p[2], -p[3]))
    front, best = [], -1.0
    for p in srt:
        if p[3] > best:
            front.append(p)
            best = p[3]
    ax.step([p[2] for p in front], [p[3] for p in front], where="post", color=INK2, linewidth=0.8, zorder=2)
    best_dwn = max((p for p in pts if p[1] == "dwn"), key=lambda p: p[3], default=None)
    if best_dwn:
        ax.annotate("DWN " + short(best_dwn[0]), (best_dwn[2], best_dwn[3]), xytext=(-4, 4), textcoords="offset points",
                    color=INK2, fontsize=5.5, ha="right")
    ax.set_xscale("log")
    x_hi = max(p[2] for p in pts) * 1.6
    ax.set_xlim(min(p[2] for p in pts) / 1.25, x_hi)
    for ref, label in (("lgbm", "LightGBM (cost not in LUTs)"), ("mlp_int8", "INT8 MLP (multipliers)")):
        if ref in latest:
            f1 = latest[ref]["operating_points"]["best_f1"]["f1"]
            ax.axhline(f1, color=MUTED, linewidth=0.8, linestyle=(0, (4, 2)), zorder=1)
            ax.text(np.sqrt(ax.get_xlim()[0] * x_hi) * 1.15, f1 + 0.004, label, color=MUTED, fontsize=5.5, ha="center")
    from matplotlib.ticker import FixedLocator, FuncFormatter, NullFormatter
    ticks = [t for t in (500, 1000, 2000, 4000, 8000, 16000) if ax.get_xlim()[0] <= t <= x_hi]
    ax.xaxis.set_major_locator(FixedLocator(ticks))
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v / 1000:g}k"))
    ax.xaxis.set_minor_formatter(NullFormatter())
    ax.set_xlabel("Estimated LUTs (encoder + network + post-processing)")
    ax.set_ylabel("Event-F1 (inner folds)")
    handles = [
        plt.Line2D([], [], marker="o", color=BLUE, linestyle="", markersize=4, label="DWN, learnable mapping"),
        plt.Line2D([], [], marker="o", markerfacecolor="none", color=BLUE, linestyle="", markersize=4,
                   label="DWN, random mapping"),
        plt.Line2D([], [], marker="s", color=ORANGE, linestyle="", markersize=4, label="other LUT-native"),
        plt.Line2D([], [], marker="P", color=AQUA, linestyle="", markersize=4, label="Tier-2 methods"),
        plt.Line2D([], [], color=INK2, linewidth=0.8, label="Pareto front"),
    ]
    ax.legend(handles=handles, frameon=False, fontsize=5.5, loc="upper left", bbox_to_anchor=(0.0, 0.92),
              labelcolor=INK2, handletextpad=0.3, borderaxespad=0.2)
    fig.tight_layout()
    paths = []
    for ext in ("pdf", "png"):
        p = out / f"pareto_inner_cv.{ext}"
        fig.savefig(p, dpi=300)
        paths.append(p)
    plt.close(fig)
    return paths


def main() -> int:
    out = REPO / "results" / "figures"
    out.mkdir(parents=True, exist_ok=True)
    made = pareto_inner_cv(out)
    (REPO / "paper" / "figures").mkdir(parents=True, exist_ok=True)
    for p in made:
        if p.suffix == ".pdf":
            shutil.copy(p, REPO / "paper" / "figures" / p.name)
    print("\n".join(str(p) for p in made) or "no figures (no complete runs)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
