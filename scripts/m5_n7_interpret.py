#!/usr/bin/env python3
"""N7: interpretable alarms (Section 6.3).

From a finished DWN inner-CV run (first layer = LUTs reading thermometer bits):
  1. Static map: for every first-layer LUT, the (feature, threshold) pairs it reads.
  2. For every alarm at the run's best-F1 operating point, classify it as a true or false
     alarm (SzCORE rules) and count, per feature, how many seizure-group LUTs that read the
     feature were firing during the alarm. Compare true vs false alarms.
  3. Spearman correlation of the DWN feature ranking with mean |SHAP| of the LightGBM run's
     fold models (optional --shap-run).
  4. Case studies: the strongest true alarm and the strongest false alarm, with the features
     and thresholds behind them.

Usage: python scripts/m5_n7_interpret.py --run results/runs/<dwn run> [--shap-run results/runs/<lgbm run>]
Output: results/runs/<dwn run>/n7_interpretability.json and results/figures/n7_feature_usage.png
"""
from __future__ import annotations

import argparse
import json
import pickle
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

from seizelut.data.featureset import FeatureStore
from seizelut.data.split import load_folds
from seizelut.eval.fastscore import prepare_ref
from seizelut.eval.operating import gate_mask, kth_of_last, run_events_at

REPO = Path(__file__).resolve().parents[1]


