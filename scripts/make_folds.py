#!/usr/bin/env python3
"""Write the fixed 5-fold patient-wise inner split of the 96 training patients.

Stratified by seizure-count bin, seed chosen for even seizure totals (centre labels are not in the public release;
see reports/data_audit.md). Test patients sub-097..sub-125 never appear.

Usage:  python scripts/make_folds.py   ->  configs/folds_inner5.json
"""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

import yaml

from seizelut.data.bids import discover_runs
from seizelut.data.split import make_inner_folds, official_train_subjects, save_folds, seizure_count_bin

REPO = Path(__file__).resolve().parents[1]


def main() -> int:
    cfg = yaml.safe_load((REPO / "configs/dataset.yaml").read_text())
    root = REPO / cfg["dataset"]["root"]
    train = official_train_subjects()
    counts = Counter()
    for r in discover_runs(root, train):
        counts[r.subject] += len(r.read_annotations().seizures)
    s = cfg["split"]
    # Search seeds deterministically for the most even seizure count per fold
    # (uses annotation counts only, never model results).
    best = None
    for seed in range(s["inner_fold_seed"], s["inner_fold_seed"] + 500):
        f = make_inner_folds(train, counts, n_splits=s["inner_folds"], seed=seed)
        tot = [sum(counts[p] for p, v in f.items() if v == k) for k in range(s["inner_folds"])]
        if best is None or max(tot) - min(tot) < best[0]:
            best = (max(tot) - min(tot), seed, f)
    _, chosen_seed, folds = best
    per_fold = {k: {"patients": sum(1 for v in folds.values() if v == k),
                    "seizures": sum(counts[p] for p, v in folds.items() if v == k)} for k in range(s["inner_folds"])}
    meta = {"n_splits": s["inner_folds"], "seed": chosen_seed,
            "seed_search": f"{s['inner_fold_seed']}..{s['inner_fold_seed'] + 499}, min seizure-count range",
            "stratified_by": "seizure-count bin (1, 2-4, 5-9, 10+); centre not available",
            "grouped_by": "patient", "per_fold": per_fold,
            "bins": dict(Counter(seizure_count_bin(counts[p]) for p in train))}
    out = REPO / s["inner_folds_file"]
    save_folds(folds, out, meta)
    print(out)
    for k, v in per_fold.items():
        print(f"  fold {k}: {v['patients']} patients, {v['seizures']} seizures")
    return 0


if __name__ == "__main__":
    sys.exit(main())
