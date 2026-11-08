#!/usr/bin/env python3
"""Block diagram of the detector for the reports (reports/phase1/figures/system_overview.{png,pdf}).
Numbers are the base DWN's (decisions D33/D34): 40 features x 8 thresholds, 50 LUT6, estimated LUTs per stage."""
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch  # noqa: E402

BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
INK, INK2, MUTED, GRID = "#0b0b0b", "#52514e", "#898781", "#e1e0d9"
OUT = Path(__file__).resolve().parents[1] / "reports" / "phase1" / "figures"

STAGES = [
    ("Sensors", ["bte-EEG, 2 ch", "ECG, EMG", "ACC, GYR"], MUTED, "int16 samples"),
    ("Front end", ["shift-add filters", "1-s block sums", "2-s window / 1 s"], BLUE, "117 features"),
    ("Selection", ["40 of 117,", "fitted on the", "training folds"], BLUE, "40 features"),
    ("Encoder", ["8 comparators", "per feature", "\u2248850 LUTs"], ORANGE, "320 bits"),
    ("LUT network", ["50 LUT6,", "learned mapping,", "popcount (\u2248110)"], ORANGE, "score"),
    ("Decision", ["threshold,", "k of last 10 s,", "artefact gate"], ORANGE, None),
]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({"font.family": "serif", "font.size": 7})
    fig, ax = plt.subplots(figsize=(7.4, 2.15))
    ax.set_xlim(0, 104)
    ax.set_ylim(0, 30)
    ax.axis("off")
    w, h, gap, y0 = 13.2, 15.0, 3.4, 8.0
    x = 0.6
    centers = []
    for title, lines, color, out in STAGES:
        box = FancyBboxPatch((x, y0), w, h, boxstyle="round,pad=0.2,rounding_size=1.2", linewidth=1.0,
                             edgecolor=color, facecolor="white")
        ax.add_patch(box)
        ax.add_patch(FancyBboxPatch((x, y0 + h - 4.2), w, 4.2, boxstyle="round,pad=0.2,rounding_size=1.2",
                                    linewidth=0, facecolor=color, alpha=0.14))
        ax.text(x + w / 2, y0 + h - 2.1, title, ha="center", va="center", color=INK, fontsize=6.8, weight="bold")
        for i, ln in enumerate(lines):
            ax.text(x + w / 2, y0 + h - 6.6 - i * 2.6, ln, ha="center", va="center", color=INK2, fontsize=5.9)
        centers.append((x, out))
        x += w + gap
    for i in range(len(STAGES) - 1):
        xa = centers[i][0] + w + 0.25
        xb = centers[i + 1][0] - 0.25
        ax.add_patch(FancyArrowPatch((xa, y0 + h / 2), (xb, y0 + h / 2), arrowstyle="-|>", mutation_scale=7,
                                     color=INK2, linewidth=0.9))
        ax.text((xa + xb) / 2 + 0.1, y0 - 2.6, centers[i][1], ha="center", va="center", color=MUTED,
                fontsize=5.6, rotation=0)
    xe = centers[-1][0] + w
    ax.annotate("", xy=(xe + 3.2, y0 + h / 2), xytext=(xe + 0.3, y0 + h / 2), color=INK, fontsize=7,
                va="center", annotation_clip=False,
                arrowprops=dict(arrowstyle="-|>", color=INK2, lw=0.9))
    ax.text(xe + 3.6, y0 + h / 2, "alarm", ha="left", va="center", color=INK, fontsize=6.8, weight="bold")
    # brace over the hardware classifier
    xs, xe2 = centers[3][0], centers[5][0] + w
    ax.plot([xs, xs, xe2, xe2], [y0 + h + 1.6, y0 + h + 2.6, y0 + h + 2.6, y0 + h + 1.6], color=ORANGE, lw=0.8)
    ax.text((xs + xe2) / 2, y0 + h + 4.2, "LUT-native classifier: no multipliers, \u2248960 LUTs (estimated)",
            ha="center", va="center", color=INK2, fontsize=6.0)
    xs, xe2 = centers[1][0], centers[2][0] + w
    ax.plot([xs, xs, xe2, xe2], [y0 + h + 1.6, y0 + h + 2.6, y0 + h + 2.6, y0 + h + 1.6], color=BLUE, lw=0.8)
    ax.text((xs + xe2) / 2, y0 + h + 4.2, "bit-exact integer golden model", ha="center", va="center",
            color=INK2, fontsize=6.0)
    for ext in ("png", "pdf"):
        fig.savefig(OUT / f"system_overview.{ext}", dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(OUT / "system_overview.png")


if __name__ == "__main__":
    main()
