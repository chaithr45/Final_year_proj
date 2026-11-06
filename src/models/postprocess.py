"""Shared post-processing for our models (Section 6.5).

1. Per-second decision = score >= threshold and artefact flag clear.
2. Alarm second when >= k of the last 10 decisions are positive (causal; official baseline k = 8).
3. Contiguous alarm seconds form an alarm event; events closer than `merge_s` are merged and a
   new alarm cannot start within `refractory_s` of the previous alarm's end.
Everything is integer/causal so it maps to a shift register and counters in hardware.
"""
from __future__ import annotations

import numpy as np

from ..eval.events import mask_to_events


def decisions(score: np.ndarray, threshold, artefact: np.ndarray | None = None) -> np.ndarray:
    d = np.asarray(score) >= threshold
    if artefact is not None:
        d &= ~np.asarray(artefact, dtype=bool)
    return d


def k_of_n(dec: np.ndarray, k: int = 8, n: int = 10) -> np.ndarray:
    """Alarm at t when at least k of decisions t-n+1..t are positive (fewer at the start)."""
    c = np.concatenate(([0], np.cumsum(np.asarray(dec, dtype=np.int64))))
    t = np.arange(1, len(dec) + 1)
    window = c[t] - c[np.maximum(0, t - n)]
    return window >= k


def alarm_events(alarm_mask: np.ndarray, merge_s: float = 90.0, refractory_s: float = 0.0,
                 fs: float = 1.0) -> list[tuple[float, float]]:
    out: list[list[float]] = []
    for a, b in mask_to_events(alarm_mask, fs):
        if out and a - out[-1][1] < max(merge_s, refractory_s):
            out[-1][1] = b
        else:
            out.append([a, b])
    return [(a, b) for a, b in out]


def postprocess(score, threshold, artefact=None, k=8, n=10, merge_s=90.0, refractory_s=0.0):
    return alarm_events(k_of_n(decisions(score, threshold, artefact), k, n), merge_s, refractory_s)
