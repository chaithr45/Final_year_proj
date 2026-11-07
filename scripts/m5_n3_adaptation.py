#!/usr/bin/env python3
"""N3: label-free per-patient adaptation of the thermometer thresholds (Section 6.3).

For every validation patient of every inner fold of a finished DWN run:
  * adaptation data = the patient's first H hours (runs in order), no labels used;
  * variants
      requantile : thresholds re-fitted to the patient's own quantiles at the training levels
      offset     : thresholds shifted by (patient median - training median) per feature
      streaming  : integer online quantile tracker over the first H hours, then frozen
                   (t += 2^-g if x > t else -= ..., the hardware-realisable rule)
  * the network (mapping, LUTs) never changes; only the threshold registers do;
  * adapted and non-adapted models are scored on exactly the same data after the window,
    with the run's own operating point (gate, k, threshold) re-chosen on the same data for both.
Reports SzCORE metrics, the paired difference per patient, and how many seizures fell inside
the adaptation windows.

Usage: python scripts/m5_n3_adaptation.py --run results/runs/<dwn run> --hours 1 2 4
"""
from __future__ import annotations

import argparse
import json
import pickle
import sys
from pathlib import Path

import numpy as np

from seizelut.data.featureset import FeatureStore
from seizelut.data.split import load_folds
from seizelut.eval.operating import choose, sweep
from seizelut.eval.stats import paired_wilcoxon
from seizelut.models.dwn import DistributiveThermometer, integer_forward

REPO = Path(__file__).resolve().parents[1]


def level_of(th: DistributiveThermometer) -> np.ndarray:
    b = th.num_bits
    return np.arange(1, b + 1) / (b + 1)


def adapt(th: DistributiveThermometer, Xa: np.ndarray, variant: str, train_median=None) -> DistributiveThermometer:
    new = DistributiveThermometer(th.num_bits)
    if variant == "requantile":
        new.thresholds = np.floor(np.quantile(Xa, level_of(th), axis=0)).T
    elif variant == "offset":
        shift = np.median(Xa, axis=0) - train_median
        new.thresholds = th.thresholds + np.round(shift)[:, None]
    elif variant == "streaming":
        t = th.thresholds.astype(np.int64) << 4                 # 4 guard bits
        lv = level_of(th)
        up = np.maximum(1, np.round(16 * (1 - lv))).astype(np.int64)    # step sizes in guard units
        dn = np.maximum(1, np.round(16 * lv)).astype(np.int64)
        for x in Xa.astype(np.int64):
            above = (x[:, None] << 4) > t
            t = t + np.where(above, up[None, :], -dn[None, :])
        new.thresholds = (t >> 4).astype(np.float64)
    else:
        raise ValueError(variant)
    return new


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", required=True)
    ap.add_argument("--hours", nargs="+", type=float, default=[1, 2, 4])
    ap.add_argument("--variants", nargs="+", default=["requantile", "offset", "streaming"])
    args = ap.parse_args()
    run = Path(args.run)
    ck = REPO / "checkpoints" / run.name
    folds = load_folds(REPO / "configs/folds_inner5.json")
    store = FeatureStore()
    results = {}
    for H in args.hours:
        per_variant = {v: [] for v in ["none", *args.variants]}
        n_sz_in_window, n_sz_total = 0, 0
        for f in sorted(ck.glob("fold_*.pkl")):
            k = int(f.stem.split("_")[1])
            obj = pickle.load(open(f, "rb"))
            m, cols = obj["model"], obj["cols"]
            th = m.therm
            train_med = np.median(th.thresholds, axis=1)          # median-level threshold ~ training median
            for sub in sorted(s for s, fk in folds.items() if fk == k):
                runs = sorted(store.iter_runs([sub]), key=lambda r: int(r.run.split("-")[1]))
                X = np.concatenate([r.X[:, cols] for r in runs])
                n_adapt = int(H * 3600)
                if len(X) <= n_adapt + 3600:
                    continue
                Xa = X[:n_adapt]
                offset = 0
                for r in runs:
                    for a, b in r.seizures:
                        n_sz_total += 1
                        n_sz_in_window += (offset + a) < n_adapt
                    offset += len(r.y)
                for variant in per_variant:
                    t2 = th if variant == "none" else adapt(th, Xa, variant, train_med)
                    pos = 0
                    for r in runs:
                        lo = max(0, n_adapt - pos)
                        pos += len(r.y)
                        if lo >= len(r.y):
                            continue
                        bits = t2.encode(r.X[lo:, cols]).numpy().astype(np.uint8)
                        s = integer_forward(bits, m.exported).astype(np.float32)
                        sz = np.array([(a - lo, b - lo) for a, b in r.seizures if b - lo > 0]).reshape(-1, 2)
                        per_variant[variant].append({"subject": sub, "score": s, "artefact": r.artefact[lo:],
                                                     "seizures": np.clip(sz, 0, None), "duration_s": float(len(s) + 1)})
        out = {"hours": H, "seizures_in_adaptation_window": n_sz_in_window, "seizures_total": n_sz_total}
        base_rows = sweep(per_variant["none"], ks=(6, 8, 10), gates=("none", "both"), n_thresholds=30)
        base = choose(base_rows)["best_f1"]
        for variant, recs in per_variant.items():
            rows = sweep(recs, ks=(6, 8, 10), gates=("none", "both"), n_thresholds=30)
            best = choose(rows)["best_f1"]
            entry = {kk: best[kk] for kk in ("gate", "k", "threshold", "f1", "sensitivity", "precision", "fp_per_24h")}
            if variant != "none":
                subs = sorted(best["per_subject"])
                def f1s(op):
                    vals = []
                    for s in subs:
                        tp, fp, nref, h = op["per_subject"][s]
                        se = tp / nref if nref else np.nan
                        pr = tp / (tp + fp) if tp + fp else 0.0
                        vals.append(2 * se * pr / (se + pr) if nref and se + pr > 0 else 0.0)
                    return np.array(vals)
                entry["vs_none_f1"] = paired_wilcoxon(f1s(best), f1s(base))
            out[variant] = entry
        results[f"H{H:g}"] = out
        print(json.dumps(out, indent=1, default=float), flush=True)
    (run / "n3_adaptation.json").write_text(json.dumps(results, indent=1, default=float) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
