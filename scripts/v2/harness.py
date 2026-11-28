#!/usr/bin/env python3
"""v2 experiment harness: score any per-window out-of-fold (OOF) score set on the 96 training patients.

Two metric families, both on the training folds only:
  * paper metric (as the SeizeIT2 paper and scripts/run_final.py): any-overlap sensitivity, mean over recordings with
    a seizure, and false-alarm events per hour, mean over recordings;
  * SzCORE event metrics (mean over patients): event-F1, sensitivity, false alarms per 24 h.

The alarm rule is v1's: alarm when at least k of the last 10 per-second scores are >= threshold.

Usage (library):  meta = load_meta(); sc = load_oof(run, meta); rep = evaluate(sc, meta)
CLI:              python scripts/v2/harness.py <run> [<run> ...]   (prints one summary line per run)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))

from seizelut.data.featureset import FeatureStore          # noqa: E402
from seizelut.data.split import official_train_subjects    # noqa: E402
from seizelut.eval.operating import kth_of_last, sweep, subject_metrics  # noqa: E402
from paper_point_cv import fast_ovlp                       # noqa: E402

META = REPO / "cache" / "v2" / "meta.npz"
FOLDS = REPO / "configs" / "folds_inner5.json"
BUDGETS_FAH = (0.1, 0.5, 1.0, 2.0, 5.0, 10.0)


def folds() -> dict:
    d = json.loads(FOLDS.read_text())
    if "folds" in d and isinstance(d["folds"], dict):
        d = d["folds"]
    out = {}
    for k, v in d.items():
        if isinstance(v, list):
            for s in v:
                out[s] = int(k)
        else:
            out[k] = int(v)
    return out


def load_meta() -> list[dict]:
    """Per training recording: key, subject, fold, y, artefact, present, seizures, duration_s (cached)."""
    store = FeatureStore("int")
    keys = store.runs_of(official_train_subjects())
    fo = folds()
    if META.exists():
        z = np.load(META, allow_pickle=True)
        meta = list(z["meta"])
        if [m["key"] for m in meta] == keys:
            return meta
    meta = []
    for k in keys:
        with np.load(store.files[k]) as d:
            sub = k.split("_")[0]
            meta.append({"key": k, "subject": sub, "fold": fo[sub], "y": d["y"].astype(np.int8),
                         "artefact": d["artefact"].astype(bool), "present": d["present"].astype(bool),
                         "seizures": d["seizures"], "duration_s": float(d["duration_s"])})
    META.parent.mkdir(parents=True, exist_ok=True)
    np.savez(META, meta=np.array(meta, dtype=object))
    return meta


def load_oof(run: str, meta: list[dict]) -> list[np.ndarray]:
    d = REPO / "cache" / "oof" / run
    return [np.load(d / f"{m['key']}.npy").astype(np.float64) for m in meta]


def _thresholds(sc, n=60):
    alls = np.concatenate(sc)
    alls = alls[np.isfinite(alls)]
    qs = 1 - np.logspace(-5, np.log10(0.3), n)
    return np.unique(np.quantile(alls, qs))


def paper_curve(sc, meta, k=10, n=60, ths=None):
    """Rows (threshold, FA/h, sensitivity, fraction of time in alarm) for the paper metric."""
    ths = _thresholds(sc, n) if ths is None else ths
    fa = np.zeros(len(ths)); se = np.zeros(len(ths)); on = np.zeros(len(ths)); nsz = 0; tot = 0
    for m, s in zip(meta, sc):
        q = kth_of_last(s, k)
        y = m["y"].astype(bool)
        has = bool(y.any()); nsz += has; tot += len(q)
        for i, th in enumerate(ths):
            a = q >= th
            tp, fp, fn = fast_ovlp(y, a)
            fa[i] += fp * 3600 / len(q); on[i] += a.sum()
            if has:
                se[i] += tp / (tp + fn)
    return [(float(t), float(f / len(meta)), float(x / nsz), float(o / tot)) for t, f, x, o in zip(ths, fa, se, on)]


def sens_at(curve, budget, max_on=0.05):
    ok = [r for r in curve if r[1] <= budget and r[3] <= max_on]
    return max(ok, key=lambda r: (r[2], -r[1])) if ok else None


def szcore(sc, meta, ks=(10,), n=40):
    runs = [{"subject": m["subject"], "score": s, "artefact": m["artefact"], "seizures": m["seizures"],
             "duration_s": m["duration_s"]} for m, s in zip(meta, sc)]
    rows = sweep(runs, ks=ks, gates=("none",), n_thresholds=n)
    best = max(rows, key=lambda r: (r["f1"], -r["fp_per_24h"]))
    s1 = [r for r in rows if r["fp_per_24h"] <= 24]
    return best, (max(s1, key=lambda r: r["sensitivity"]) if s1 else None), rows


def window_auc(sc, meta):
    from sklearn.metrics import roc_auc_score
    y = np.concatenate([m["y"] for m in meta]); s = np.concatenate(sc)
    ok = np.isfinite(s)
    return float(roc_auc_score(y[ok], s[ok]))


def evaluate(sc, meta, ks=(1, 4, 10), with_szcore=True) -> dict:
    rep = {"auroc": window_auc(sc, meta), "paper": {}}
    for k in ks:
        cur = paper_curve(sc, meta, k=k)
        rep["paper"][k] = {str(b): sens_at(cur, b) for b in BUDGETS_FAH}
    best_by_budget = {}
    for b in BUDGETS_FAH:
        cands = [(k, rep["paper"][k][str(b)]) for k in ks if rep["paper"][k][str(b)]]
        if cands:
            k, r = max(cands, key=lambda c: c[1][2])
            best_by_budget[str(b)] = {"k": k, "th": r[0], "fa_h": r[1], "sens": r[2]}
    rep["paper_best"] = best_by_budget
    if with_szcore:
        best, s1, _ = szcore(sc, meta)
        rep["szcore_best_f1"] = {kk: best[kk] for kk in ("k", "threshold", "f1", "sensitivity", "precision", "fp_per_24h")}
        rep["szcore_sens_1fah"] = ({kk: s1[kk] for kk in ("k", "threshold", "f1", "sensitivity", "fp_per_24h")}
                                   if s1 else None)
    return rep


def line(name, rep) -> str:
    pb = rep["paper_best"]
    parts = [f"{name}: AUROC {rep['auroc']:.3f}"]
    if "szcore_best_f1" in rep:
        b = rep["szcore_best_f1"]
        parts.append(f"F1 {b['f1']:.3f} (sens {b['sensitivity']:.3f}, FP/24h {b['fp_per_24h']:.1f})")
    parts.append("paper sens@FA/h " + " ".join(f"{b}:{pb[b]['sens']:.3f}" if b in pb else f"{b}:-" for b in
                                                map(str, BUDGETS_FAH)))
    return " | ".join(parts)


if __name__ == "__main__":
    meta = load_meta()
    out = REPO / "results" / "v2" / "harness.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    res = json.loads(out.read_text()) if out.exists() else {}
    for run in sys.argv[1:]:
        rep = evaluate(load_oof(run, meta), meta)
        res[run] = rep
        print(line(run, rep), flush=True)
        out.write_text(json.dumps(res, indent=1))
