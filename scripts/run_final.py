#!/usr/bin/env python3
"""M6 final evaluation (Section 7.1, step 3): retrain on all 96 training patients, 5 seeds,
score the 29 test patients ONCE per seed.

The operating point (artefact gate, k, decision threshold) is taken from the finished inner-CV
run of the same config; nothing is tuned on test data. Metrics:
  * SzCORE event + sample scoring with the official `timescoring` library, mean over patients,
    pooled totals, 95 % patient-bootstrap intervals;
  * dataset-paper metrics on our alarms: any-overlap sensitivity and false alarms per hour
    (mean over recordings), window AUROC / AUPR of the raw score.
Training is scripts/run_inner_cv.py's fit_config() on all 96 training patients (same feature selection,
switches and seeds), with every trainable model seeded per seed. Each seed's model is kept in
checkpoints/<id>/seed_<s>.pkl for the export (M7). Test recordings are scored one at a time.
Writes results/runs/<id>/final_metrics.json and per-seed per-subject tables; an interrupted run is
continued with --resume <run dir> (finished seeds are kept).

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
from seizelut.eval.runlog import mark_complete, log_test_access, new_run_dir, require_test_access
from seizelut.eval.stats import bootstrap_ci
from seizelut.eval.szcore import aggregate, score_recording
from seizelut.models.training import bits_of, feature_names, fit_config, set_device

REPO = Path(__file__).resolve().parents[1]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", required=True)
    ap.add_argument("--cv-run", required=True, help="inner-CV run whose operating points are reused")
    ap.add_argument("--seeds", nargs="+", type=int, default=[0, 1, 2, 3, 4])
    ap.add_argument("--op", default="best_f1", choices=["best_f1", "sens_at_1fah"])
    ap.add_argument("--device", default=None)
    ap.add_argument("--final-test", action="store_true")
    ap.add_argument("--resume", default=None, help="unfinished final run directory to continue")
    ap.add_argument("--out", default=None, help="write runs/ and checkpoints under this directory (tests)")
    ap.add_argument("--features-root", default=None, help="feature cache root (tests)")
    ap.add_argument("--train-subjects", nargs="*", default=None, help="tests only (default: sub-001..096)")
    ap.add_argument("--test-subjects", nargs="*", default=None, help="tests only (default: sub-097..125)")
    args = ap.parse_args()
    out = Path(args.out).resolve() if args.out else REPO
    train = args.train_subjects or official_train_subjects()
    test = args.test_subjects or official_test_subjects()
    require_test_access(test, args.final_test)
    cfg = yaml.safe_load(Path(args.config).read_text())
    set_device(cfg, args.device)
    cv = json.loads((Path(args.cv_run) / "metrics.json").read_text())
    ops = {k: v for k, v in cv["operating_points"].items() if v}
    store = FeatureStore(root=Path(args.features_root) if args.features_root else None)
    store.stack = int(cfg.get("stack", 1))
    names = feature_names(store.stack)
    missing = store.missing(test + train)
    if missing:
        raise SystemExit(f"feature cache incomplete: {missing[:5]}")
    run_cfg = {**cfg, "cv_run": Path(args.cv_run).name, "seeds": args.seeds}
    if args.resume:
        run = Path(args.resume).resolve()
        results = json.loads((run / "final_metrics.json").read_text()) if (run / "final_metrics.json").exists() else None
    else:
        run = new_run_dir(cfg["name"] + "_final", run_cfg, args.seeds[0],
                          root=(out / "results" / "runs") if args.out else None)
        results = None
    results = results or {"config": cfg["name"], "cv_run": Path(args.cv_run).name, "seeds": {}}
    log_test_access(run, f"M6 final evaluation of {cfg['name']} (seeds {args.seeds})")
    logf = open(run / "log.txt", "a")

    def log(msg):
        print(msg, flush=True)
        logf.write(msg + "\n")
        logf.flush()

    import pickle
    ck = out / "checkpoints" / run.name
    ck.mkdir(parents=True, exist_ok=True)
    for seed in args.seeds:
        if str(seed) in results["seeds"]:
            log(f"seed {seed}: already done")
            continue
        log(f"seed {seed}: training on {len(train)} patients")
        model, cols, _ = fit_config(cfg, store, train, seed, log, seed_all_models=True)
        lf = getattr(model, "log", None)
        model.log = None
        with open(ck / f"seed_{seed}.pkl", "wb") as fh:
            pickle.dump({"model": model, "cols": cols, "features": [names[i] for i in cols]}, fh)
        model.log = lf
        runs, scores = [], []
        if getattr(model, "needs_store", False):
            X_list = []
            for r in store.iter_runs(test):
                X_list.append(np.ascontiguousarray(r.X[:, cols]))
                r.X = None
                runs.append(r)
            scores = model.score_runs(X_list)
            del X_list
        else:
            for r in store.iter_runs(test):
                scores.append(model.score(r.X[:, cols]).astype(np.float32))
                r.X = None
                runs.append(r)
        seed_out = {"cost": model.cost([bits_of(i) for i in cols]), "features": [names[i] for i in cols]}
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
            log(f"seed {seed} {opname}: SzCORE sens {m['sensitivity']:.3f} prec {m['precision']:.3f} "
                  f"F1 {m['f1']:.3f} FP/24h {m['fp_per_24h']:.1f}")
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
    log(json.dumps(summary, indent=1))
    mark_complete(run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
