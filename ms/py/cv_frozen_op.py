#!/usr/bin/env python3
"""Out-of-fold metrics of retrained inner-CV runs at the FROZEN operating point (no gate, 10 of 10, score >= 9),
over all 96 training patients; and the run-to-run spread across seeds that MS_SPEC.md D-MS10 needs.

Each run directory is one `scripts/run_inner_cv.py --config configs/m5/n4_distill.yaml --seed S --out <dir>` run;
its out-of-fold scores are in <out>/cache/oof/<run name>/<subject>_<run>.npy.

Usage: python ms/py/cv_frozen_op.py <out dir> [<out dir> ...]  -> prints a table, writes
       ms/results/phase1/cv_frozen_op.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from seizelut.data.featureset import FeatureStore   # noqa: E402
from seizelut.data.split import load_folds          # noqa: E402
from seizelut.eval.operating import sweep           # noqa: E402

HEAD = json.loads((REPO / "export/n4_distill_s0/head.json").read_text())


def frozen_metrics(oof_dir: Path, store: FeatureStore, subjects: list[str]) -> dict:
    runs = []
    for k in store.runs_of(subjects):
        d = np.load(store.files[k])
        runs.append({"subject": k.split("_")[0], "score": np.load(oof_dir / f"{k}.npy"),
                     "artefact": d["artefact"].astype(bool), "seizures": d["seizures"],
                     "duration_s": float(d["duration_s"])})
    row = sweep(runs, ks=(HEAD["k"],), gates=(HEAD["artefact_gate"],),
                thresholds=[float(HEAD["decision_threshold"])])[0]
    per_f1 = {}
    for s, (tp, fp, nref, h) in row["per_subject"].items():
        if nref:
            se, pr = tp / nref, (tp / (tp + fp) if tp + fp else 0.0)
            per_f1[s] = 2 * se * pr / (se + pr) if se + pr else 0.0
    return {k: v for k, v in row.items()} | {"per_subject_f1": per_f1}


def main() -> int:
    outs = [Path(p) for p in sys.argv[1:]]
    subjects = sorted(load_folds(REPO / "configs/folds_inner5.json"))
    store = FeatureStore("int")
    res = {}
    for o in outs:
        for run in sorted((o / "results/runs").glob("*")):
            oof = o / "cache/oof" / run.name
            if not (run / "metrics.json").exists():
                print(f"skip unfinished {run}")
                continue
            seed = json.loads((run / "run.json").read_text())["seed"]
            m = frozen_metrics(oof, store, subjects)
            res[run.name] = {"seed": seed, **{k: m[k] for k in ("f1", "sensitivity", "precision", "fp_per_24h",
                                                                   "pooled_f1", "pooled_fp_per_24h")},
                             "per_subject": m["per_subject"], "per_subject_f1": m["per_subject_f1"]}
            print(f"{run.name}: seed {seed} F1 {m['f1']:.4f} sens {m['sensitivity']:.4f} prec {m['precision']:.4f} "
                  f"FP/24h {m['fp_per_24h']:.3f}")
    if len(res) > 1:
        f1 = np.array([r["f1"] for r in res.values()])
        fp = np.array([r["fp_per_24h"] for r in res.values()])
        summ = {"n_seeds": len(res), "f1_mean": float(f1.mean()), "f1_std": float(f1.std(ddof=1)),
                "fp24_mean": float(fp.mean()), "fp24_std": float(fp.std(ddof=1)),
                "delta_f1": float(max(f1.std(ddof=1), 0.005)), "delta_fp24": float(max(fp.std(ddof=1), 0.1))}
        res["summary"] = summ
        print(json.dumps(summ, indent=1))
    p = REPO / "ms/results/phase1/cv_frozen_op.json"
    p.write_text(json.dumps(res, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
