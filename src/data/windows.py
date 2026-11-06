"""Windowing and labels (Section 5.1).

Windows are defined on a time grid in seconds and mapped to sample indices per
modality, so 256 Hz EEG, 250 Hz files and 25 Hz motion share one window grid.
A window never extends past the end of its run (no window crosses a file).
"""
from __future__ import annotations

import numpy as np

_EPS = 1e-9


def window_starts(duration_s: float, length_s: float = 2.0, hop_s: float = 1.0) -> np.ndarray:
    """Start times of every full window inside [0, duration_s)."""
    if duration_s < length_s:
        return np.zeros(0)
    n = int(np.floor((duration_s - length_s) / hop_s + _EPS)) + 1
    return np.arange(n) * hop_s


def to_sample(t_s: np.ndarray | float, fs: float) -> np.ndarray:
    """Sample index of time t (floor, robust to float noise)."""
    return np.floor(np.asarray(t_s) * fs + _EPS).astype(np.int64)


def overlap_seconds(starts: np.ndarray, length_s: float, intervals: list[tuple[float, float]]) -> np.ndarray:
    """Seconds of each window [s, s+length) covered by the (merged) intervals."""
    starts = np.asarray(starts, dtype=np.float64)
    ov = np.zeros_like(starts)
    for a, b in intervals:
        ov += np.clip(np.minimum(starts + length_s, b) - np.maximum(starts, a), 0.0, None)
    return ov


def window_labels(starts: np.ndarray, length_s: float, intervals: list[tuple[float, float]],
                  min_overlap: float = 0.5) -> np.ndarray:
    """1 if at least `min_overlap` of the window lies inside a seizure (SzCORE sample rule)."""
    frac = overlap_seconds(starts, length_s, intervals) / length_s
    return (frac >= min_overlap - _EPS).astype(np.int8)


def seizure_augmentation_starts(intervals: list[tuple[float, float]], duration_s: float,
                                length_s: float = 2.0, hop_s: float = 1.0, aug_hop_s: float = 0.5,
                                min_overlap: float = 0.5) -> np.ndarray:
    """Extra positive windows on a finer grid inside seizures. TRAINING ONLY.

    Returns starts on the `aug_hop_s` grid that are labelled seizure and are not
    already on the regular `hop_s` grid. Never apply to evaluation data.
    """
    if not intervals:
        return np.zeros(0)
    grid = window_starts(duration_s, length_s, aug_hop_s)
    lab = window_labels(grid, length_s, intervals, min_overlap).astype(bool)
    on_regular = np.abs(grid / hop_s - np.round(grid / hop_s)) < _EPS
    return grid[lab & ~on_regular]
