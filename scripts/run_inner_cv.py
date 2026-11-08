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
import csv
import json
import sys
import time
from pathlib import Path

import numpy as np
import yaml

from seizelut.data.featureset import FeatureStore
from seizelut.data.split import load_folds
from seizelut.eval.operating import choose, sweep, subject_metrics
from seizelut.eval.runlog import mark_complete, new_run_dir
from seizelut.features import spec as S
from seizelut.models.registry import build

REPO = Path(__file__).resolve().parents[1]


def select_features(spec, names):
    if spec in (None, "all"):
        return list(range(len(names)))
    if isinstance(spec, dict) and "exclude_prefix" in spec:
        return [i for i, n in enumerate(names) if not n.startswith(tuple(spec["exclude_prefix"]))]
    if isinstance(spec, dict) and "include_prefix" in spec:
        return [i for i, n in enumerate(names) if n.startswith(tuple(spec["include_prefix"]))]
    if isinstance(spec, dict) and "mi_top" in spec:
        return list(range(len(names)))          # selected per fold inside the CV loop
    if isinstance(spec, dict) and "ranking" in spec:
        order = json.loads((REPO / spec["ranking"]).read_text())["order"]
        return sorted(names.index(n) for n in order[: spec["top"]])
    return [names.index(n) for n in spec]


MODALITY_PREFIX = {"ecg": ("ecg_", "present_ecg"), "emg": ("emg_", "present_emg"),
                   "mov": ("mov_", "present_mov_acc", "present_mov_gyr")}


def modality_dropout(X, p, rng):
    """N6: for each training row, drop ECG, EMG and motion independently with probability p
    (features and present bits set to 0, exactly as when the modality is missing)."""
    X = X.copy()
    for prefixes in MODALITY_PREFIX.values():
        cols = [i for i, n in enumerate(S.FEATURES) if n.startswith(prefixes)]
        rows = rng.random(len(X)) < p
        X[np.ix_(rows, cols)] = 0
    return X


