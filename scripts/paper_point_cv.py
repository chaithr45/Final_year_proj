#!/usr/bin/env python3
"""Paper-matched operating points chosen on the training folds only (no test data).

For a finished inner-CV run, the out-of-fold scores (cache/oof/<run>/) of the 96 training patients are swept over
k (alarm when at least k of the last 10 s are positive) and the decision threshold, and scored with the dataset
paper's metrics, computed as in scripts/run_final.py: any-overlap sensitivity (mean over recordings with a seizure)
and false-alarm events per hour (mean over recordings). For each false-alarm budget it reports the operating point
with the highest training-fold sensitivity among those whose alarm is on at most --max-on of the time. Budgets default to just below the paper's two baselines
(SVM 11.0 FA/h, ChronoNet 100.5 FA/h).

Usage:  python scripts/paper_point_cv.py <inner-cv run name> [...] [--budgets 10 11 90 100]
Output: results/tables/paper_points_cv.json (merged by run name), printed table
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

from seizelut.data.featureset import FeatureStore
from seizelut.data.split import official_train_subjects
from seizelut.eval import seizeit2 as s2
from seizelut.eval.operating import kth_of_last

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "results/tables/paper_points_cv.json"


def load(run: str):
    store = FeatureStore("int")
    d = REPO / "cache/oof" / run
    ys, sc = [], []
    for key in store.runs_of(official_train_subjects()):
        f = d / f"{key}.npy"
        if not f.exists():
            raise SystemExit(f"missing out-of-fold scores {f}")
        sc.append(np.load(f).astype(np.float64))
        ys.append(store.load_labels(key).astype(int))
    return ys, sc


def thresholds(sc, n=80):
    alls = np.concatenate(sc)
    top = alls[alls >= np.quantile(alls, 0.5)]
    u = np.unique(top)
    if len(u) <= 400:
        return u
    return np.unique(np.quantile(alls, 1 - np.logspace(-5, np.log10(0.5), n)))


def _events(m):
    """Event index ranges [start, end) as mask2eventList (fs = 1) builds them, including its edge case."""
    d = np.diff(m.astype(np.int8))
    st = np.where(d == 1)[0] + 1
    en = np.where(d == -1)[0] + 1
    if len(st) == 0 and m[0]:
        return np.array([0]), np.array([len(m) - 1])
    if m[0]:
        st = np.concatenate([[0], st])
    if m[-1]:
        en = np.concatenate([en, [len(m)]])
    return st, en


def fast_ovlp(y, alarm):
    """Vectorised s2.perf_measure_ovlp(y, alarm, fs=1, fixed=True): (tp, fp, fn)."""
    ts, te = _events(y) if y.any() else (np.array([], int), np.array([], int))
    ps, pe = _events(alarm) if alarm.any() else (np.array([], int), np.array([], int))
    n = len(y)
    cy, ca = _covered(ts, te, n), _covered(ps, pe, n)
    # positive-length overlap of [a0, a1) and [b0, b1) with integer ends = at least one shared second
    tp = int(np.sum((ca[te] - ca[ts]) > 0)) if len(ts) else 0
    fp = int(np.sum((cy[pe] - cy[ps]) == 0)) if len(ps) else 0
    return tp, fp, len(ts) - tp


def _covered(st, en, n):
    """Prefix counts of the seconds covered by the events [st, en) (events as built, not the raw mask)."""
    d = np.zeros(n + 1, dtype=np.int64)
    np.add.at(d, st, 1)
    np.add.at(d, en, -1)
    cov = np.cumsum(d[:n]) > 0
    return np.concatenate([[0], np.cumsum(cov)])


def curve(ys, sc, k, ths):
    """(threshold, mean FA/h, mean sensitivity, fraction of time in alarm) per threshold, streaming."""
    fa = np.zeros(len(ths)); sens = np.zeros(len(ths)); on = np.zeros(len(ths)); n_sz = 0; tot = 0
    for y, s in zip(ys, sc):
        q = kth_of_last(s, k)
        has = bool(y.any()); n_sz += has; tot += len(q)
        for i, th in enumerate(ths):
            a = q >= th
            tp, fp, fn = fast_ovlp(y, a)
            fa[i] += fp * 3600 / len(q)
            on[i] += a.sum()
            if has:
                sens[i] += tp / (tp + fn)
    return [(float(t), float(f / len(ys)), float(se / n_sz), float(o / tot)) for t, f, se, o in zip(ths, fa, sens, on)]


def check_fast(ys, sc, n=40, seed=0):
    """The vectorised scorer must equal the literal port (on random recordings and thresholds)."""
    rng = np.random.default_rng(seed)
    for i in rng.choice(len(ys), size=min(n, len(ys)), replace=False):
        for k in (1, 10):
            q = kth_of_last(sc[i], k)
            for th in np.quantile(q[np.isfinite(q)], [0.5, 0.9, 0.99, 0.999]):
                a = (q >= th).astype(int)
                assert fast_ovlp(ys[i], a > 0) == s2.perf_measure_ovlp(ys[i], a, fs=1, fixed=True), (i, k, th)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("runs", nargs="+")
    ap.add_argument("--ks", type=int, nargs="+", default=[1, 2, 4, 6, 8, 10])
    ap.add_argument("--budgets", type=float, nargs="+", default=[5.0, 10.0, 50.0, 90.0])
    ap.add_argument("--max-on", type=float, default=0.05,
                    help="largest fraction of time in alarm allowed: the paper's metric counts alarm events, so an "
                         "alarm that stays on almost permanently looks cheap (excluded)")
    args = ap.parse_args()
    res = json.loads(OUT.read_text()) if OUT.exists() else {}
    for run in args.runs:
        ys, sc = load(run)
        check_fast(ys, sc)
        ths = thresholds(sc)
        pts = []
        for k in args.ks:
            pts += [(k, *p) for p in curve(ys, sc, k, ths)]
            print(f"{run} k={k}: {len(ths)} thresholds", flush=True)
        best = {}
        for b in args.budgets:
            ok = [p for p in pts if p[2] <= b and p[4] <= args.max_on]
            if ok:
                k, th, fa, se, on = max(ok, key=lambda p: (p[3], -p[2]))
                best[str(b)] = {"k": k, "threshold": th, "gate": "none", "cv_fa_per_hour": fa, "cv_sens": se,
                                "cv_time_in_alarm": on}
                print(f"  budget {b:6.1f} FA/h: k={k} th={th:.4g} -> CV sens {se * 100:.1f} % at {fa:.2f} FA/h "
                      f"(alarm on {on * 100:.2f} % of the time)")
        res[run] = {"budgets": best, "points": pts}
        OUT.write_text(json.dumps(res))
    return 0


if __name__ == "__main__":
    sys.exit(main())
