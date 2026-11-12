#!/usr/bin/env python3
"""Self-test coverage against the number of test vectors (after scripts/fault_analysis.py, make_kv260_rtl.py and
make_fault_list.py). For three vector orders the share of decision-relevant faults (faults that change at least one
decision of the 96 training patients at the frozen threshold) that the first m vectors detect:
  coverage-selected  the new BIST ROM (selected training windows first, then the seizure stretch)
  seizure stretch    the kit-v4 ROM (1,024 consecutive windows of one exported recording)
  random training    1,024 windows drawn at random from 64 random training recordings
A fault is detected by a vector when the faulty score differs from the golden score (the BIST compares score,
decision and alarm). Output: paper/figures/fault_coverage.{pdf,png}, results/tables/fault_coverage_curves.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "hw/kv260/board"))
BLUE, ORANGE, AQUA, INK, INK2, MUTED, GRID = "#2a78d6", "#eb6834", "#1baf7a", "#0b0b0b", "#52514e", "#898781", "#e1e0d9"


def first_detection(model, F, faults):
    """Index of the first vector of F (in order) that detects each fault (len(F) = never)."""
    bits0, out0, s0 = model.forward(F)
    mp = model.layers[-1][0]
    addr = np.zeros((len(F), mp.shape[0]), np.int64)
    for lb in range(mp.shape[1]):
        addr |= bits0[:, mp[:, lb]].astype(np.int64) << lb
    first = np.full(len(faults), len(F), np.int64)
    for n, f in enumerate(faults):
        if f["kind"] == "tt":
            hit = np.nonzero(addr[:, f["idx"]] == f["addr"])[0]
        else:
            key = {"sab0": "b0", "sab1": "b1", "sal0": "l0", "sal1": "l1"}[f["kind"]]
            hit = np.nonzero(model.forward(F, {key: [f["idx"]]})[2] != s0)[0]
        if len(hit):
            first[n] = hit[0]
    return first


def main() -> int:
    from seizelut_model import SeizeLUTModel
    from seizelut.data.featureset import FeatureStore
    from seizelut.data.split import official_train_subjects
    model = SeizeLUTModel(REPO / "hw/kv260/board/model")
    faults = json.loads((REPO / "hw/kv260/board/fault_list.json").read_text())["faults"]
    rel = np.array([f["decision_9"] for f in faults])
    new = np.load(REPO / "hw/kv260/board/seizelut_bist_vectors.npz")
    regs = json.loads((REPO / "hw/kv260/rtl/seizelut_regs.json").read_text())["bist"]
    v = np.load(REPO / "hw/kv260/board/vectors/sub-098_run-03.npz")
    old = v["feats"][69571:69571 + 1024].astype(np.int64)      # the kit-v4 ROM
    store = FeatureStore("int")
    rng = np.random.default_rng(0)
    keys = store.runs_of(official_train_subjects())
    spec = [f["spec_index"] for f in json.loads((REPO / "hw/kv260/board/model/thresholds.json").read_text())["features"]]
    pick = rng.choice(len(keys), 64, replace=False)
    rows = []
    for i in pick:
        r = store.load_run(keys[i])
        rows.append(r.X[rng.choice(len(r.X), 16, replace=False)][:, spec])
    rnd = np.concatenate(rows).astype(np.int64)
    orders = {"coverage-selected (ours)": new["feats"].astype(np.int64), "consecutive windows of one recording": old,
              "random training windows": rnd}
    ms = np.unique(np.round(np.logspace(0, np.log10(1024), 60)).astype(int))
    curves = {}
    for name, F in orders.items():
        fd = first_detection(model, F, faults)
        curves[name] = [[int(m), round(100.0 * ((fd < m) & rel).sum() / rel.sum(), 2)] for m in ms]
    curves = {k: v for k, v in curves.items()}
    out = {"metric": "share of decision-relevant faults (frozen threshold, training patients) detected by the first "
                     "m self-test vectors", "decision_relevant_faults": int(rel.sum()),
           "selected_vectors": int(regs.get("selected", 0)), "curves": curves}
    (REPO / "results/tables/fault_coverage_curves.json").write_text(json.dumps(out, indent=1))

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"font.size": 8, "font.family": "serif", "axes.edgecolor": MUTED, "axes.labelcolor": INK2,
                         "xtick.color": MUTED, "ytick.color": MUTED})
    fig, ax = plt.subplots(figsize=(3.45, 2.55))
    ax.grid(True, color=GRID, linewidth=0.5)
    col = {"coverage-selected (ours)": BLUE, "consecutive windows of one recording": ORANGE,
           "random training windows": INK2}
    for name, c in curves.items():
        a = np.array(c)
        ax.plot(a[:, 0], a[:, 1], color=col[name], linewidth=1.6 if "ours" in name else 1.2, label=name)
    k = out["selected_vectors"]
    if k:
        ax.axvline(k, color=MUTED, linewidth=0.7, linestyle=(0, (3, 2)))
        ax.text(k * 0.9, 103, f"{k} selected vectors: 100 %", fontsize=6, color=INK2, ha="right", va="bottom")
    ax.set_xscale("log", base=2)
    ax.set_xlim(1, 1024)
    ax.set_ylim(0, 112)
    ax.set_yticks([0, 20, 40, 60, 80, 100])
    ax.set_xticks([1, 4, 16, 64, 256, 1024])
    ax.set_xticklabels(["1", "4", "16", "64", "256", "1024"])
    ax.set_xlabel("self-test vectors")
    ax.set_ylabel("decision-relevant faults\ndetected (%)")
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.legend(frameon=False, fontsize=6.2, loc="upper center", bbox_to_anchor=(0.42, -0.27), ncol=1, labelcolor=INK2,
              handlelength=1.6, borderaxespad=0.0)
    fig.tight_layout()
    for ext in ("pdf", "png"):
        fig.savefig(REPO / "paper/figures" / f"fault_coverage.{ext}", dpi=300, bbox_inches="tight", pad_inches=0.02)
    print(json.dumps({n: [c[i] for i in (0, len(c) // 2, -1)] for n, c in curves.items()}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
