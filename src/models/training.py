"""Training of one config on a set of patients, shared by the inner folds (scripts/run_inner_cv.py) and
the final models (scripts/run_final.py), so the final retraining on all 96 patients is exactly the
procedure that was compared on the inner folds (Section 7.1).

fit_config() does, in order: training windows (all seizure windows + bg_ratio x background), feature
selection (fixed list, prefixes, ranking file, or mutual information on the training windows only,
plus `always` columns), the model's seed, modality dropout (N6), the teacher (N4: distillation and/or
teacher-guided hard negatives), the N5 onset and seizure-bag labels, and one hard-negative round.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from ..features import spec as S
from .registry import build

REPO = Path(__file__).resolve().parents[2]
MODALITY_PREFIX = {"ecg": ("ecg_", "present_ecg"), "emg": ("emg_", "present_emg"),
                   "mov": ("mov_", "present_mov_acc", "present_mov_gyr")}
DWN_LIKE = ("dwn", "dwn_late")


def set_device(cfg: dict, device: str | None) -> None:
    """Override the model's torch device, for models that take one (sequence models train on the CPU)."""
    if not device:
        return
    import inspect
    from .registry import REGISTRY
    sig = inspect.signature(REGISTRY[cfg["model"]["type"]].__init__).parameters
    if "device" in sig or any(v.kind == v.VAR_KEYWORD for v in sig.values()):
        cfg["model"].setdefault("params", {})["device"] = device


def feature_names(stack: int) -> list[str]:
    return S.FEATURES if stack == 1 else [f"{n}@t-{j}" for j in range(stack - 1, -1, -1) for n in S.FEATURES]


def bits_of(i: int) -> int:
    return S.FEATURE_BITS[S.FEATURES[i % len(S.FEATURES)]]


def select_features(spec, names):
    """Candidate columns of a feature spec (mutual-information specs are narrowed per training set)."""
    if spec in (None, "all"):
        return list(range(len(names)))
    if isinstance(spec, dict) and "exclude_prefix" in spec:
        return [i for i, n in enumerate(names) if not n.startswith(tuple(spec["exclude_prefix"]))]
    if isinstance(spec, dict) and "include_prefix" in spec:
        return [i for i, n in enumerate(names) if n.startswith(tuple(spec["include_prefix"]))]
    if isinstance(spec, dict) and ("mi_top" in spec or spec.get("rank_by")):
        return list(range(len(names)))          # selected per training set by rank_select()
    if isinstance(spec, dict) and "ranking" in spec:
        order = json.loads((REPO / spec["ranking"]).read_text())["order"]
        return sorted(names.index(n) for n in order[: spec["top"]])
    return [names.index(n) for n in spec]


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
    """Section 5.2: rank by mutual information on the training windows only (200k-row sample)."""
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


def lgbm_select(fspec, X, y, cols, names, seed, log):
    """Rank by the gain importance of a LightGBM trained on the training windows only (200k-row sample).
    Unlike one-feature-at-a-time mutual information, it credits features that matter in combination
    (e.g. heart rate relative to the rest)."""
    import lightgbm as lgb
    rs = np.random.default_rng(seed)
    sub = rs.choice(len(y), size=min(len(y), 200_000), replace=False)
    m = lgb.LGBMClassifier(n_estimators=200, num_leaves=31, learning_rate=0.05, subsample=0.8, subsample_freq=1,
                           colsample_bytree=0.8, min_child_samples=50, importance_type="gain", random_state=seed,
                           n_jobs=4, verbose=-1)
    m.fit(X[sub][:, cols].astype(np.float32), y[sub])
    order = np.argsort(-m.feature_importances_, kind="stable")
    fcols = [cols[i] for i in order[: fspec["top"]]]
    log(f"  LightGBM-gain top {fspec['top']}: {[names[i] for i in fcols[:10]]} ...")
    return fcols


def rank_select(fspec, X, y, cols, names, stack, seed, log):
    """Per-training-set feature selection: mutual information (mi_top) or LightGBM gain (rank_by: lgbm, top)."""
    if fspec.get("rank_by") == "lgbm":
        return lgbm_select(fspec, X, y, cols, names, seed, log)
    return mi_select(fspec, X, y, cols, names, stack, seed, log)


