#!/usr/bin/env python3
"""Figures for the Phase I report, every value read from committed result files (no test-patient access: the test
numbers come from results/tables/final_test.json, written by scripts/make_final_table.py).

Usage:  python scripts/make_report_figures.py
Output: reports/phase1_nitw/figures/<name>.png (300 dpi) and .pdf
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "reports/phase1_nitw/figures"
BLUE, ORANGE, AQUA, INK, INK2, MUTED, GRID = "#2a78d6", "#eb6834", "#1baf7a", "#0b0b0b", "#52514e", "#898781", "#e1e0d9"
LIGHT = "#a9c8ef"
RUNS = REPO / "results/runs"


def style(ax, grid_axis="x"):
    ax.grid(True, axis=grid_axis, color=GRID, linewidth=0.5)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)


def save(fig, name):
    fig.tight_layout()
    for ext in ("png", "pdf"):
        fig.savefig(OUT / f"{name}.{ext}", dpi=300)
    plt.close(fig)
    print(OUT / f"{name}.png")


def run_dir(pattern):
    return sorted(RUNS.glob(pattern))[-1]


def seizure_classes():
    cls = [("Focal impaired awareness", 289, 102), ("Focal aware", 274, 42), ("Focal, awareness unknown", 105, 10),
           ("Focal to bilateral tonic-clonic", 33, 22), ("Unknown onset", 1, 5)]
    fig, ax = plt.subplots(figsize=(5.6, 2.4))
    style(ax)
    y = np.arange(len(cls))
    ax.barh(y - 0.2, [c[1] for c in cls], 0.4, color=BLUE, label="training patients (96)")
    ax.barh(y + 0.2, [c[2] for c in cls], 0.4, color=ORANGE, label="test patients (29)")
    for i, c in enumerate(cls):
        ax.text(c[1] + 4, i - 0.2, str(c[1]), va="center", fontsize=7, color=INK2)
        ax.text(c[2] + 4, i + 0.2, str(c[2]), va="center", fontsize=7, color=INK2)
    ax.set_yticks(y, [c[0] for c in cls], fontsize=7.5)
    ax.invert_yaxis()
    ax.set_xlabel("Seizures")
    ax.legend(frameon=False, fontsize=7, loc="lower right")
    save(fig, "seizure_classes")


def chrononet_repro():
    rows = [("Published", 84.2, 100.5), ("Ours, official protocol", 74.5, 22.6), ("Ours, clean protocol", 67.1, 11.9)]
    colors = [MUTED, ORANGE, BLUE]
    fig, (a, b) = plt.subplots(1, 2, figsize=(6.2, 2.2))
    for ax, idx, lab in ((a, 1, "Seizures detected (%)"), (b, 2, "False alarms per hour")):
        style(ax)
        vals = [r[idx] for r in rows]
        ax.barh(range(3), vals, color=colors, height=0.6)
        for i, v in enumerate(vals):
            ax.text(v * (1.02 if idx == 1 else 1.04), i, f"{v:g}", va="center", fontsize=7, color=INK2)
        ax.set_yticks(range(3), [r[0] for r in rows] if idx == 1 else [""] * 3, fontsize=7.5)
        ax.invert_yaxis()
        ax.set_xlabel(lab)
        ax.set_xlim(0, max(vals) * 1.25)
    save(fig, "chrononet_repro")


def cost():
    fm = json.loads((run_dir("*_n4_distill_final_s0") / "final_metrics.json").read_text())
    c = fm["seeds"]["0"]["cost"]
    parts = [("Thermometer encoder", c["encoder_luts"], ORANGE), ("LUT network", c["network_luts"], BLUE),
             ("Popcount", c["popcount_luts"], AQUA), ("Decision logic", c["postproc_luts"], MUTED)]
    final = json.loads((REPO / "results/tables/final_test.json").read_text())
    tot = {r["name"]: r["luts"] for r in final if r.get("luts")}
    models = [("Our DWN (final)", tot["n4_distill"]), ("TreeLUT", tot["treelut_w5"]), ("Logic-gate network", tot["lgn_mi40"]),
              ("CatBoost", tot["catboost"]), ("LightGBM", tot["lgbm"]), ("XGBoost", tot["xgb"]), ("Random forest", tot["rf"])]
    fig, (a, b) = plt.subplots(1, 2, figsize=(6.6, 2.6), gridspec_kw={"width_ratios": [1, 1.2]})
    style(a)
    left = 0
    for name, v, col in parts:
        a.barh(0, v, left=left, color=col, height=0.5, edgecolor="white", linewidth=1.5)
        left += v
    a.set_yticks([])
    a.set_xlim(0, left * 1.05)
    a.set_xlabel("Estimated LUTs, final DWN")
    handles = [plt.Rectangle((0, 0), 1, 1, color=col) for _, _, col in parts]
    a.legend(handles, [f"{n}: {v}" for n, v, _ in parts], frameon=False, fontsize=6.5, loc="upper center",
             bbox_to_anchor=(0.5, -0.32), ncol=2)
    a.set_title(f"Total {sum(p[1] for p in parts)} LUTs, 0 multipliers", fontsize=8, color=INK2)
    style(b)
    y = np.arange(len(models))
    b.barh(y, [m[1] for m in models], color=[BLUE] + [MUTED] * (len(models) - 1), height=0.6)
    for i, m in enumerate(models):
        b.text(m[1] * 1.15, i, f"{m[1]:,.0f}", va="center", fontsize=6.5, color=INK2)
    b.set_xscale("log")
    b.set_xlim(300, 3e6)
    b.set_yticks(y, [m[0] for m in models], fontsize=7)
    b.invert_yaxis()
    b.set_xlabel("Estimated LUTs (log scale)")
    save(fig, "cost")


def ablation():
    rows = []
    for ln in (REPO / "results/tables/m5_ablation.md").read_text().splitlines():
        m = re.match(r"\| (\S+) \| \S+ \| [^|]+\| ([+-][\d.]+) \[([+-][\d.]+), ([+-][\d.]+)\] \| ([\d.e-]+) \|", ln)
        if m and not m.group(1).startswith("n46"):
            rows.append((m.group(1), float(m.group(2)), float(m.group(3)), float(m.group(4)), float(m.group(5))))
    label = {"n1_stack5_sel": "N1 stacked windows", "n1_stateful_sel": "N1 stateful (16 state bits)",
             "n2_gaussian": "N2 Gaussian thresholds", "n2_learned": "N2 learned thresholds",
             "n2_learned_p1e3": "N2 learned, strong penalty", "n2_uniform": "N2 uniform thresholds",
             "n4_distill": "N4 distillation (adopted)", "n4_distill_hardneg": "N4 distillation + hard negatives",
             "n4_hardneg_teacher": "N4 hard negatives", "n5_focal": "N5 focal loss", "n5_gce": "N5 GCE loss",
             "n5_mil": "N5 multiple-instance loss", "n5_onset": "N5 onset weighting", "n5_sce": "N5 SCE loss",
             "n6_dropout": "N6 modality dropout (adopted*)", "n6_eeg_only": "N6 EEG only", "n6_gated": "N6 gated fusion",
             "n6_late": "N6 late fusion"}
    rows = [r for r in rows if r[0] in label]
    rows.sort(key=lambda r: r[1])
    fig, ax = plt.subplots(figsize=(5.6, 4.4))
    style(ax)
    for i, (n, d, lo, hi, p) in enumerate(rows):
        col = BLUE if n in ("n4_distill", "n6_dropout") else (ORANGE if (p < 0.05 and d < 0) else MUTED)
        ax.plot([lo, hi], [i, i], color=col, linewidth=1.4)
        ax.plot(d, i, "o", color=col, markersize=4.5)
    ax.axvline(0, color=INK2, linewidth=0.8)
    ax.set_yticks(range(len(rows)), [label[r[0]] for r in rows], fontsize=7)
    ax.set_xlabel("Change in per-patient event-F1 vs base DWN (mean, 95 % CI)")
    handles = [plt.Line2D([], [], color=BLUE, marker="o", label="adopted"),
               plt.Line2D([], [], color=ORANGE, marker="o", label="significantly worse (p < 0.05)"),
               plt.Line2D([], [], color=MUTED, marker="o", label="no significant difference")]
    ax.legend(handles=handles, frameon=False, fontsize=6.5, loc="upper left")
    save(fig, "ablation")


def missing():
    names = {"Base DWN": "*_dwn_L50_b8_lgbm40_e15bg10_s0", "DWN + distillation (final)": "*_n4_distill_s0",
             "DWN + modality dropout": "*_n6_dropout_s0"}
    conds = [("intact", "All sensors"), ("no_ecg", "No ECG"), ("no_emg", "No EMG"), ("no_mov", "No motion"),
             ("eeg_only", "EEG only")]
    vals = {k: json.loads((run_dir(v) / "breakdown.json").read_text())["missing_modality"] for k, v in names.items()}
    fig, ax = plt.subplots(figsize=(6.0, 2.6))
    style(ax, "y")
    x = np.arange(len(conds))
    for j, (k, col) in enumerate(zip(names, [MUTED, BLUE, AQUA])):
        h = [vals[k][c]["f1"] for c, _ in conds]
        ax.bar(x + (j - 1) * 0.26, h, 0.26, color=col, label=k)
    ax.set_xticks(x, [c[1] for c in conds], fontsize=7.5)
    ax.set_ylabel("Event-F1 (training folds)")
    ax.legend(frameon=False, fontsize=6.5, loc="upper right")
    save(fig, "missing_sensors")


def seizure_types():
    b = json.loads((run_dir("*_dwn_L50_b8_lgbm40_e15bg10_s0") / "breakdown.json").read_text())["by_class"]
    order = [("FBTC", "Focal to bilateral\ntonic-clonic"), ("FIA", "Focal impaired\nawareness"), ("FA", "Focal aware"),
             ("focal_unknown_awareness", "Focal, awareness\nunknown")]
    fig, ax = plt.subplots(figsize=(5.2, 2.4))
    style(ax, "y")
    v = [100 * b[k]["sensitivity"] for k, _ in order]
    ax.bar(range(4), v, color=[BLUE, MUTED, MUTED, MUTED], width=0.6)
    for i, (k, _) in enumerate(order):
        ax.text(i, v[i] + 2, f"{b[k]['detected']}/{b[k]['seizures']}", ha="center", fontsize=7, color=INK2)
    ax.set_xticks(range(4), [o[1] for o in order], fontsize=7)
    ax.set_ylabel("Seizures detected (%)")
    ax.set_ylim(0, 100)
    save(fig, "seizure_types")


def test_results():
    rows = json.loads((REPO / "results/tables/final_test.json").read_text())
    label = {"n4_distill": "Our DWN (final)", "n6_dropout": "DWN + modality dropout", "dwn_L50_b8_lgbm40_e15bg10": "DWN base",
             "lgbm": "LightGBM", "xgb": "XGBoost", "catboost": "CatBoost", "rf": "Random forest", "lr": "Logistic regression",
             "treelut_w5": "TreeLUT", "mlp_int8": "INT8 MLP", "lgn_mi40": "Logic-gate network"}
    rows = [r for r in rows if r["name"] in label]
    ch = json.loads((RUNS / "20261107-204035_chrononet_clean_s1/metrics.json").read_text())["szcore"]["0.50"]["mean_over_subjects"]
    data = [(label[r["name"]], r["f1"]["mean"], r["f1"]["std"], r["fp"]["mean"], r["name"]) for r in rows]
    data.append(("ChronoNet (published baseline, clean)", ch["f1"], 0.0, ch["fp_per_24h"], "chrononet"))
    data.sort(key=lambda r: r[1])
    fig, ax = plt.subplots(figsize=(5.8, 3.6))
    style(ax)
    col = [BLUE if d[4].startswith(("n4", "n6", "dwn")) else (ORANGE if d[4] == "chrononet" else MUTED) for d in data]
    ax.barh(range(len(data)), [d[1] for d in data], xerr=[d[2] for d in data], color=col, height=0.6,
            error_kw={"elinewidth": 0.8, "ecolor": INK2, "capsize": 2})
    for i, d in enumerate(data):
        ax.text(d[1] + d[2] + 0.006, i, f"{d[1]:.3f}  ({d[3]:.1f} FA/day)", va="center", fontsize=6.5, color=INK2)
    ax.set_yticks(range(len(data)), [d[0] for d in data], fontsize=7)
    ax.set_xlim(0, 0.42)
    ax.set_xlabel("Event-F1 on the 29 test patients (mean ± std over 5 seeds)")
    save(fig, "test_f1")
    # accuracy against hardware cost on the test patients
    pts = [(r["luts"], r["f1"]["mean"], label[r["name"]], r["name"]) for r in rows if r.get("luts")]
    fig, ax = plt.subplots(figsize=(5.4, 3.2))
    style(ax, "both")
    for x, y, lab, n in pts:
        ours = n.startswith(("n4", "n6", "dwn"))
        ax.scatter(x, y, s=34 if n == "n4_distill" else 22, color=BLUE if ours else MUTED, zorder=3,
                   edgecolors="white", linewidths=0.6)
        short = "DWN + dropout" if n == "n6_dropout" else lab
        ax.annotate(short, (x, y), xytext=(5, 3 if n != "n6_dropout" else -11), textcoords="offset points", fontsize=6.5,
                    color=INK if ours else INK2)
    mlp = next(r for r in rows if r["name"] == "mlp_int8")["f1"]["mean"]
    ax.axhline(mlp, color=ORANGE, linewidth=0.8, linestyle=(0, (4, 2)))
    ax.text(2.2e5, mlp + 0.005, "INT8 MLP (9,600 multipliers)", color=ORANGE, fontsize=6.5, ha="right")
    ax.axhline(ch["f1"], color=ORANGE, linewidth=0.8, linestyle=(0, (1, 2)))
    ax.text(2.2e5, ch["f1"] + 0.005, "ChronoNet, clean (CNN + GRU)", color=ORANGE, fontsize=6.5, ha="right")
    ax.set_xscale("log")
    ax.set_xlim(500, 8e5)
    ax.set_ylim(0, 0.35)
    ax.set_xlabel("Estimated LUTs (log scale)")
    ax.set_ylabel("Event-F1, 29 test patients")
    save(fig, "test_f1_vs_luts")


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({"font.size": 8, "font.family": "serif", "axes.edgecolor": MUTED, "axes.labelcolor": INK2,
                         "xtick.color": INK2, "ytick.color": INK2})
    for f in (seizure_classes, chrononet_repro, cost, ablation, missing, seizure_types, test_results):
        f()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