def mi_select(fspec, X, y, cols, names, stack, seed, log):
    """Section 5.2: rank by mutual information on the training folds only (200k-row sample)."""
    from sklearn.feature_selection import mutual_info_classif
    rs = np.random.default_rng(seed)
    sub = rs.choice(len(y), size=min(len(y), 200_000), replace=False)
    if fspec.get("mi_on") == "base" and stack > 1:
        # rank the base features on the current window (t-0 block) only, then keep every lag of
        # the winners: ranking the stacked columns picks lagged copies of a few features (D31)
        nF = len(S.FEATURES)
        cur = list(range((stack - 1) * nF, stack * nF))
        mi = mutual_info_classif(X[sub][:, cur].astype(np.float32), y[sub], random_state=seed)
        top = sorted(np.argsort(-mi)[: fspec["mi_top"]].tolist(), key=lambda i: -mi[i])
        fcols = [b * nF + i for i in top for b in range(stack)]
    else:
        mi = mutual_info_classif(X[sub][:, cols].astype(np.float32), y[sub], random_state=seed)
        fcols = [cols[i] for i in np.argsort(-mi)[: fspec["mi_top"]]]
    log(f"  MI top {fspec['mi_top']}: {[names[i] for i in fcols[:10]]} ...")
    return fcols


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
    names = S.FEATURES if store.stack == 1 else [f"{n}@t-{j}" for j in range(store.stack - 1, -1, -1) for n in S.FEATURES]
    cols = select_features(cfg.get("features", "all"), names)
    bits_of = lambda i: S.FEATURE_BITS[S.FEATURES[i % len(S.FEATURES)]]
    feat_bits = [bits_of(i) for i in cols]
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
    tc = cfg.get("train", {})
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
        spec_model = build(cfg["model"], log=log)
        spec_model.ckpt_path = ckpt
        if getattr(spec_model, "needs_store", False):
            # sequence models (N1): sample their own training sequences from the store
            log(f"fold {k}: train {len(tr)} patients (sequence model); val {len(va)} patients")
            scols = cols
            fspec = cfg.get("features")
            if isinstance(fspec, dict) and "mi_top" in fspec:
                # same per-fold selection as the window models (sequence models used every column before)
                Xm, ym, _, _, _ = store.training_set(tr, tc.get("bg_ratio", 20), seed=seed + k, max_bg=tc.get("max_bg"))
                scols = mi_select(fspec, Xm, ym, cols, names, store.stack, seed + k, log)
                del Xm, ym
            spec_model.fit_store(store, tr, scols, seed + k)
            runs_va, X_va = [], []
            for r in store.iter_runs(va):        # keep only the model's columns of each validation run
                X_va.append(np.ascontiguousarray(r.X[:, scols]))
                r.X = None
                runs_va.append(r)
            scores = spec_model.score_runs(X_va)
            del X_va
            n_win = 0
            for r, s in zip(runs_va, scores):
                np.save(oof_dir / f"{r.subject}_{r.run}.npy", s)
                oof.append({"subject": r.subject, "fold": k, "score": s, "artefact": r.artefact,
                            "seizures": r.seizures, "duration_s": r.duration_s, "y": r.y})
                n_win += len(s)
            c = spec_model.cost([bits_of(i) for i in scols])
            costs.append(c)
            _save_model(spec_model, run, k, scols, out)
            fold_info.append({"fold": k, "val_windows": n_win, "features": [names[i] for i in scols],
                              "seconds": round(time.time() - t0, 1), "cost": c})
            log(f"  fold {k} done in {time.time() - t0:.0f} s; estimated cost {c}")
            done_f.write_text(json.dumps(fold_info[-1], default=float))
            ckpt.unlink(missing_ok=True)
            continue
        X, y, _, _, keys = store.training_set(tr, tc.get("bg_ratio", 20), seed=seed + k, max_bg=tc.get("max_bg"))
        log(f"fold {k}: train {len(tr)} patients, {len(y)} windows ({int(y.sum())} seizure); val {len(va)} patients")
        fcols = cols
        fspec = cfg.get("features")
        if isinstance(fspec, dict) and "mi_top" in fspec:
            fcols = mi_select(fspec, X, y, cols, names, store.stack, seed + k, log)
        if isinstance(fspec, dict) and fspec.get("always"):
            # N6 gated fusion: quality and presence bits are always inputs, whatever their MI rank
            fcols = list(fcols) + [names.index(n) for n in fspec["always"] if names.index(n) not in fcols]
        fold_bits = [bits_of(i) for i in fcols]
        model = build(cfg["model"], log=log)
        model.ckpt_path = None if tc.get("hard_negative") else ckpt   # hard-negative retrains a second model
        dwn_like = cfg["model"]["type"] in ("dwn", "dwn_late")
        if dwn_like:
            model.p["seed"] = seed + k
        if tc.get("modality_dropout"):
            X = modality_dropout(X, tc["modality_dropout"], np.random.default_rng(seed + 100 + k))
        fit_kw = {}
        hn = tc.get("hard_negative")
        teacher = None
        if tc.get("distill") or (hn and hn.get("by") == "teacher"):
            # N4: the teacher (a Tier-1 model) is trained on the same fold's training windows
            tspec = (tc.get("distill") or hn)["teacher"]
            teacher = build(tspec, log=log)
            teacher.fit(X[:, fcols], y)
            log(f"  teacher {tspec['type']} trained")
        if dwn_like:
            fit_kw = {"onset": store.last_onset, "bags": store.last_bags}
            if tc.get("distill"):
                fit_kw["soft"] = teacher.score(X[:, fcols])        # in-sample soft targets (probabilities)
        model.fit(X[:, fcols], y, **fit_kw)
        if hn:
            # one round: score all training background, add the highest-scoring false positives
            # (scored by the model itself, or by the teacher for teacher-guided mining, N4)
            miner = teacher if hn.get("by") == "teacher" else model
            cand = []
            for r in store.iter_runs(tr):
                bg = np.flatnonzero(r.y == 0)
                if len(bg):
                    s = miner.score(r.X[bg][:, fcols])
                    cand.append((r.subject + "_" + r.run, bg, s))
            alls = np.concatenate([c[2] for c in cand])
            cut = np.quantile(alls, 1 - hn.get("top_fraction", 0.001))
            extra = {key: bg[s >= cut] for key, bg, s in cand if (s >= cut).any()}
            X, y, _, _, _ = store.training_set(tr, tc.get("bg_ratio", 20), seed=seed + k, max_bg=tc.get("max_bg"),
                                               extra_bg=extra)
            log(f"  hard negatives: +{sum(len(v) for v in extra.values())} windows, retraining on {len(y)}")
            if tc.get("modality_dropout"):
                X = modality_dropout(X, tc["modality_dropout"], np.random.default_rng(seed + 200 + k))
            model = build(cfg["model"], log=log)
            if dwn_like:
                model.p["seed"] = seed + k
                fit_kw = {"onset": store.last_onset, "bags": store.last_bags}
            model.fit(X[:, fcols], y, **fit_kw)
        del X
        n_win = 0
        for r in store.iter_runs(va):
            s = model.score(r.X[:, fcols]).astype(np.float32)
            np.save(oof_dir / f"{r.subject}_{r.run}.npy", s)
            oof.append({"subject": r.subject, "fold": k, "score": s, "artefact": r.artefact,
                        "seizures": r.seizures, "duration_s": r.duration_s, "y": r.y})
            n_win += len(s)
        c = model.cost(fold_bits)
        costs.append(c)
        _save_model(model, run, k, fcols, out)
        fold_info.append({"fold": k, "train_windows": int(len(y)), "val_windows": n_win,
                          "features": [names[i] for i in fcols],
                          "seconds": round(time.time() - t0, 1), "cost": c})
        log(f"  fold {k} done in {time.time() - t0:.0f} s; estimated cost {c}")
        done_f.write_text(json.dumps(fold_info[-1], default=float))
        ckpt.unlink(missing_ok=True)

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
    metrics = {"name": cfg["name"], "seed": seed, "folds": fold_ids, "n_features": len(cols),
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
    log(f"run dir: {run}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
