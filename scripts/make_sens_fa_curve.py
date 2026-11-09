#!/usr/bin/env python3
"""Seizures detected against false alarms per hour on the 29 test patients (figure for the report and paper).

The frozen M6 models (checkpoints/<final run>/seed_<s>.pkl) re-score the test recordings; the decision threshold is
swept while the artefact gate and k of each model's inner-CV operating point stay fixed. Metrics are the dataset paper's,
computed exactly as in scripts/run_final.py (any-overlap sensitivity on the per-second grid, mean over recordings with a
seizure; false-alarm events per hour, mean over recordings). Each model's curve is averaged over its 5 seeds on a common
false-alarm grid. ChronoNet's curve is the clean reproduction's own threshold sweep (M2); the published SVM and ChronoNet
points are quoted from the paper. Nothing is trained or tuned; the test access is logged in each final run's folder.

The sweep uses every distinct score in the top 20 % when there are at most 400 (the LUT network's integer scores),
otherwise 150 quantiles spaced log-uniformly towards the top score, plus the thresholds of the operating points.
The DWN's two operating points (mean over seeds, as in the final table) are marked on its curve.

Usage:  python scripts/make_sens_fa_curve.py --final-test        (re-score and plot; ~1 h on 4 CPUs)
        python scripts/make_sens_fa_curve.py --plot-only         (re-plot from results/tables/sens_fa_test.json)
Output: results/figures/sens_fa_test.{pdf,png} (copied to paper/figures/), results/tables/sens_fa_test.json
"""
from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import pickle
import re
import shutil
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from seizelut.data.featureset import FeatureStore  # noqa: E402
from seizelut.data.split import official_test_subjects  # noqa: E402
from seizelut.eval import seizeit2 as s2  # noqa: E402
from seizelut.eval.operating import gate_mask, kth_of_last  # noqa: E402
from seizelut.eval.runlog import log_test_access, require_test_access  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
CHRONONET = REPO / "results/runs/20261107-204035_chrononet_clean_s1/metrics.json"
MODELS = {"n4_distill": "Our LUT network (final, ~900 LUTs)", "lgbm": "LightGBM (~31k LUTs)",
          "treelut_w5": "TreeLUT (~6.3k LUTs)"}
BLUE, ORANGE, AQUA, INK, INK2, MUTED, GRID = "#2a78d6", "#eb6834", "#1baf7a", "#0b0b0b", "#52514e", "#898781", "#e1e0d9"
COLOR = {"n4_distill": BLUE, "lgbm": AQUA, "treelut_w5": INK2}
FA_GRID = np.logspace(-2.5, 2.3, 200)


def final_run(name):
    hits = [d for d in sorted((REPO / "results/runs").glob(f"*_{name}_final_s0"))
            if re.match(rf"^\d{{8}}-\d{{6}}_{re.escape(name)}_final_s0$", d.name)]
    return hits[-1]


def paper_curve(runs, scores, gate, k, thresholds):
    """(fa_per_hour, sensitivity) for each threshold, dataset-paper definitions."""
    out = []
    gated = [np.where(gate_mask(r.artefact, gate), -np.inf, sc.astype(float)) for r, sc in zip(runs, scores)]
    kth = [kth_of_last(g, k) for g in gated]
    for th in thresholds:
        sens, fa = [], []
        for r, q in zip(runs, kth):
            alarm = q >= th
            tp, fp, fn = s2.perf_measure_ovlp(r.y.astype(int), alarm.astype(int), fs=1, fixed=True)
            fa.append(fp * 3600 / len(alarm))
            if r.y.any():
                sens.append(tp / (tp + fn))
        out.append((float(np.mean(fa)), float(np.mean(sens))))
    return out


def on_grid(curve):
    """Best sensitivity reachable at or below each false-alarm rate of FA_GRID (a step curve)."""
    fa = np.array([c[0] for c in curve]); se = np.array([c[1] for c in curve])
    return np.array([se[fa <= g].max() if (fa <= g).any() else 0.0 for g in FA_GRID])