def fit_config(cfg, store, subjects, seed, log, ckpt=None, seed_all_models=False):
    """Train `cfg` on `subjects`. Returns (model, columns, number of training windows or None).

    seed: the training-set draw, feature selection and model seed (the inner folds pass seed + fold).
    seed_all_models: also set the seed of non-DWN trainable models (final runs: five distinct seeds).
    """
    tc = cfg.get("train", {})
    names = feature_names(store.stack)
    cols = select_features(cfg.get("features", "all"), names)
    fspec = cfg.get("features")
    model = build(cfg["model"], log=log)

    def seed_model(m):
        if cfg["model"]["type"] in DWN_LIKE or (seed_all_models and isinstance(getattr(m, "p", None), dict)
                                                and "seed" in m.p):
            m.p["seed"] = seed

    if getattr(model, "needs_store", False):
        # sequence models (N1, GRU) sample their own training sequences from the store
        model.ckpt_path = ckpt
        scols = cols
        if isinstance(fspec, dict) and ("mi_top" in fspec or fspec.get("rank_by")):
            Xm, ym, _, _, _ = store.training_set(subjects, tc.get("bg_ratio", 20), seed=seed, max_bg=tc.get("max_bg"))
            scols = rank_select(fspec, Xm, ym, cols, names, store.stack, seed, log)
            del Xm, ym
        model.fit_store(store, subjects, scols, seed)
        return model, scols, None

    X, y, _, _, _ = store.training_set(subjects, tc.get("bg_ratio", 20), seed=seed, max_bg=tc.get("max_bg"))
    log(f"  training windows: {len(y)} ({int(y.sum())} seizure)")
    fcols = cols
    if isinstance(fspec, dict) and ("mi_top" in fspec or fspec.get("rank_by")):
        fcols = rank_select(fspec, X, y, cols, names, store.stack, seed, log)
    if isinstance(fspec, dict) and fspec.get("always"):
        # N6 gated fusion: quality and presence bits are always inputs, whatever their MI rank
        fcols = list(fcols) + [names.index(n) for n in fspec["always"] if names.index(n) not in fcols]
    hn = tc.get("hard_negative")
    model.ckpt_path = None if hn else ckpt          # hard-negative mining retrains a second model
    seed_model(model)
    if tc.get("modality_dropout"):
        X = modality_dropout(X, tc["modality_dropout"], np.random.default_rng(seed + 100))
    fit_kw, teacher = {}, None
    if tc.get("distill") or (hn and hn.get("by") == "teacher"):
        # N4: the teacher (a Tier-1 model) is trained on the same training windows
        tspec = (tc.get("distill") or hn)["teacher"]
        teacher = build(tspec, log=log)
        teacher.fit(X[:, fcols], y)
        log(f"  teacher {tspec['type']} trained")
    dwn_like = cfg["model"]["type"] in DWN_LIKE
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
        for r in store.iter_runs(subjects):
            bg = np.flatnonzero(r.y == 0)
            if len(bg):
                s = miner.score(r.X[bg][:, fcols])
                cand.append((r.subject + "_" + r.run, bg, s))
        alls = np.concatenate([c[2] for c in cand])
        cut = np.quantile(alls, 1 - hn.get("top_fraction", 0.001))
        extra = {key: bg[s >= cut] for key, bg, s in cand if (s >= cut).any()}
        X, y, _, _, _ = store.training_set(subjects, tc.get("bg_ratio", 20), seed=seed, max_bg=tc.get("max_bg"),
                                           extra_bg=extra)
        log(f"  hard negatives: +{sum(len(v) for v in extra.values())} windows, retraining on {len(y)}")
        if tc.get("modality_dropout"):
            X = modality_dropout(X, tc["modality_dropout"], np.random.default_rng(seed + 200))
        model = build(cfg["model"], log=log)
        seed_model(model)
        if dwn_like:
            fit_kw = {"onset": store.last_onset, "bags": store.last_bags}
        model.fit(X[:, fcols], y, **fit_kw)
    return model, fcols, int(len(y))