def first_layer_reads(model, names):
    """For each first-layer LUT: list of (feature name, threshold) it reads."""
    mp = model.exported["layers"][0]["mapping"]
    nb = model.therm.num_bits
    th = model.therm.thresholds
    return [[(names[b // nb], float(th[b // nb, b % nb])) for b in row] for row in mp]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", required=True)
    ap.add_argument("--shap-run", default=None)
    ap.add_argument("--max-windows-shap", type=int, default=20000)
    args = ap.parse_args()
    run = Path(args.run)
    metrics = json.loads((run / "metrics.json").read_text())
    op = metrics["operating_points"]["best_f1"]
    folds = load_folds(REPO / "configs/folds_inner5.json")
    store = FeatureStore()
    usage_tp, usage_fp = defaultdict(float), defaultdict(float)
    n_tp = n_fp = 0
    static = defaultdict(int)
    cases = {"tp": None, "fp": None}
    for f in sorted((REPO / "checkpoints" / run.name).glob("fold_*.pkl")):
        k = int(f.stem.split("_")[1])
        obj = pickle.load(open(f, "rb"))
        m, cols, names = obj["model"], obj["cols"], obj["features"]
        reads = first_layer_reads(m, names)
        if len(m.exported["layers"]) != 1:
            print("note: multi-layer DWN; attributing through first-layer LUTs only")
        for row in reads:
            for name, _ in row:
                static[name] += 1
        L = len(reads)
        half = (L + 1) // 2
        for r in store.iter_runs(sorted(s for s, fk in folds.items() if fk == k)):
            bits = m.therm.encode(r.X[:, cols]).numpy().astype(np.uint8)
            mp, tt = m.exported["layers"][0]["mapping"], m.exported["layers"][0]["tables"]
            addr = np.zeros((len(bits), L), dtype=np.int64)
            for lb in range(mp.shape[1]):
                addr |= bits[:, mp[:, lb]].astype(np.int64) << lb
            fire = tt[np.arange(L)[None, :], addr]
            score = fire[:, half:].sum(1).astype(np.int64) - fire[:, :half].sum(1).astype(np.int64)
            gated = np.where(gate_mask(r.artefact, op["gate"]), -np.inf, score.astype(float))
            events = run_events_at(kth_of_last(gated, op["k"]), op["threshold"])
            ref = prepare_ref([tuple(s) for s in r.seizures], r.duration_s)
            for a, b in events:
                is_tp = any(a < rb and b > ra for ra, rb in ref)
                w = np.arange(max(0, int(a) - 2), min(len(score), int(b) - 1))
                if not len(w):
                    continue
                counts = defaultdict(float)
                for j in range(half, L):
                    frac = fire[w, j].mean()
                    for name, _ in reads[j]:
                        counts[name] += frac / len(reads[j])
                tgt = usage_tp if is_tp else usage_fp
                for name, v in counts.items():
                    tgt[name] += v
                n_tp += is_tp
                n_fp += not is_tp
                strength = float(score[w].max())
                key = "tp" if is_tp else "fp"
                if cases[key] is None or strength > cases[key]["peak_score"]:
                    top = sorted(counts.items(), key=lambda kv: -kv[1])[:6]
                    lut_detail = [{"lut": j, "reads": reads[j]} for j in range(half, L) if fire[w, j].mean() > 0.9][:3]
                    cases[key] = {"subject": r.subject, "run": r.run, "start_s": a, "end_s": b, "peak_score": strength,
                                  "top_features": top, "example_luts": lut_detail}
    norm = lambda d, n: {k2: v / max(n, 1) for k2, v in d.items()}
    tp, fp = norm(usage_tp, n_tp), norm(usage_fp, n_fp)
    feats = sorted(set(tp) | set(fp), key=lambda x: -(tp.get(x, 0) + fp.get(x, 0)))
    out = {"operating_point": {kk: op[kk] for kk in ("gate", "k", "threshold")}, "n_true_alarms": n_tp,
           "n_false_alarms": n_fp, "static_reads": dict(sorted(static.items(), key=lambda kv: -kv[1])),
           "usage_true_alarms": tp, "usage_false_alarms": fp, "cases": cases}
    if args.shap_run:
        import shap
        shap_abs = defaultdict(float)
        for f in sorted((REPO / "checkpoints" / Path(args.shap_run).name).glob("fold_*.pkl")):
            k = int(f.stem.split("_")[1])
            obj = pickle.load(open(f, "rb"))
            X = np.concatenate([r.X[:, obj["cols"]] for r in store.iter_runs(
                sorted(s for s, fk in folds.items() if fk == k))])
            Xs = X[np.random.default_rng(k).choice(len(X), min(len(X), args.max_windows_shap), replace=False)]
            sv = shap.TreeExplainer(obj["model"].m).shap_values(Xs)
            sv = sv[1] if isinstance(sv, list) else sv
            for name, v in zip(obj["features"], np.abs(sv).mean(0)):
                shap_abs[name] += v
        from scipy.stats import spearmanr
        common = [n for n in feats if n in shap_abs]
        rho = spearmanr([tp.get(n, 0) for n in common], [shap_abs[n] for n in common])
        out["shap_mean_abs"] = dict(sorted(shap_abs.items(), key=lambda kv: -kv[1]))
        out["spearman_dwn_true_alarm_usage_vs_shap"] = {"rho": float(rho.statistic), "p": float(rho.pvalue),
                                                        "n_features": len(common)}
    (run / "n7_interpretability.json").write_text(json.dumps(out, indent=1, default=float) + "\n")
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    top = feats[:20][::-1]
    fig, ax = plt.subplots(figsize=(6, 5), dpi=150)
    y = np.arange(len(top))
    ax.barh(y + 0.2, [tp.get(n, 0) for n in top], 0.4, label=f"true alarms (n={n_tp})", color="#2a6fdb")
    ax.barh(y - 0.2, [fp.get(n, 0) for n in top], 0.4, label=f"false alarms (n={n_fp})", color="#e8833a")
    ax.set_yticks(y, top, fontsize=7)
    ax.set_xlabel("firing seizure-group LUT inputs per alarm")
    ax.legend(frameon=False, fontsize=7)
    fig.tight_layout()
    (REPO / "results" / "figures").mkdir(parents=True, exist_ok=True)
    fig.savefig(REPO / "results" / "figures" / "n7_feature_usage.png")
    print(json.dumps({kk: out[kk] for kk in ("n_true_alarms", "n_false_alarms")}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