def thresholds(alls, extra):
    top = alls[alls >= np.quantile(alls, 0.8)]
    uniq = np.unique(top)
    if len(uniq) <= 400:
        return np.unique(np.concatenate([uniq, extra]))
    q = np.quantile(alls, 1 - np.logspace(-5, np.log10(0.2), 150))
    return np.unique(np.concatenate([q, extra]))


_RUNS = []


def _curve_job(job):
    """One (model, seed): score the test runs with the frozen checkpoint and sweep the threshold."""
    ck, gate, k, extra = job
    obj = pickle.load(open(ck, "rb"))
    model, cols = obj["model"], obj["cols"]
    scores = [model.score(r.X[:, cols]).astype(np.float32) for r in _RUNS]
    ths = thresholds(np.concatenate(scores), np.asarray(extra, dtype=np.float32))
    out = paper_curve(_RUNS, scores, gate, k, ths)
    print(f"{ck.parent.name} {ck.stem}: {len(ths)} thresholds", flush=True)
    return out


def op_points(run):
    """Mean over seeds of the paper metrics at each final operating point (as in the final table)."""
    seeds = json.loads((run / "final_metrics.json").read_text())["seeds"].values()
    out = {}
    for op in ("best_f1", "sens_at_1fah"):
        pm = [s[op]["paper_metrics"] for s in seeds if op in s]
        out[op] = (float(np.mean([p["fa_per_hour_mean_over_recordings"] for p in pm])),
                   float(np.mean([p["sens_ovlp_mean_over_recordings"] for p in pm])))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--final-test", action="store_true")
    ap.add_argument("--plot-only", action="store_true", help="re-plot from results/tables/sens_fa_test.json")
    ap.add_argument("--workers", type=int, default=3)
    args = ap.parse_args()
    out_json = REPO / "results/tables/sens_fa_test.json"
    if args.plot_only:
        data = json.loads(out_json.read_text())
    else:
        data = score_all(args)
        out_json.write_text(json.dumps(data, default=float))
    plot(data)
    return 0


def score_all(args):
    test = official_test_subjects()
    require_test_access(test, args.final_test)
    store = FeatureStore("int")
    _RUNS.extend(store.iter_runs(test))
    jobs, meta = [], {}
    for name in MODELS:
        run = final_run(name)
        log_test_access(run, "sensitivity vs false-alarm curve of the frozen final models (make_sens_fa_curve.py)")
        seeds = json.loads((run / "final_metrics.json").read_text())["seeds"]
        cv = seeds["0"]["best_f1"]["operating_point"]
        extra = sorted({s[op]["operating_point"]["threshold"] for s in seeds.values()
                        for op in ("best_f1", "sens_at_1fah") if op in s})
        cks = sorted((REPO / "checkpoints" / run.name).glob("seed_*.pkl"))
        meta[name] = (run, len(jobs), len(cks))
        jobs += [(ck, cv["gate"], cv["k"], extra) for ck in cks]
    with mp.get_context("fork").Pool(args.workers) as pool:
        curves = pool.map(_curve_job, jobs, chunksize=1)
    data = {}
    for name, (run, i0, n) in meta.items():
        cs = curves[i0:i0 + n]
        g = np.stack([on_grid(c) for c in cs])
        data[name] = {"run": run.name, "fa_grid": FA_GRID.tolist(), "sens_mean": g.mean(0).tolist(),
                      "sens_std": g.std(0, ddof=1).tolist(), "per_seed_points": cs,
                      "fa_max": float(min(max(p[0] for p in c) for c in cs)), "operating_points": op_points(run)}
    ch = json.loads(CHRONONET.read_text())["seizeit2_as_published"]["curves"]
    data["chrononet_clean"] = {"fa": ch["fa_ovlp"], "sens": ch["sens_ovlp"]}
    return data


