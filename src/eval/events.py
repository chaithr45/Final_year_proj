"""Conversions between per-second masks and event lists (seconds, end exclusive)."""
from __future__ import annotations

import numpy as np


def mask_to_events(mask: np.ndarray, fs: float = 1.0) -> list[tuple[float, float]]:
    """Contiguous runs of True as (start_s, end_s), end exclusive."""
    m = np.asarray(mask, dtype=bool).astype(np.int8)
    if m.size == 0:
        return []
    d = np.diff(np.concatenate(([0], m, [0])))
    starts, ends = np.flatnonzero(d == 1), np.flatnonzero(d == -1)
    return [(s / fs, e / fs) for s, e in zip(starts, ends)]


def events_to_mask(events, n: int, fs: float = 1.0) -> np.ndarray:
    m = np.zeros(n, dtype=bool)
    for a, b in events:
        m[max(0, int(np.floor(a * fs + 1e-9))):min(n, int(np.ceil(b * fs - 1e-9)))] = True
    return m
