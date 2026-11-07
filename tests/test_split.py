import pytest

from seizelut.data.split import (load_folds, make_inner_folds, official_test_subjects,
                                 official_train_subjects, save_folds, split_of)


def test_official_split():
    tr, te = official_train_subjects(), official_test_subjects()
    assert len(tr) == 96 and len(te) == 29 and not set(tr) & set(te)
    assert tr[0] == "sub-001" and tr[-1] == "sub-096" and te[0] == "sub-097" and te[-1] == "sub-125"
    assert split_of("sub-096") == "train" and split_of("sub-097") == "test"
    with pytest.raises(ValueError):
        split_of("sub-126")


def test_inner_folds_partition_train_patients(tmp_path):
    subs = official_train_subjects()
    counts = {s: (i % 13) + 1 for i, s in enumerate(subs)}
    folds = make_inner_folds(subs, counts, n_splits=5, seed=1)
    assert set(folds) == set(subs) and set(folds.values()) == set(range(5))
    sizes = [list(folds.values()).count(k) for k in range(5)]
    assert max(sizes) - min(sizes) <= 2
    assert folds == make_inner_folds(subs, counts, n_splits=5, seed=1)
    save_folds(folds, tmp_path / "f.json", {"seed": 1})
    assert load_folds(tmp_path / "f.json") == folds


def test_test_patients_never_enter_folds():
    with pytest.raises(ValueError):
        make_inner_folds(["sub-001", "sub-100"], {}, n_splits=2)
