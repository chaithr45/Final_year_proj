#!/usr/bin/env python3
"""v2 WP3: per-second base model (LightGBM) on v1 features plus patient-relative features, patient-wise 5-fold CV.

Patient-relative features are causal: for each of the 45 context-source features x (spec.CONTEXT_SOURCES),
  x - mean(x over the past 300 s), x - mean(x over the past 3600 s), mean(x over the past 30 s) - mean(past 3600 s)
of the same recording. Nothing looks into the future and nothing uses labels, so they are valid in real time.

Usage: python scripts/v2/base_model.py --name base_rel --feat rel
Output: cache/oof/v2_<name>_s<seed>/<recording>.npy
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts" / "v2"))
from harness import load_meta, evaluate, line  # noqa: E402
from context_model import past_mean            # noqa: E402

from seizelut.data.featureset import FeatureStore  # noqa: E402
import seizelut.features.spec as spec               # noqa: E402


def feats(X: np.ndarray, mode: str) -> np.ndarray:
    X = X.astype(np.float32)
    if mode == "raw":
        return X
    idx = [spec.FEATURES.index(n) for n in spec.CONTEXT_SOURCES]
    cols = [X]
    for j in idx:
        x = X[:, j].astype(np.float64)
        m3600 = past_mean(x, 3600)
        cols.append(np.stack([x - past_mean(x, 300), x - m3600, past_mean(x, 30) - m3600], axis=1).astype(np.float32))
    return np.concatenate(cols, axis=1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True)
    ap.add_argument("--feat", choices=("raw", "rel"), default="rel")
    ap.add_argument("--bg-ratio", type=float, default=20)
    ap.add_argument("--trees", type=int, default=600)
    ap.add_argument("--leaves", type=int, default=63)
    ap.add_argument("--lr", type=float, default=0.05)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()
    import lightgbm as lgb

    t0 = time.time()
    meta = load_meta()
    store = FeatureStore("int")
    rng = np.random.default_rng(args.seed)
    n_pos = sum(int(m["y"].sum()) for m in meta)
    n_neg = sum(len(m["y"]) - int(m["y"].sum()) for m in meta)
    p_bg = min(1.0, args.bg_ratio * n_pos / n_neg)
    Xs, ys, fs = [], [], []
    for i, m in enumerate(meta):
        with np.load(store.files[m["key"]]) as d:
            F = feats(d["X"], args.feat)
        y = m["y"]
        sel = (y == 1) | (rng.random(len(y)) < p_bg)
        Xs.append(F[sel]); ys.append(y[sel]); fs.append(np.full(int(sel.sum()), m["fold"]))
        if i % 400 == 0:
            print(f"pass1 {i}/{len(meta)} {time.time()-t0:.0f}s", flush=True)
    X, y, fo = np.concatenate(Xs), np.concatenate(ys), np.concatenate(fs)
    del Xs, ys, fs
    print(f"training rows {len(y)} positives {int(y.sum())} features {X.shape[1]}", flush=True)
    params = {"objective": "binary", "learning_rate": args.lr, "num_leaves": args.leaves, "min_data_in_leaf": 100,
              "feature_fraction": 0.7, "bagging_fraction": 0.8, "bagging_freq": 1, "lambda_l2": 1.0,
              "verbose": -1, "num_threads": 4, "seed": args.seed}
    models = {}
    for k in sorted(set(fo.tolist())):
        tr = fo != k
        models[k] = lgb.train(params, lgb.Dataset(X[tr], y[tr]), num_boost_round=args.trees)
        print(f"fold {k} trained {time.time()-t0:.0f}s", flush=True)
    del X, y, fo
    out = REPO / "cache/oof" / f"v2_{args.name}_s{args.seed}"
    out.mkdir(parents=True, exist_ok=True)
    preds = []
    for i, m in enumerate(meta):
        with np.load(store.files[m["key"]]) as d:
            F = feats(d["X"], args.feat)
        p = models[m["fold"]].predict(F, num_threads=4).astype(np.float32)
        np.save(out / f"{m['key']}.npy", p)
        preds.append(p.astype(np.float64))
        if i % 400 == 0:
            print(f"pass2 {i}/{len(meta)} {time.time()-t0:.0f}s", flush=True)
    (out / "config.json").write_text(json.dumps(vars(args), indent=1))
    rep = evaluate(preds, meta)
    res = REPO / "results/v2"
    allr = json.loads((res / "harness.json").read_text()) if (res / "harness.json").exists() else {}
    allr[f"v2_{args.name}_s{args.seed}"] = rep
    (res / "harness.json").write_text(json.dumps(allr, indent=1))
    print(line(f"v2_{args.name}", rep), flush=True)
    print(f"done {time.time()-t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
