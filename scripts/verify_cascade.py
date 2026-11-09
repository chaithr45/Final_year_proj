#!/usr/bin/env python3
"""Two-stage detector with post-ictal verification (N8), developed on the training patients only.

Stage 1 is a finished LUT network run at a sensitive operating point: every rising edge of its alarm
("at least k of the last 10 s score >= th1") opens a candidate event [t0, t1). Stage 2 waits until t0 + delay and
verifies the candidate from three windows of the integer feature stream, all with power-of-two lengths so that
every mean is a sum and a shift:

    before  [t0 - 136, t0 - 8)        128 s   the patient's own baseline
    during  [t0, t0 + 16)              16 s   ictal evidence
    after   [t0 + a, t0 + a + L)       L s    post-ictal evidence (variant d96: a = 32, L = 64; d48: a = 16, L = 32)

Verifier inputs: the during and after means of 45 base features (EEG, ECG, EMG, motion), their changes from the
baseline and the after-minus-during change, the stage-1 score in the during and after windows, the candidate's
duration (capped at the delay), the number of candidates in the previous 10 min and the sensor-presence bits.
Confirmed candidates keep their stage-1 extent, so the output is an event log with a decision delay of
a + L seconds (96 s or 48 s); it is not an instant alarm.

Stage 1 uses the out-of-fold scores of the inner-CV run (cache/oof/<run>/). The verifier is trained with the same
patient-wise folds (configs/folds_inner5.json): each fold's candidates are scored by a verifier trained on the other
four folds' candidates, so every number here is out-of-fold. Metrics are the dataset paper's (any-overlap
sensitivity, mean over recordings with a seizure; false alarms per hour, mean over recordings), computed with the
vectorised scorer of scripts/paper_point_cv.py (identical to the literal port).

Verifiers: lgbm (reference) and dwn (LUT-native: thermometer + 6-input LUT network on the 24 inputs with the
highest LightGBM gain in the training folds).

Usage:  python scripts/verify_cascade.py --cv-run 20261108-145504_n4_distill_s0 --k1 10 --th1 2 4 6 \
            --variant d96 --verifier lgbm
Output: results/tables/verify_cv.json (merged by configuration), printed table
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
from pathlib import Path

import numpy as np

from seizelut.data.featureset import FeatureStore
from seizelut.data.split import official_train_subjects
from seizelut.eval.operating import kth_of_last
from seizelut.features.spec import FEATURES

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "results/tables/verify_cv.json"
_spec = importlib.util.spec_from_file_location("ppcv", REPO / "scripts/paper_point_cv.py")
ppcv = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ppcv)

BASE_FEATS = ([f for f in FEATURES[:30]] + ["eeg_sign_agree", "ecg_log_rr", "ecg_log_masrd"]
              + ["emg_mav", "emg_ll", "emg_zc", "emg_hl_ratio"]
              + [f"mov_{s}_{k}" for s in ("acc", "gyr") for k in ("mag", "jerk", "act", "band")])
FIDX = [FEATURES.index(f) for f in BASE_FEATS]
PRES = [FEATURES.index(f) for f in ("present_ecg", "present_emg", "present_mov_acc", "present_mov_gyr")]
VARIANTS = {"d96": (32, 64), "d48": (16, 32)}
PRE, PRE_GAP, DUR = 128, 8, 16


def names(variant):
    out = []
    for w in ("during", "after", "during-before", "after-before", "after-during"):
        out += [f"{f}:{w}" for f in BASE_FEATS]
    out += ["s1_during_max", "s1_during_mean", "s1_after_mean", "s1_after_frac", "dur_capped", "n_prev_10min"]
    out += ["present_ecg", "present_emg", "present_mov_acc", "present_mov_gyr"]
    return out


def wmean(cs, a, b):
    """Means of rows [a, b) from prefix sums cs (len n+1), windows clipped to the recording; empty -> nan."""
    n = len(cs) - 1
    a = np.clip(a, 0, n); b = np.clip(b, 0, n)
    m = (b - a).astype(float)
    out = (cs[b] - cs[a]) / np.where(m > 0, m, 1)[:, None]
    out[m == 0] = np.nan
    return out


def event_features(X, q, s, t0, t1, th1, variant):
    a_off, L = VARIANTS[variant]
    delay = a_off + L
    F = X[:, FIDX].astype(np.float64)
    cs = np.concatenate([np.zeros((1, F.shape[1])), np.cumsum(F, 0)])
    pre = wmean(cs, t0 - PRE - PRE_GAP, t0 - PRE_GAP)
    dur = wmean(cs, t0, t0 + DUR)
    aft = wmean(cs, t0 + a_off, t0 + a_off + L)
    pre = np.where(np.isnan(pre), dur, pre)          # no baseline at the start of a recording: no change
    aft_ = np.where(np.isnan(aft), dur, aft)
    s = np.where(np.isfinite(s), s, np.nan).astype(np.float64)
    q = np.where(np.isfinite(q), q, -1e9)
    ss = np.concatenate([[0.0], np.cumsum(np.nan_to_num(s))])
    qa = np.concatenate([[0.0], np.cumsum(q >= th1)])
    n = len(s)
    c = lambda v: np.clip(v, 0, n)
    s_dmax = np.array([np.nanmax(s[c(a):c(a + DUR)]) if c(a + DUR) > c(a) else np.nan for a in t0])
    s_dmean = (ss[c(t0 + DUR)] - ss[c(t0)]) / np.maximum(c(t0 + DUR) - c(t0), 1)
    s_amean = (ss[c(t0 + a_off + L)] - ss[c(t0 + a_off)]) / np.maximum(c(t0 + a_off + L) - c(t0 + a_off), 1)
    s_afrac = (qa[c(t0 + a_off + L)] - qa[c(t0 + a_off)]) / np.maximum(c(t0 + a_off + L) - c(t0 + a_off), 1)
    dcap = np.minimum(t1 - t0, delay).astype(float)
    nprev = np.searchsorted(t0, t0, side="left") - np.searchsorted(t0, t0 - 600, side="left")
    pres = X[np.clip(t0, 0, n - 1)][:, PRES].astype(float)
    return np.column_stack([dur, aft_, dur - pre, aft_ - pre, aft_ - dur,
                            s_dmax, s_dmean, s_amean, s_afrac, dcap, nprev, pres]).astype(np.float32)


def collect(run, k1, th1s, variant, subjects):
    store = FeatureStore("int")
    d = REPO / "cache/oof" / run
    recs = []
    for key in store.runs_of(subjects):
        r = store.load_run(key)
        s = np.load(d / f"{key}.npy").astype(np.float64)
        q = kth_of_last(s, k1)
        ev = {}
        for th1 in th1s:
            st, en = ppcv._events(q >= th1) if (q >= th1).any() else (np.array([], int), np.array([], int))
            if len(st):
                feats = event_features(r.X, q, s, st, en, th1, variant)
                lab = np.array([r.y[a:b].any() for a, b in zip(st, en)], dtype=np.int8)
            else:
                feats, lab = np.zeros((0, len(names(variant))), np.float32), np.zeros(0, np.int8)
            ev[th1] = (st, en, feats, lab)
        recs.append({"key": key, "subject": r.subject, "y": r.y.astype(np.int8), "n": len(r.y), "ev": ev})
    return recs


def make_verifier(kind, seed=0):
    if kind == "lgbm":
        from seizelut.models.registry import LightGBM
        return LightGBM(n_estimators=300, num_leaves=15, learning_rate=0.05, min_child_samples=20, random_state=seed)
    raise ValueError(kind)


def fit_score(kind, Xtr, ytr, Xte, seed=0):
    if kind == "lgbm":
        m = make_verifier("lgbm", seed).fit(Xtr, ytr)
        return m.score(Xte), m
    if kind == "dwn":
        from seizelut.models.registry import DWNModel, LightGBM
        g = LightGBM(n_estimators=200, num_leaves=15, learning_rate=0.05, min_child_samples=20,
                     random_state=seed).fit(Xtr, ytr)
        imp = g.m.booster_.feature_importance("gain")
        cols = np.argsort(-imp)[:24]
        med = np.nanmedian(Xtr[:, cols], 0)
        fill = lambda A: np.where(np.isnan(A), med, A)
        m = DWNModel(bits=8, layers=(50,), n=6, epochs=30, lr=1e-2, batch=512, seed=seed, threads=3)
        m.fit(fill(Xtr[:, cols]), ytr)
        return m.score(fill(Xte[:, cols])).astype(float), (m, cols, med)
    raise ValueError(kind)


def apply_verifier(kind, fitted, X):
    """Score new candidates with a verifier returned by fit_score (no refitting)."""
    if kind == "lgbm":
        return fitted.score(X)
    m, cols, med = fitted
    return m.score(np.where(np.isnan(X[:, cols]), med, X[:, cols])).astype(float)


def paper_metrics(recs, th1, accept):
    """accept: per recording, a boolean array over its stage-1 candidates."""
    fa, sens, on, tot = [], [], 0, 0
    for r, acc in zip(recs, accept):
        st, en, _, _ = r["ev"][th1]
        mask = np.zeros(r["n"], bool)
        for a, b in zip(st[acc], en[acc]):
            mask[a:b] = True
        tp, fp, fn = ppcv.fast_ovlp(r["y"], mask)
        fa.append(fp * 3600 / r["n"])
        on += mask.sum(); tot += r["n"]
        if r["y"].any():
            sens.append(tp / (tp + fn))
    return float(np.mean(fa)), float(np.mean(sens)), float(on / tot)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cv-run", required=True)
    ap.add_argument("--k1", type=int, default=10)
    ap.add_argument("--th1", type=float, nargs="+", required=True)
    ap.add_argument("--variant", choices=list(VARIANTS), default="d96")
    ap.add_argument("--verifier", choices=["lgbm", "dwn"], default="lgbm")
    ap.add_argument("--budgets", type=float, nargs="+", default=[5.0, 10.0, 50.0, 90.0])
    ap.add_argument("--max-on", type=float, default=0.05, help="largest fraction of time in alarm allowed")
    args = ap.parse_args()
    t = time.time()
    folds = json.loads((REPO / "configs/folds_inner5.json").read_text())["folds"]
    recs = collect(args.cv_run, args.k1, args.th1, args.variant, official_train_subjects())
    print(f"loaded {len(recs)} recordings in {time.time() - t:.0f} s", flush=True)
    res = json.loads(OUT.read_text()) if OUT.exists() else {}
    for th1 in args.th1:
        allX = np.concatenate([r["ev"][th1][2] for r in recs])
        ally = np.concatenate([r["ev"][th1][3] for r in recs])
        fold_of = np.concatenate([[folds[r["subject"]]] * len(r["ev"][th1][3]) for r in recs]).astype(int)
        p = np.zeros(len(ally))
        for f in sorted(set(folds.values())):
            te = fold_of == f
            if te.any():
                p[te], _ = fit_score(args.verifier, allX[~te], ally[~te], allX[te])
        off = np.cumsum([0] + [len(r["ev"][th1][3]) for r in recs])
        per_rec = [p[off[i]:off[i + 1]] for i in range(len(recs))]
        s1 = paper_metrics(recs, th1, [np.ones(len(x), bool) for x in per_rec])
        grid = np.unique(np.quantile(p, np.linspace(0, 0.999, 120))) if len(p) else []
        pts = [(float(th2), *paper_metrics(recs, th1, [x >= th2 for x in per_rec])) for th2 in grid]
        print(f"th1={th1}: {len(ally)} candidates ({ally.mean() * 100:.2f} % true); stage 1 alone "
              f"{s1[1] * 100:.1f} % at {s1[0]:.2f} FA/h, alarm on {s1[2] * 100:.2f} %", flush=True)
        best = {}
        for b in args.budgets:
            ok = [q for q in pts if q[1] <= b and q[3] <= args.max_on]
            if ok:
                th2, fa, se, on = max(ok, key=lambda q: (q[2], -q[1]))
                best[str(b)] = {"th2": th2, "cv_fa_per_hour": fa, "cv_sens": se, "cv_time_in_alarm": on}
                print(f"   budget {b:5.1f} FA/h: th2={th2:.4g} -> CV sens {se * 100:.1f} % at {fa:.2f} FA/h "
                      f"(alarm on {on * 100:.2f} %)", flush=True)
        name = f"{args.cv_run}|k{args.k1}|th1={th1}|{args.variant}|{args.verifier}"
        res[name] = {"stage1": {"fa": s1[0], "sens": s1[1], "time_in_alarm": s1[2]}, "n_candidates": int(len(ally)),
                     "frac_true": float(ally.mean()) if len(ally) else None, "budgets": best, "points": pts,
                     "delay_s": sum(VARIANTS[args.variant])}
        OUT.write_text(json.dumps(res))
    print(f"done in {time.time() - t:.0f} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
