"""Load cached golden features (scripts/extract_features.py) for training and evaluation.

Training sets: every seizure window plus a random background subsample at a fixed ratio
(Section 7.3), drawn per call with a seed. Evaluation sets: every window of every run,
kept per run so alarms never cross a file and SzCORE can score each recording.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]


@dataclass
class RunFeatures:
    subject: str
    run: str
    X: np.ndarray            # (n_win, n_features) int16 / float32
    y: np.ndarray            # (n_win,) window labels
    artefact: np.ndarray     # (n_win, 2) bool
    present: np.ndarray      # (n_win, 4) bool
    seizures: np.ndarray     # (k, 2) seconds
    duration_s: float


def stack_windows(X: np.ndarray, k: int, rows: np.ndarray | None = None) -> np.ndarray:
    """Causal stacking within one run: row t -> [X[t-k+1], ..., X[t]] (earliest rows repeat X[0])."""
    rows = np.arange(len(X)) if rows is None else rows
    parts = [X[np.maximum(rows - j, 0)] for j in range(k - 1, -1, -1)]
    return np.concatenate(parts, axis=1)


class FeatureStore:
    onset_s = 20     # N5 onset weighting: first 20 windows (s) of each seizure
    stack = 1        # >1: each row holds the last `stack` windows (N1 baseline)

    def __init__(self, mode: str = "int", root: Path | None = None):
        self.dir = (root or REPO / "cache" / "features") / mode
        self.files = {p.stem: p for p in sorted(self.dir.glob("sub-*_run-*.npz")) if ".tmp" not in p.name}

    def runs_of(self, subjects) -> list[str]:
        s = set(subjects)
        return [k for k in self.files if k.split("_")[0] in s]

    def missing(self, subjects, expected_runs: dict[str, int] | None = None) -> list[str]:
        have = {k.split("_")[0] for k in self.files}
        return [s for s in subjects if s not in have]

    def load_run(self, key: str) -> RunFeatures:
        d = np.load(self.files[key])
        sub, run = key.split("_")[:2]
        X = stack_windows(d["X"], self.stack) if self.stack > 1 else d["X"]
        return RunFeatures(sub, run, X, d["y"].astype(np.int8), d["artefact"].astype(bool),
                           d["present"].astype(bool), d["seizures"], float(d["duration_s"]))

    def load_labels(self, key: str) -> np.ndarray:
        """Window labels of one run without reading its features."""
        with np.load(self.files[key]) as d:
            return d["y"].astype(np.int8)

    def iter_runs(self, subjects):
        for k in self.runs_of(subjects):
            yield self.load_run(k)

    def training_set(self, subjects, bg_ratio: float, seed: int = 0, max_bg: int | None = None,
                     extra_bg: dict[str, np.ndarray] | None = None):
        """All seizure windows + bg_ratio x as many uniformly drawn background windows.

        Two passes over the cache (labels first, then only the selected rows), so memory stays
        bounded. `extra_bg` (run key -> window indices) adds hard negatives (Section 7.3).
        Returns X, y, groups (subject index per row), present, keys (run, window index).
        """
        rng = np.random.default_rng(seed)
        keys = self.runs_of(subjects)
        ys = {k: np.load(self.files[k])["y"] for k in keys}
        n_pos = sum(int((y == 1).sum()) for y in ys.values())
        neg_sizes = np.array([int((ys[k] == 0).sum()) for k in keys])
        n_bg = int(round(bg_ratio * n_pos))
        if max_bg:
            n_bg = min(n_bg, max_bg)
        pick = np.sort(rng.choice(neg_sizes.sum(), size=min(n_bg, int(neg_sizes.sum())), replace=False))
        offs = np.concatenate(([0], np.cumsum(neg_sizes)))
        Xs, Ys, Gs, Ps, Ks = [], [], [], [], []
        sub_ids = {}
        for i, k in enumerate(keys):
            y = ys[k]
            neg_idx = np.flatnonzero(y == 0)
            sel = neg_idx[pick[(pick >= offs[i]) & (pick < offs[i + 1])] - offs[i]]
            if extra_bg and k in extra_bg:
                sel = np.union1d(sel, extra_bg[k])
            rows = np.concatenate([np.flatnonzero(y == 1), sel])
            if not len(rows):
                continue
            d = np.load(self.files[k])
            Xs.append(stack_windows(d["X"], self.stack, rows) if self.stack > 1 else d["X"][rows])
            Ys.append(y[rows]); Ps.append(d["present"][rows])
            Gs.append(np.full(len(rows), sub_ids.setdefault(k.split("_")[0], len(sub_ids))))
            Ks.append(np.stack([np.full(len(rows), i), rows], axis=1))
        X, y = np.concatenate(Xs), np.concatenate(Ys).astype(np.int8)
        perm = rng.permutation(len(y))
        rk = np.concatenate(Ks)
        # seizure "bags" (one id per contiguous block of positive windows) and onset flags
        bag_of, onset_of = {}, {}
        next_bag = 0
        for i, k in enumerate(keys):
            pos = np.flatnonzero(ys[k] == 1)
            if not len(pos):
                continue
            starts = np.r_[0, np.flatnonzero(np.diff(pos) > 1) + 1]
            ends = np.r_[starts[1:], len(pos)]
            for a, b in zip(starts, ends):
                for j, w in enumerate(pos[a:b]):
                    bag_of[(i, int(w))] = next_bag
                    onset_of[(i, int(w))] = j < self.onset_s
                next_bag += 1
        self.last_bags = np.array([bag_of.get((int(a), int(b)), -1) for a, b in rk[perm]])
        self.last_onset = np.array([onset_of.get((int(a), int(b)), False) for a, b in rk[perm]])
        return (X[perm], y[perm], np.concatenate(Gs)[perm], np.concatenate(Ps)[perm],
                [(keys[a], b) for a, b in rk[perm]])
