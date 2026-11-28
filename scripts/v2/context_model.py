#!/usr/bin/env python3
"""v2 WP2: context model (stage 2), stacked on v1 out-of-fold scores, trained with the same patient-wise folds.

For every second t of a recording it builds multi-scale summaries of
  * the base models' out-of-fold scores (log-odds): value, past means over 10-600 s, past maxima over 10-180 s, and the
    value relative to the past 30 min (the patient's own recent level);
  * selected signal features (heart rate, RR variability, EMG, movement, EEG power) relative to the same recording's
    past 5 min and past hour;
then a LightGBM classifier per fold is trained on the other four folds' rows and predicts its own fold. Because every
base score is out-of-fold, no stage of the model ever sees the patient it scores.

mode "causal": only past and present seconds (real-time alarm).
mode "delayed": adds windows reaching D seconds into the future (seizure logging / alarm D seconds late).

Usage: python scripts/v2/context_model.py --name ctx_causal --mode causal
Output: cache/oof/v2_<name>_s<seed>/<recording>.npy, results/v2/<name>_importance.json
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
from scipy.ndimage import maximum_filter1d

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts" / "v2"))
from harness import load_meta, evaluate, line  # noqa: E402

from seizelut.data.featureset import FeatureStore  # noqa: E402
import seizelut.features.spec as spec               # noqa: E402

BASES = {"lgbm": "20261106-184317_lgbm_s0", "cat": "20261106-200254_catboost_s0",
         "xgb": "20261106-191103_xgb_s0", "dwn": "20261108-145504_n4_distill_s0",
         "rel": "v2_base_rel_s0"}
RAW = ["ecg_log_rr", "ecg_log_masrd", "emg_mav", "emg_ll", "emg_zc", "mov_acc_mag", "mov_acc_act", "mov_gyr_mag",
       "mov_acc_jerk", "eeg_ll_mean", "eeg_mav_mean", "eeg_delta_mean", "eeg_theta_mean", "eeg_beta_mean",
       "eeg_hf_mean", "eeg_sign_agree", "eeg_zc_mean"]


def logit(p):
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p))


def past_mean(x, w):
    cs = np.concatenate([[0.0], np.cumsum(x)])
    t = np.arange(1, len(x) + 1)
    lo = np.maximum(t - w, 0)
    return (cs[t] - cs[lo]) / (t - lo)


def fut_mean(x, w):
    """Mean over [t, t+w)."""
    return past_mean(x[::-1], w)[::-1]


def past_max(x, w):
    # window [t-w+1, t]
    return maximum_filter1d(x, size=w, origin=(w - 1) // 2, mode="nearest")


def fut_max(x, w):
    return past_max(x[::-1], w)[::-1]


def build(scores: dict, X: np.ndarray, present: np.ndarray, artefact: np.ndarray, mode: str, delay: int):
    cols, names = [], []
    for nm, s in scores.items():
        b = logit(s)
        cols.append(b); names.append(f"{nm}")
        for w in (10, 30, 60, 180, 600):
            cols.append(past_mean(b, w)); names.append(f"{nm}_pmean{w}")
        for w in (10, 30, 60, 180):
            cols.append(past_max(b, w)); names.append(f"{nm}_pmax{w}")
        cols.append(b - past_mean(b, 1800)); names.append(f"{nm}_rel1800")
        cols.append(past_mean(b, 30) - past_mean(b, 1800)); names.append(f"{nm}_m30rel1800")
        if mode == "delayed":
            for w in (10, 30, 60, delay):
                cols.append(fut_mean(b, min(w, delay))); names.append(f"{nm}_fmean{w}")
            cols.append(fut_max(b, delay)); names.append(f"{nm}_fmax{delay}")
    idx = {n: i for i, n in enumerate(spec.FEATURES)}
    for nm in RAW:
        r = X[:, idx[nm]].astype(np.float64)
        m300, m3600 = past_mean(r, 300), past_mean(r, 3600)
        cols += [r - m300, r - m3600, past_mean(r, 30) - m3600, past_mean(r, 10) - m300]
        names += [f"{nm}_rel300", f"{nm}_rel3600", f"{nm}_m30rel3600", f"{nm}_m10rel300"]
        if mode == "delayed":
            cols.append(fut_mean(r, delay) - m3600); names.append(f"{nm}_f{delay}rel3600")
    for j in range(present.shape[1]):
        cols.append(present[:, j].astype(np.float64)); names.append(f"present{j}")
    cols += [artefact[:, 0].astype(np.float64), artefact[:, 1].astype(np.float64)]
    names += ["art0", "art1"]
    t = np.arange(len(X), dtype=np.float64)
    cols.append(np.minimum(t, 3600.0)); names.append("t_since_start_cap")
    return np.stack(cols, axis=1).astype(np.float32), names


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True)
    ap.add_argument("--mode", choices=("causal", "delayed"), default="causal")
    ap.add_argument("--delay", type=int, default=60)
    ap.add_argument("--bases", nargs="+", default=list(BASES))
    ap.add_argument("--bg", type=int, default=600000, help="background rows sampled for training (all folds)")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--rounds", type=int, default=600)
    ap.add_argument("--leaves", type=int, default=63)
    args = ap.parse_args()
    import lightgbm as lgb

    t0 = time.time()
    meta = load_meta()
    store = FeatureStore("int")
    rng = np.random.default_rng(args.seed)
    n_total = sum(len(m["y"]) for m in meta)
    p_bg = args.bg / n_total
    bdirs = {b: REPO / "cache/oof" / BASES[b] for b in args.bases}

    def rec_features(m):
        sc = {b: np.load(bdirs[b] / f"{m['key']}.npy").astype(np.float64) for b in args.bases}
        with np.load(store.files[m["key"]]) as d:
            X = d["X"]
        return build(sc, X, m["present"], m["artefact"], args.mode, args.delay)

    # pass 1: training rows
    Xs, ys, fs = [], [], []
    names = None
    for i, m in enumerate(meta):
        F, names = rec_features(m)
        y = m["y"]
        sel = (y == 1) | (rng.random(len(y)) < p_bg)
        # also keep the 10 minutes around every seizure (context the model must learn to reject or accept)
        Xs.append(F[sel]); ys.append(y[sel]); fs.append(np.full(sel.sum(), m["fold"]))
        if i % 300 == 0:
            print(f"pass1 {i}/{len(meta)} {time.time()-t0:.0f}s", flush=True)
    X, y, fo = np.concatenate(Xs), np.concatenate(ys), np.concatenate(fs)
    del Xs, ys, fs
    print(f"training rows {len(y)} positives {int(y.sum())} features {X.shape[1]}", flush=True)

    params = {"objective": "binary", "learning_rate": 0.05, "num_leaves": args.leaves, "min_data_in_leaf": 200,
              "feature_fraction": 0.8, "bagging_fraction": 0.8, "bagging_freq": 1, "lambda_l2": 1.0,
              "scale_pos_weight": 1.0, "verbose": -1, "num_threads": 4, "seed": args.seed}
    models, imp = {}, np.zeros(X.shape[1])
    for k in sorted(set(fo.tolist())):
        tr = fo != k
        ds = lgb.Dataset(X[tr], y[tr])
        models[k] = lgb.train(params, ds, num_boost_round=args.rounds)
        imp += models[k].feature_importance("gain")
        print(f"fold {k} trained {time.time()-t0:.0f}s", flush=True)
    del X, y, fo

    out = REPO / "cache/oof" / f"v2_{args.name}_s{args.seed}"
    out.mkdir(parents=True, exist_ok=True)
    preds = []
    for i, m in enumerate(meta):
        F, _ = rec_features(m)
        p = models[m["fold"]].predict(F, num_threads=4).astype(np.float32)
        np.save(out / f"{m['key']}.npy", p)
        preds.append(p.astype(np.float64))
        if i % 300 == 0:
            print(f"pass2 {i}/{len(meta)} {time.time()-t0:.0f}s", flush=True)
    order = np.argsort(-imp)
    res = REPO / "results/v2"
    res.mkdir(parents=True, exist_ok=True)
    (res / f"{args.name}_importance.json").write_text(json.dumps(
        [[names[j], float(imp[j])] for j in order], indent=0))
    (out / "config.json").write_text(json.dumps(vars(args), indent=1))
    rep = evaluate(preds, meta)
    allr = json.loads((res / "harness.json").read_text()) if (res / "harness.json").exists() else {}
    allr[f"v2_{args.name}_s{args.seed}"] = rep
    (res / "harness.json").write_text(json.dumps(allr, indent=1))
    print(line(f"v2_{args.name}", rep), flush=True)
    print(f"done {time.time()-t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
