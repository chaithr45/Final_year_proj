"""Official outer split and patient-wise inner folds (Section 7.1).

Outer split (fixed): train sub-001..sub-096, test sub-097..sub-125, identical to
biomedepi/seizeit2 net/datasets/SZ2_training.tsv and SZ2_validation.tsv.
The test patients are scored once per final model (M6) and never used for tuning.
"""
from __future__ import annotations

import json
import warnings
from pathlib import Path

import numpy as np

TRAIN_RANGE = (1, 96)
TEST_RANGE = (97, 125)


def subject_id(n: int) -> str:
    return f"sub-{n:03d}"


def official_train_subjects() -> list[str]:
    return [subject_id(i) for i in range(TRAIN_RANGE[0], TRAIN_RANGE[1] + 1)]


def official_test_subjects() -> list[str]:
    return [subject_id(i) for i in range(TEST_RANGE[0], TEST_RANGE[1] + 1)]


def split_of(subject: str) -> str:
    n = int(subject.split("-")[1])
    if TRAIN_RANGE[0] <= n <= TRAIN_RANGE[1]:
        return "train"
    if TEST_RANGE[0] <= n <= TEST_RANGE[1]:
        return "test"
    raise ValueError(f"{subject} is outside the official split")


def seizure_count_bin(n: int) -> str:
    if n <= 1:
        return "1"
    if n <= 4:
        return "2-4"
    if n <= 9:
        return "5-9"
    return "10+"


def make_inner_folds(subjects: list[str], seizure_counts: dict[str, int],
                     centres: dict[str, str] | None = None, n_splits: int = 5,
                     seed: int = 0) -> dict[str, int]:
    """Assign each TRAINING subject to one of `n_splits` patient-wise folds.

    Stratified by seizure-count bin, and by centre when centre labels are
    available (they are not in the public participants.tsv; see the data audit).
    Grouped by patient, so no patient appears in two folds.
    """
    from sklearn.model_selection import StratifiedGroupKFold

    test = set(official_test_subjects())
    leaked = [s for s in subjects if s in test]
    if leaked:
        raise ValueError(f"test subjects must never enter the inner folds: {leaked}")
    subjects = sorted(subjects)
    strata = []
    for s in subjects:
        key = seizure_count_bin(seizure_counts.get(s, 0))
        if centres is not None:
            key = f"{centres.get(s, 'unknown')}|{key}"
        strata.append(key)
    x = np.zeros((len(subjects), 1))
    cv = StratifiedGroupKFold(n_splits=n_splits, shuffle=True, random_state=seed)
    folds: dict[str, int] = {}
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="The least populated class")
        for k, (_, val_idx) in enumerate(cv.split(x, strata, groups=subjects)):
            for i in val_idx:
                folds[subjects[i]] = k
    return folds


def save_folds(folds: dict[str, int], path: str | Path, meta: dict) -> None:
    payload = {"meta": meta, "folds": {s: folds[s] for s in sorted(folds)}}
    Path(path).write_text(json.dumps(payload, indent=2) + "\n")


def load_folds(path: str | Path) -> dict[str, int]:
    return {s: int(k) for s, k in json.loads(Path(path).read_text())["folds"].items()}
