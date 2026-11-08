"""Turn out-of-fold scores into a finished inner-CV run (shared by scripts/run_inner_cv.py and
scripts/run_inner_cv_raw.py): operating points chosen on the pooled out-of-fold predictions
(Section 6.5), per-fold metrics for paired tests, metrics.json, sweep.csv and the RESULT log line."""
from __future__ import annotations

import csv
import json

import numpy as np

from .operating import choose, subject_metrics, sweep
from .runlog import mark_complete


def finalize(oof, cfg, seed, fold_ids, folds, n_features, fold_info, costs, run, log) -> dict:
    post = cfg.get("post", {})
    rows = sweep(oof, ks=post.get("k", (6, 8, 10)), gates=post.get("gate", ("none", "both", "any")),
                 n_thresholds=post.get("n_thresholds", 40))
    ops = choose(rows)
    # per-fold metrics at the chosen operating points (for paired tests across methods)
    out_ops = {}
    for name, op in ops.items():
        if op is None:
            out_ops[name] = None
            continue
        per_fold = {}
        for k in fold_ids:
            subs = {s for s, f in folds.items() if f == k}
            per_fold[k] = subject_metrics({s: v for s, v in op["per_subject"].items() if s in subs})
        out_ops[name] = {kk: v for kk, v in op.items() if kk != "per_subject"} | {
            "per_fold": per_fold, "per_subject": op["per_subject"]}
    from sklearn.metrics import average_precision_score, roc_auc_score
    ally = np.concatenate([o["y"] for o in oof])
    alls = np.concatenate([o["score"] for o in oof])
    metrics = {"name": cfg["name"], "seed": seed, "folds": fold_ids, "n_features": n_features,
               "window_auroc": float(roc_auc_score(ally, alls)), "window_aupr": float(average_precision_score(ally, alls)),
               "operating_points": out_ops, "fold_info": fold_info,
               "cost_median": {kk: float(np.median([c[kk] for c in costs])) for kk in costs[0]} if costs and costs[0] else {}}
    (run / "metrics.json").write_text(json.dumps(metrics, indent=1) + "\n")
    mark_complete(run)
    with open(run / "sweep.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=[kk for kk in rows[0] if kk != "per_subject"])
        w.writeheader()
        for r in rows:
            w.writerow({kk: v for kk, v in r.items() if kk != "per_subject"})
    b, s = out_ops["best_f1"], out_ops["sens_at_1fah"]
    log(f"RESULT {cfg['name']}: window AUROC {metrics['window_auroc']:.3f} AUPR {metrics['window_aupr']:.3f} | "
        f"best-F1 op (gate {b['gate']}, k {b['k']}): F1 {b['f1']:.3f} sens {b['sensitivity']:.3f} "
        f"prec {b['precision']:.3f} FP/24h {b['fp_per_24h']:.1f}" +
        (f" | sens@<=1FA/h {s['sensitivity']:.3f} (FP/24h {s['fp_per_24h']:.1f})" if s else ""))
    return metrics
