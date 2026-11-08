import numpy as np

from seizelut.data.windows import (overlap_seconds, seizure_augmentation_starts, to_sample,
                                   window_labels, window_starts)


def test_window_grid_stays_inside_run():
    s = window_starts(10.0, 2.0, 1.0)
    assert np.array_equal(s, np.arange(9.0))
    assert s[-1] + 2.0 <= 10.0
    assert window_starts(1.5).size == 0
    assert window_starts(10.9).size == 9


def test_fifty_percent_rule():
    starts = np.array([0.0, 1.0, 2.0, 3.0, 4.0])
    # seizure covers [3, 4]: window [2,4) has 1 s = 50 % -> positive; [3,5) 50 % -> positive
    lab = window_labels(starts, 2.0, [(3.0, 4.0)])
    assert lab.tolist() == [0, 0, 1, 1, 0]
    assert window_labels(starts, 2.0, [(3.0, 3.9)]).sum() == 0


def test_overlap_sums_merged_intervals():
    assert overlap_seconds(np.array([0.0]), 2.0, [(0.0, 0.5), (1.0, 1.5)]).tolist() == [1.0]


def test_augmentation_is_positive_and_off_grid():
    iv = [(40.0, 70.0)]
    aug = seizure_augmentation_starts(iv, 120.0)
    assert aug.size > 0
    assert np.all(window_labels(aug, 2.0, iv) == 1)
    assert np.all(np.abs(aug - np.round(aug)) == 0.5)
    assert aug.min() >= 39.0 and aug.max() + 2.0 <= 71.0
    assert seizure_augmentation_starts([], 120.0).size == 0


def test_samples_per_modality():
    s = window_starts(6.0)
    assert to_sample(s, 256).tolist() == [0, 256, 512, 768, 1024]
    assert to_sample(np.array([0.5, 1.5]), 25).tolist() == [12, 37]
    assert to_sample(np.array([0.1 * 3]), 250).tolist() == [75]   # float noise safe
