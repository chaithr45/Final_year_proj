#!/usr/bin/env python3
"""One evaluation on the 29 test patients of the pre-registered paper-matched detectors (N8).

Settings are read from results/tables/paper_points_prereg.json, which is committed before this script runs; they
were chosen on the training folds only (scripts/paper_point_cv.py, scripts/verify_cascade.py). Two detectors:

  plain     the frozen final LUT network (5 seeds, checkpoints/<n4_distill final run>/) at a lower threshold;
  cascade   the same network as stage 1 at a more sensitive threshold, followed by the post-ictal verifier, retrained
            on every training-fold candidate (out-of-fold stage-1 scores of the inner-CV run) and frozen.

Metrics: the dataset paper's (any-overlap sensitivity, mean over recordings with a seizure; false alarms per hour,
mean over recordings), the time in alarm, and SzCORE event metrics; mean +- std over the 5 seeds.

Usage:  python scripts/paper_points_test.py --final-test
Output: results/tables/paper_points_test.json, results/tables/paper_points_test.md; access logged in the final run.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import pickle
import sys
from pathlib import Path

import numpy as np

from seizelut.data.featureset import FeatureStore
from seizelut.data.split import official_test_subjects, official_train_subjects
from seizelut.eval.operating import kth_of_last, run_events_at, subject_metrics
from seizelut.eval.runlog import log_test_access, require_test_access

REPO = Path(__file__).resolve().parents[1]
PREREG = REPO / "results/tables/paper_points_prereg.json"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, REPO / f"scripts/{name}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


vc = _load("verify_cascade")
ppcv = vc.ppcv


def szcore(runs, masks):
    """SzCORE event metrics (mean over subjects) for per-second alarm masks."""
    from seizelut.eval.fastscore import prepare_ref, score_events
    counts = {}
    for r, m in zip(runs, masks):
        ev = run_events_at(m.astype(float), 0.5)
        tp, fp, nref = score_events(prepare_ref([tuple(x) for x in r.seizures], r.duration_s), ev)
        c = counts.setdefault(r.subject, [0, 0, 0, 0.0])
        c[0] += tp; c[1] += fp; c[2] += nref; c[3] += r.duration_s / 3600
    return subject_metrics(counts)


def paper(runs, masks):
    fa, sens, on, tot = [], [], 0, 0
    for r, m in zip(runs, masks):
        tp, fp, fn = ppcv.fast_ovlp(r.y.astype(int), m)
        fa.append(fp * 3600 / len(m)); on += m.sum(); tot += len(m)
        if r.y.any():
            sens.append(tp / (tp + fn))
    return {"sens": float(np.mean(sens)), "fa_per_hour": float(np.mean(fa)), "time_in_alarm": float(on / tot)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--final-test", action="store_true")
    args = ap.parse_args()
    pre = json.loads(PREREG.read_text())
    test = official_test_subjects()
    require_test_access(test, args.final_test)
    final = REPO / "results/runs" / pre["final_run"]
    log_test_access(final, "pre-registered paper-matched detectors, plain and post-ictal cascade (paper_points_test.py)")

    # the verifier: trained once on every training-fold candidate, frozen before the test data is read
    c = pre["cascade"]
    recs = vc.collect(pre["cv_run"], c["k1"], [c["th1"]], c["variant"], official_train_subjects())
    Xtr = np.concatenate([r["ev"][c["th1"]][2] for r in recs])
    ytr = np.concatenate([r["ev"][c["th1"]][3] for r in recs])
    del recs

    store = FeatureStore("int")
    runs = list(store.iter_runs(test))
    out = {"prereg": pre, "seeds": {}}
    verifier = None
    for ck in sorted((REPO / "checkpoints" / final.name).glob("seed_*.pkl")):
        obj = pickle.load(open(ck, "rb"))
        model, cols = obj["model"], obj["cols"]
        seed = int(ck.stem.split("_")[1])
        scores = [model.score(r.X[:, cols]).astype(np.float64) for r in runs]
        res = {}
        p = pre["plain"]
        masks = [kth_of_last(s, p["k"]) >= p["threshold"] for s in scores]
        res["plain"] = {"paper": paper(runs, masks), "szcore": szcore(runs, masks)}
        feats, cand = [], []
        for r, s in zip(runs, scores):
            q = kth_of_last(s, c["k1"])
            a = q >= c["th1"]
            st, en = ppcv._events(a) if a.any() else (np.array([], int), np.array([], int))
            cand.append((st, en))
            feats.append(vc.event_features(r.X, q, s, st, en, c["th1"], c["variant"]) if len(st)
                         else np.zeros((0, len(vc.names(c["variant"]))), np.float32))
        if verifier is None:          # trained once (seed 0) on the training-fold candidates, then frozen
            pv, verifier = vc.fit_score(c["verifier"], Xtr, ytr, np.concatenate(feats), seed=0)
        else:
            pv = vc.apply_verifier(c["verifier"], verifier, np.concatenate(feats))
        off = np.cumsum([0] + [len(f) for f in feats])
        for th2 in c["th2"]:
            masks = []
            for i, (r, (st, en)) in enumerate(zip(runs, cand)):
                m = np.zeros(len(r.y), bool)
                acc = pv[off[i]:off[i + 1]] >= th2
                for a0, b0 in zip(st[acc], en[acc]):
                    m[a0:b0] = True
                masks.append(m)
            res[f"cascade@{th2:g}"] = {"paper": paper(runs, masks), "szcore": szcore(runs, masks),
                                       "n_candidates": int(off[-1])}
        out["seeds"][str(seed)] = res
        print(seed, json.dumps({k: v["paper"] for k, v in res.items()}), flush=True)

    dets = ["plain"] + [f"cascade@{t:g}" for t in c["th2"]]
    summ = {}
    for det in dets:
        summ[det] = {}
        for part in ("paper", "szcore"):
            keys = out["seeds"]["0"][det][part].keys()
            summ[det][part] = {k: {"mean": float(np.nanmean([out["seeds"][s][det][part][k] for s in out["seeds"]])),
                                   "std": float(np.nanstd([out["seeds"][s][det][part][k] for s in out["seeds"]],
                                                          ddof=1))} for k in keys}
    out["summary"] = summ
    (REPO / "results/tables/paper_points_test.json").write_text(json.dumps(out, indent=1, default=float))
    lines = ["# Paper-matched detectors on the 29 test patients (pre-registered, N8)", "",
             "Settings chosen on the training folds and committed before this evaluation "
             "(`results/tables/paper_points_prereg.json`). Paper metrics: any-overlap sensitivity and false alarms "
             "per hour (mean over recordings), as in the dataset paper; mean +- std over 5 seeds. "
             "Generated by `python scripts/paper_points_test.py --final-test`.", "",
             "| Detector | Seizures detected | False alarms / h | Time in alarm | SzCORE F1 | Decision delay |",
             "|---|---|---|---|---|---|"]
    for det in dets:
        delay = "10 s window" if det == "plain" else f"{sum(vc.VARIANTS[c['variant']])} s"
        s = summ[det]
        lines.append(f"| {det} | {s['paper']['sens']['mean'] * 100:.1f} +- {s['paper']['sens']['std'] * 100:.1f} % | "
                     f"{s['paper']['fa_per_hour']['mean']:.2f} +- {s['paper']['fa_per_hour']['std']:.2f} | "
                     f"{s['paper']['time_in_alarm']['mean'] * 100:.2f} % | {s['szcore']['f1']['mean']:.3f} | {delay} |")
    lines += ["| SVM, published | 71.1 % | 11.0 | - | - | - |", "| ChronoNet, published | 84.2 % | 100.5 | - | - | - |"]
    (REPO / "results/tables/paper_points_test.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
