#!/usr/bin/env python3
"""Tolerance-curve figure of one modality (MS_SPEC.md 1.2 deliverables), from ms/results/phase1/tolerance.json.

One cell per impairment parameter; in each cell the change of event-F1 (top) and of false alarms per 24 h (bottom)
against the clean run, both out-of-fold on the sweep subset at the frozen operating point. The x axis always runs
from mild (left) to severe (right). The grey band is the tolerance band of D-MS10 (+-delta); a filled marker is a
tolerated level, an open marker a level outside the band; the vertical hairline marks the tolerance limit. Error
bars: standard deviation over impairment seeds (random impairments only).

Usage: python ms/py/plot_tolerance.py <eeg|ecg|emg|mov>  -> ms/results/phase1/figures/tolerance_<grid>.png
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt   # noqa: E402
from matplotlib.ticker import NullLocator   # noqa: E402

REPO = Path(__file__).resolve().parents[2]
P1 = REPO / "ms/results/phase1"
ORDER = ["lsb", "clip", "white", "pink", "gain+", "gain-", "offset", "drift", "mains50", "mains250", "hp", "lp"]
LOGX = {"lsb", "clip", "white", "pink", "drift", "mains50", "mains250", "hp", "lp"}
UNIT = {"uV": "uV", "uVrms": "uV rms", "Hz": "Hz", "C": "fraction of C", "LSB": "LSB (2^-12 g)",
        "LSBrms": "LSB rms", "": "|relative error|"}
# reference palette (dataviz skill, light mode): series 1 blue, series 2 orange; ink and chrome
F1_C, FA_C = "#2a78d6", "#eb6834"
SURF, INK, INK2, MUTED, GRID, AXIS, BAND = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7", "#f0efec"


def style(ax):
    ax.set_facecolor(SURF)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(AXIS); ax.spines[s].set_linewidth(0.8)
    ax.tick_params(colors=MUTED, labelcolor=INK2, labelsize=7, width=0.8)
    ax.grid(True, color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)


def draw(ax, fam, levels, key, sd_key, delta, sign, color, limit):
    x = [v["level"] for v in levels]
    y = [v[key] for v in levels]
    ax.axhspan(-delta if sign < 0 else -1e9, delta if sign > 0 else 1e9, color=BAND, zorder=0)
    ax.axhline(0, color=AXIS, linewidth=0.8, zorder=1)
    if sign < 0:
        ax.axhline(-delta, color=MUTED, linewidth=0.6, zorder=1)
    else:
        ax.axhline(delta, color=MUTED, linewidth=0.6, zorder=1)
    ax.plot(x, y, color=color, linewidth=1.6, solid_capstyle="round", zorder=2)
    for v in levels:
        sd = v.get(sd_key)
        if sd:
            ax.errorbar(v["level"], v[key], yerr=sd, color=color, linewidth=0.8, capsize=0, zorder=2)
        ok = v["tolerated"]
        ax.plot(v["level"], v[key], "o", ms=5, mfc=color if ok else SURF, mec=color, mew=1.4, zorder=3)
    if limit is not None:
        ax.axvline(limit, color=INK2, linewidth=0.7, zorder=1)
    if fam in LOGX:
        ax.set_xscale("log")
    ax.set_xticks(x)                        # ticks at the tested levels only, plain numbers
    ax.xaxis.set_minor_locator(NullLocator())
    ax.set_xticklabels([f"{v:g}" for v in x], fontsize=6.5)
    if fam in ("clip", "lp") and not ax.xaxis_inverted():
        ax.invert_xaxis()                   # severe to the right (once: the two panels share x)
    lo = min(min(y), -2 * delta); hi = max(max(y), 2 * delta)
    pad = 0.08 * (hi - lo)
    ax.set_ylim(lo - pad, hi + pad)


def main() -> int:
    if len(sys.argv) not in (2, 4):
        raise SystemExit(__doc__)
    grid = sys.argv[1]
    src = Path(sys.argv[2]) if len(sys.argv) == 4 else P1 / "tolerance.json"   # (testing: <grid> <json> <png>)
    tol = json.loads(src.read_text())
    g = tol["grids"][grid]
    d_f1, d_fa = tol["deltas"]["delta_f1"], tol["deltas"]["delta_fp24"]
    fams = [f for f in ORDER if f"{grid}/{f}" in g["families"]]
    ncol = 4 if len(fams) > 4 else len(fams)
    nrow = -(-len(fams) // ncol)
    fig = plt.figure(figsize=(3.0 * ncol, 3.0 * nrow + 0.7), facecolor=SURF)
    outer = fig.add_gridspec(nrow, ncol, hspace=0.42, wspace=0.32, top=1 - 0.95 / (3.0 * nrow + 0.7),
                             bottom=0.35 / (3.0 * nrow + 0.7), left=0.06, right=0.99)
    for i, fam in enumerate(fams):
        f = g["families"][f"{grid}/{fam}"]
        inner = outer[i // ncol, i % ncol].subgridspec(2, 1, hspace=0.12)
        a1 = fig.add_subplot(inner[0]); a2 = fig.add_subplot(inner[1], sharex=a1)
        for a in (a1, a2):
            style(a)
        draw(a1, fam, f["levels"], "d_f1", "f1_sd", d_f1, -1, F1_C, f["limit"])
        draw(a2, fam, f["levels"], "d_fp24", "fp24_sd", d_fa, +1, FA_C, f["limit"])
        plt.setp(a1.get_xticklabels(), visible=False)
        unit = UNIT.get(f["levels"][0]["unit"], f["levels"][0]["unit"])
        a2.set_xlabel(unit, fontsize=7, color=INK2)
        a1.set_ylabel("dF1", fontsize=7, color=INK2); a2.set_ylabel("dFP/24h", fontsize=7, color=INK2)
        lim = "none tolerated" if f["status"] == "none tolerated" else (
            f"limit {f['limit']:g}" + (" (beyond grid)" if f["status"] == "beyond grid" else ""))
        a1.set_title(f"{f['label']}\n{lim}", fontsize=8, color=INK, loc="left")
    c = g["clean"]
    fig.suptitle(f"{grid.upper()}: change vs clean (F1 {c['f1']:.3f}, FP/24h {c['fp_per_24h']:.2f}), subset, "
                 f"out-of-fold.  Band: +-delta (F1 {d_f1:.3f}, FP/24h {d_fa:.2f}).  Filled = tolerated.",
                 fontsize=9, color=INK, x=0.01, y=1 - 0.2 / (3.0 * nrow + 0.7), ha="left", va="top")
    out = Path(sys.argv[3]) if len(sys.argv) == 4 else P1 / f"figures/tolerance_{grid}.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=200, facecolor=SURF)
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
