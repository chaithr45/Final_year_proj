"""Threshold / k / artefact-gate selection on out-of-fold predictions (Section 6.5).

"Alarm when at least k of the last 10 decisions (score >= th, gate clear) are positive" is
equivalent to "the k-th largest gated score of the last 10 s is >= th", so every threshold
of a sweep costs one comparison per second. Events are scored with the fast SzCORE scorer
(identical to timescoring); per-subject metrics are averaged over subjects.

Two operating points are reported (both chosen on training folds only):
  * best_f1: maximum mean event-F1;
  * sens_at_1fah: maximum mean sensitivity with mean false alarms <= 24 per 24 h (1 per hour).
"""
from __future__ import annotations

from collections import defaultdict

import numpy as np

from .events import mask_to_events
from .fastscore import prepare_ref, score_events

GATES = ("none", "both", "any")


def gate_mask(artefact: np.ndarray, gate: str) -> np.ndarray:
    if gate == "none":
        return np.zeros(len(artefact), dtype=bool)
    if gate == "both":
        return artefact[:, 0] & artefact[:, 1]
    if gate == "any":
        return artefact[:, 0] | artefact[:, 1]
    raise ValueError(gate)


def kth_of_last(score: np.ndarray, k: int, n: int = 10) -> np.ndarray:
    """k-th largest value among score[t-n+1 .. t] (fewer at the start -> -inf padding)."""
    from numpy.lib.stride_tricks import sliding_window_view
    padded = np.concatenate([np.full(n - 1, -np.inf, dtype=np.float64), score.astype(np.float64)])
    win = np.sort(sliding_window_view(padded, n), axis=1)
    return win[:, n - k]


def run_events_at(sk: np.ndarray, th: float):
    """Alarm events (seconds) when the k-th largest score >= th. Window t ends at second t+2."""
    ev = mask_to_events(sk >= th)
    return [(a + 2.0, b + 2.0) for a, b in ev]


def subject_metrics(counts: dict) -> dict:
    """counts: subject -> [tp, fp, n_ref, hours]; returns mean-over-subjects and pooled metrics."""
    sens, prec, f1, fp24 = [], [], [], []
    T = np.zeros(4)
    for tp, fp, nref, hours in counts.values():
        T += (tp, fp, nref, hours)
        s = tp / nref if nref else np.nan
        p = tp / (tp + fp) if (tp + fp) else 0.0
        sens.append(s)
        prec.append(p)
        f1.append(2 * s * p / (s + p) if nref and (s + p) > 0 else (0.0 if nref else np.nan))
        fp24.append(24 * fp / hours if hours else np.nan)
    ps = T[0] / T[2] if T[2] else np.nan
    pp = T[0] / (T[0] + T[1]) if (T[0] + T[1]) else 0.0
    return {"sensitivity": float(np.nanmean(sens)), "precision": float(np.nanmean(prec)),
            "f1": float(np.nanmean(f1)), "fp_per_24h": float(np.nanmean(fp24)),
            "pooled_sensitivity": float(ps), "pooled_precision": float(pp),
            "pooled_f1": float(2 * ps * pp / (ps + pp)) if (ps + pp) > 0 else 0.0,
            "pooled_fp_per_24h": float(24 * T[1] / T[3]) if T[3] else np.nan}


def sweep(runs: list[dict], ks=(6, 8, 10), gates=GATES, n_thresholds: int = 40, thresholds=None):
    """runs: dicts with subject, score, artefact, seizures, duration_s (one per recording).
    Returns rows (gate, k, th, metrics, per-subject counts)."""
    refs = [prepare_ref([tuple(s) for s in r["seizures"]], r["duration_s"]) for r in runs]
    if thresholds is None:
        allsc = np.concatenate([r["score"] for r in runs])
        qs = 1 - np.logspace(-4.5, -0.3, n_thresholds)       # dense in the upper tail
        thresholds = np.unique(np.quantile(allsc, qs))
    rows = []
    for gate in gates:
        gated = [np.where(gate_mask(r["artefact"], gate), -np.inf, r["score"]) for r in runs]
        for k in ks:
            sks = [kth_of_last(g, k) for g in gated]
            for th in thresholds:
                counts = defaultdict(lambda: [0, 0, 0, 0.0])
                for r, sk, ref in zip(runs, sks, refs):
                    tp, fp, nref = score_events(ref, run_events_at(sk, th))
                    c = counts[r["subject"]]
                    c[0] += tp; c[1] += fp; c[2] += nref; c[3] += r["duration_s"] / 3600
                m = subject_metrics(counts)
                rows.append({"gate": gate, "k": int(k), "threshold": float(th), **m,
                             "per_subject": {s: list(v) for s, v in counts.items()}})
    return rows


def choose(rows: list[dict]) -> dict:
    best_f1 = max(rows, key=lambda r: (r["f1"], -r["fp_per_24h"]))
    ok = [r for r in rows if r["fp_per_24h"] <= 24.0]
    best_sens = max(ok, key=lambda r: (r["sensitivity"], -r["fp_per_24h"])) if ok else None
    return {"best_f1": best_f1, "sens_at_1fah": best_sens}
