#!/usr/bin/env python3
"""M6 final evaluation (Section 7.1, step 3): retrain on all 96 training patients, 5 seeds,
score the 29 test patients ONCE per seed.

The operating point (artefact gate, k, decision threshold) is taken from the finished inner-CV
run of the same config; nothing is tuned on test data. Metrics:
  * SzCORE event + sample scoring with the official `timescoring` library, mean over patients,
    pooled totals, 95 % patient-bootstrap intervals;
  * dataset-paper metrics on our alarms: any-overlap sensitivity and false alarms per hour
    (mean over recordings), window AUROC / AUPR of the raw score.
Writes results/runs/<id>/final_metrics.json and per-seed per-subject tables.

Usage: python scripts/run_final.py --config configs/m4/lgbm.yaml --cv-run results/runs/<inner-cv run> \
           --seeds 0 1 2 3 4 --final-test
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import yaml

from seizelut.data.featureset import FeatureStore
from seizelut.data.split import official_test_subjects, official_train_subjects
from seizelut.eval import seizeit2 as s2
from seizelut.eval.events import mask_to_events
from seizelut.eval.operating import gate_mask, kth_of_last
from seizelut.eval.runlog import log_test_access, new_run_dir, require_test_access
from seizelut.eval.stats import bootstrap_ci
from seizelut.eval.szcore import aggregate, score_recording
from seizelut.features import spec as S
from seizelut.models.registry import build

REPO = Path(__file__).resolve().parents[1]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", required=True)
    ap.add_argument("--cv-run", required=True, help="inner-CV run whose operating points are reused")
    ap.add_argument("--seeds", nargs="+", type=int, default=[0, 1, 2, 3, 4])
    ap.add_argument("--op", default="best_f1", choices=["best_f1", "sens_at_1fah"])
    ap.add_argument("--device", default=None)
    ap.add_argument("--final-test", action="store_true")
    args = ap.parse_args()
    test = official_test_subjects()
    require_test_access(test, args.final_test)
    cfg = yaml.safe_load(Path(args.config).read_text())
    if args.device:
        cfg["model"].setdefault("params", {})["device"] = args.device
    cv = json.loads((Path(args.cv_run) / "metrics.json").read_text())
    ops = {k: v for k, v in cv["operating_points"].items() if v}
    store = FeatureStore()
    missing = store.missing(test + official_train_subjects())
    if missing:
        raise SystemExit(f"feature cache incomplete: {missing[:5]}")
    run = new_run_dir(cfg["name"] + "_final", {**cfg, "cv_run": Path(args.cv_run).name, "seeds": args.seeds}, args.seeds[0])
    log_test_access(run, f"M6 final evaluation of {cfg['name']} (seeds {args.seeds})")
    names = S.FEATURES
    results = {"config": cfg["name"], "cv_run": Path(args.cv_run).name, "seeds": {}}
    for seed in args.seeds:
        X, y, *_ = store.training_set(official_train_subjects(), cfg.get("train", {}).get("bg_ratio", 20), seed=seed)
        fspec = cfg.get("features", "all")
        if isinstance(fspec, dict) and "mi_top" in fspec:
            from sklearn.feature_selection import mutual_info_classif
            sub = np.random.default_rng(seed).choice(len(y), size=min(len(y), 200_000), replace=False)
            mi = mutual_info_classif(X[sub].astype(np.float32), y[sub], random_state=seed)
            cols = list(np.argsort(-mi)[: fspec["mi_top"]])
        else:
            cols = list(range(len(names)))
        model = build(cfg["model"], log=print)
        if cfg["model"]["type"] in ("dwn", "lgn", "stateful_dwn", "mlp_int8"):
            model.p["seed"] = seed
        if getattr(model, "needs_store", False):
            model.fit_store(store, official_train_subjects(), cols, seed)
        else:
            model.fit(X[:, cols], y)
        del X
        runs = list(store.iter_runs(test))
        scores = (model.score_runs([r.X[:, cols] for r in runs]) if getattr(model, "needs_store", False)
                  else [model.score(r.X[:, cols]) for r in runs])
        seed_out = {"cost": model.cost([S.FEATURE_BITS[names[i]] for i in cols]),
                    "features": [names[i] for i in cols]}
        from sklearn.metrics import average_precision_score, roc_auc_score
        ally = np.concatenate([r.y for r in runs])
        alls = np.concatenate(scores)
        seed_out["window_auroc"] = float(roc_auc_score(ally, alls))
        seed_out["window_aupr"] = float(average_precision_score(ally, alls))
        for opname, op in ops.items():
            recs, paper = [], []
            for r, sc in zip(runs, scores):
                gated = np.where(gate_mask(r.artefact, op["gate"]), -np.inf, sc.astype(float))
                alarm = kth_of_last(gated, op["k"]) >= op["threshold"]
                hyp = [(a + 2.0, b + 2.0) for a, b in mask_to_events(alarm)]
                recs.append(score_recording(r.subject, f"{r.subject}_{r.run}", [tuple(s) for s in r.seizures], hyp,
                                            r.duration_s))
                # dataset-paper style: any-overlap on the per-second label grid, FP events per hour
                if r.y.any():
                    tp, fp, fn = s2.perf_measure_ovlp(r.y.astype(int), alarm.astype(int), fs=1, fixed=True)
                    paper.append({"sens": tp / (tp + fn), "fa_h": fp * 3600 / len(alarm)})
                else:
                    _, fp, _ = s2.perf_measure_ovlp(r.y.astype(int), alarm.astype(int), fs=1, fixed=True)
                    paper.append({"sens": np.nan, "fa_h": fp * 3600 / len(alarm)})
            agg = aggregate(recs)
            per_sub = agg["per_subject"]
            ci = {m: bootstrap_ci([v[m] for v in per_sub.values()]) for m in ("sensitivity", "precision", "f1", "fp_per_24h")}
            seed_out[opname] = {"operating_point": {k: op[k] for k in ("gate", "k", "threshold")},
                                "szcore_mean_over_subjects": agg["mean_over_subjects"], "szcore_pooled": agg["pooled"],
                                "bootstrap_ci": ci, "per_subject": per_sub,
                                "paper_metrics": {"sens_ovlp_mean_over_recordings": float(np.nanmean([p["sens"] for p in paper])),
                                                  "fa_per_hour_mean_over_recordings": float(np.mean([p["fa_h"] for p in paper]))}}
            m = agg["mean_over_subjects"]
            print(f"seed {seed} {opname}: SzCORE sens {m['sensitivity']:.3f} prec {m['precision']:.3f} "
                  f"F1 {m['f1']:.3f} FP/24h {m['fp_per_24h']:.1f}", flush=True)
        results["seeds"][str(seed)] = seed_out
        (run / "final_metrics.json").write_text(json.dumps(results, indent=1, default=float) + "\n")
    summary = {}
    for opname in ops:
        vals = {m: [results["seeds"][str(s)][opname]["szcore_mean_over_subjects"][m] for s in args.seeds]
                for m in ("sensitivity", "precision", "f1", "fp_per_24h")}
        summary[opname] = {m: {"mean": float(np.mean(v)), "std": float(np.std(v, ddof=1)) if len(v) > 1 else 0.0}
                           for m, v in vals.items()}
    results["summary_mean_std_over_seeds"] = summary
    (run / "final_metrics.json").write_text(json.dumps(results, indent=1, default=float) + "\n")
    print(json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
