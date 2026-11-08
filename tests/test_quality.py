import numpy as np

from seizelut.data.quality import constant_runs, flatline_summary, rms_artefact_mask, window_rms


def test_constant_runs():
    x = np.array([1, 2, 2, 2, 3, 3, 4, 4, 4, 4])
    assert constant_runs(x, 3).tolist() == [[1, 3], [6, 4]]


def test_flatline_summary_on_fixture(bids_root):
    from seizelut.data.bids import discover_runs
    r = discover_runs(bids_root)[0]
    d = r.read_signals("eeg")
    s = flatline_summary(d.digital["BTEleft SD"], 256, 1.0)
    assert s["flat_spans"] == 1 and abs(s["flat_s"] - 3.0) < 0.01


def test_window_rms_and_rule():
    fs = 250
    x = np.concatenate([np.full(2 * fs, 5.0), np.full(2 * fs, 50.0), np.full(2 * fs, 500.0)])
    rms = window_rms(x, fs)
    assert np.allclose(rms[[0, 2, 4]], [5.0, 50.0, 500.0])
    assert rms_artefact_mask(rms[[0, 2, 4]]).tolist() == [True, False, True]
