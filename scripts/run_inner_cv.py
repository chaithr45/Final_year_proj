#!/usr/bin/env python3
"""5-fold patient-wise inner cross-validation inside the 96 training patients (Section 7.1).

For each fold: train on the other four folds (all seizure windows + background at the
configured ratio, optional hard-negative round), score every window of the held-out
patients. Then choose the artefact gate, k and threshold on the pooled out-of-fold
predictions and report SzCORE event metrics per fold and per subject. Never touches the
test patients.

Usage:  python scripts/run_inner_cv.py --config configs/m4/lgbm.yaml [--folds 0 1] [--seed 0]
Output: results/runs/<id>/{config.yaml, run.json, metrics.json, sweep.csv, log.txt}
        cache/oof/<id>/<run>.npy (out-of-fold scores)
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import yaml

from seizelut.data.featureset import FeatureStore
from seizelut.data.split import load_folds
from seizelut.eval.innercv import finalize
from seizelut.eval.runlog import new_run_dir
from seizelut.features import spec as S
from seizelut.models.training import bits_of, feature_names, fit_config, select_features

REPO = Path(__file__).resolve().parents[1]


def _save_model(model, run, fold, cols, out=REPO):
    """Keep each fold's fitted model (checkpoints/, not committed) for post-hoc studies (N3, N7)."""
    import pickle
    d = out / "checkpoints" / run.name
    d.mkdir(parents=True, exist_ok=True)
    log_fn = getattr(model, "log", None)
    if log_fn is not None:
        model.log = None
    with open(d / f"fold_{fold}.pkl", "wb") as fh:
        pickle.dump({"model": model, "cols": cols, "features": [S.FEATURES[i % len(S.FEATURES)] for i in cols]}, fh)
    if log_fn is not None:
        model.log = log_fn


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", required=True)
    ap.add_argument("--folds", nargs="*", type=int, default=None)
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--mode", default="int", help="feature cache: int (golden) or float (twin)")
    ap.add_argument("--device", default=None, help="override the model's torch device (e.g. cuda)")
    ap.add_argument("--resume", default=None,
                    help="unfinished run directory to continue: folds whose out-of-fold scores were fully "
                         "written are reloaded instead of retrained (same config required)")
    ap.add_argument("--folds-file", default=str(REPO / "configs/folds_inner5.json"),
                    help="patient->fold map (default: the fixed inner folds); smaller maps for dry runs")
    ap.add_argument("--out", default=None, help="write runs/, oof scores and checkpoints under this directory "
                                                "instead of the repository (tests)")
    ap.add_argument("--features-root", default=None, help="feature cache root (default cache/features; tests)")
    args = ap.parse_args()
    out = Path(args.out).resolve() if args.out else REPO
    cfg = yaml.safe_load(Path(args.config).read_text())
    if args.device:
        cfg["model"].setdefault("params", {})["device"] = args.device
    seed = args.seed if args.seed is not None else cfg.get("seed", 0)
    folds = load_folds(args.folds_file)
    fold_ids = args.folds if args.folds is not None else sorted(set(folds.values()))
    store = FeatureStore(args.mode, root=Path(args.features_root) if args.features_root else None)
    missing = store.missing(sorted(folds))
    if missing:
        raise SystemExit(f"feature cache incomplete for {len(missing)} training patients, e.g. {missing[:5]}")
    store.stack = int(cfg.get("stack", 1))
    names = feature_names(store.stack)
    cols = select_features(cfg.get("features", "all"), names)
    run_cfg = {**cfg, "folds_run": fold_ids, "feature_mode": args.mode,
               "folds_file": str(Path(args.folds_file).name)}
    if args.resume:
        run = Path(args.resume).resolve()
        if not (run / ".gitignore").exists():
            raise SystemExit(f"{run} is not an unfinished run")
        if yaml.safe_load((run / "config.yaml").read_text()) != yaml.safe_load(yaml.safe_dump(run_cfg, sort_keys=False)):
            raise SystemExit(f"config of {run} differs from {args.config}; start a new run instead")
        if json.loads((run / "run.json").read_text())["seed"] != seed:
            raise SystemExit("seed differs from the unfinished run")
    else:
        run = new_run_dir(cfg["name"], run_cfg, seed, root=(out / "results" / "runs") if args.out else None)
    logf = open(run / "log.txt", "a")

    def log(msg):
        print(msg, flush=True)
        logf.write(msg + "\n")
        logf.flush()

    oof_dir = out / "cache" / "oof" / run.name
    oof_dir.mkdir(parents=True, exist_ok=True)
    oof, costs, fold_info = [], [], []
    for k in fold_ids:
        tr = sorted(s for s, f in folds.items() if f != k)
        va = sorted(s for s, f in folds.items() if f == k)
        t0 = time.time()
        done_f = oof_dir / f"_fold_{k}.json"
        if done_f.exists():
            # resumed run: this fold finished before the interruption; reload its scores
            info = json.loads(done_f.read_text())
            for r in store.iter_runs(va):
                s = np.load(oof_dir / f"{r.subject}_{r.run}.npy")
                oof.append({"subject": r.subject, "fold": k, "score": s, "artefact": r.artefact,
                            "seizures": r.seizures, "duration_s": r.duration_s, "y": r.y})
            costs.append(info["cost"])
            fold_info.append(info)
            log(f"fold {k}: reloaded from the interrupted run ({info['val_windows']} val windows)")
            continue
        ckpt = oof_dir / f"_fold_{k}_train.pt"     # per-epoch training state (deleted when the fold is done)
        log(f"fold {k}: train {len(tr)} patients; val {len(va)} patients")
        model, fcols, n_train = fit_config(cfg, store, tr, seed + k, log, ckpt=ckpt)
        n_win = 0
        if getattr(model, "needs_store", False):
            runs_va, X_va = [], []
            for r in store.iter_runs(va):        # keep only the model's columns of each validation run
                X_va.append(np.ascontiguousarray(r.X[:, fcols]))
                r.X = None
                runs_va.append(r)
            scored = zip(runs_va, model.score_runs(X_va))
            del X_va
        else:
            scored = ((r, model.score(r.X[:, fcols]).astype(np.float32)) for r in store.iter_runs(va))
        for r, s in scored:
            np.save(oof_dir / f"{r.subject}_{r.run}.npy", s)
            oof.append({"subject": r.subject, "fold": k, "score": s, "artefact": r.artefact,
                        "seizures": r.seizures, "duration_s": r.duration_s, "y": r.y})
            r.X = None
            n_win += len(s)
        c = model.cost([bits_of(i) for i in fcols])
        costs.append(c)
        _save_model(model, run, k, fcols, out)
        fold_info.append({"fold": k, **({"train_windows": n_train} if n_train is not None else {}),
                          "val_windows": n_win, "features": [names[i] for i in fcols],
                          "seconds": round(time.time() - t0, 1), "cost": c})
        log(f"  fold {k} done in {time.time() - t0:.0f} s; estimated cost {c}")
        done_f.write_text(json.dumps(fold_info[-1], default=float))
        ckpt.unlink(missing_ok=True)

    finalize(oof, cfg, seed, fold_ids, folds, len(cols), fold_info, costs, run, log)
    log(f"run dir: {run}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