def plot(data):
    plt.rcParams.update({"font.size": 8, "font.family": "serif", "axes.edgecolor": MUTED, "axes.labelcolor": INK2,
                         "xtick.color": MUTED, "ytick.color": MUTED})
    fig, ax = plt.subplots(figsize=(5.4, 4.4))
    ax.grid(True, color=GRID, linewidth=0.5, which="major")
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    grid = np.array(FA_GRID)
    for name, label in MODELS.items():
        d = data[name]
        keep = grid <= d.get("fa_max", grid[-1])          # draw only where every seed's sweep reaches
        m, sd = np.array(d["sens_mean"])[keep] * 100, np.array(d["sens_std"])[keep] * 100
        lw = 2.0 if name == "n4_distill" else 1.2
        ax.step(grid[keep], m, where="post", color=COLOR[name], linewidth=lw, label=label,
                zorder=3 if name == "n4_distill" else 2)
        if name == "n4_distill":
            ax.fill_between(grid[keep], m - sd, m + sd, step="post", color=BLUE, alpha=0.15, linewidth=0)
    ops = data["n4_distill"].get("operating_points", {})
    if ops:
        xs = [ops[o][0] for o in ("best_f1", "sens_at_1fah")]; ys = [ops[o][1] * 100 for o in ("best_f1", "sens_at_1fah")]
        ax.scatter(xs, ys, s=30, color=BLUE, edgecolors="white", linewidths=1.0, zorder=5,
                   label="Our network, operating points (test)")
        for x, y in zip(xs, ys):
            ax.annotate(f"{y:.1f} % @ {x:.2f}/h", (x, y), xytext=(6, -13), textcoords="offset points",
                        fontsize=6, color=INK2)
    casc = REPO / "results/tables/paper_points_test.json"      # D40: pre-registered two-stage detector, if run
    if casc.exists():
        summ = json.loads(casc.read_text())["summary"]
        pts = [(summ[k]["paper"]["fa_per_hour"]["mean"], summ[k]["paper"]["sens"]["mean"] * 100)
               for k in sorted(summ) if k.startswith("cascade@")]
        ax.scatter([p[0] for p in pts], [p[1] for p in pts], marker="*", s=90, color=BLUE, edgecolors=INK,
                   linewidths=0.6, zorder=6, label="Our network + post-ictal check (test, pre-registered)")
        x, y = max(pts)
        ax.annotate(f"{y:.1f} % @ {x:.1f}/h", (x, y), xytext=(-58, 9), textcoords="offset points", fontsize=6,
                    color=INK2)
    fa = np.array(data["chrononet_clean"]["fa"]); se = np.array(data["chrononet_clean"]["sens"]) * 100
    order = np.argsort(fa)
    ax.plot(fa[order], se[order], color=ORANGE, linewidth=1.4, marker="o", markersize=2.5,
            label="ChronoNet, our clean reproduction")
    ax.scatter([11.0], [71.1], marker="s", s=36, color="white", edgecolors=INK, linewidths=1.2, zorder=4,
               label="SVM, published")
    ax.scatter([100.5], [84.2], marker="D", s=36, color="white", edgecolors=ORANGE, linewidths=1.2, zorder=4,
               label="ChronoNet, published")
    ax.axvline(1.0, color=MUTED, linewidth=0.8, linestyle=(0, (4, 2)), zorder=1)
    ax.text(0.92, 88, "1 false alarm\nper hour", color=MUTED, fontsize=6.5, ha="right")
    ax.set_xscale("log")
    ax.set_xlim(FA_GRID[0], FA_GRID[-1])
    ax.set_ylim(0, 100)
    ax.set_xlabel("False alarms per hour (log scale)")
    ax.set_ylabel("Seizures detected (%)")
    ax.legend(frameon=False, fontsize=6.3, loc="upper center", bbox_to_anchor=(0.5, -0.16), ncol=2, labelcolor=INK2)
    fig.tight_layout()
    out = REPO / "results/figures"
    for ext in ("pdf", "png"):
        fig.savefig(out / f"sens_fa_test.{ext}", dpi=300)
    shutil.copy(out / "sens_fa_test.pdf", REPO / "paper/figures/sens_fa_test.pdf")
    print(out / "sens_fa_test.png")


if __name__ == "__main__":
    sys.exit(main())
