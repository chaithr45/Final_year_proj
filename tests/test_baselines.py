import random

import numpy as np
import pytest

from seizelut.models.baselines import official as off


def test_subsample_keys_rule():
    recs = [(0, [(100.0, 130.0)], 1000.0), (1, [], 500.0)]
    keys = off.subsample_keys(recs, random.Random(1))
    sz = keys[keys[:, 3] == 1]
    assert len(sz) == 60                                   # (130-100)/0.5 seizure windows
    assert sz[:, 1].min() == 99.0 and sz[:, 1].max() == 128.5
    assert (keys[:, 3] == 0).sum() == 5 * 60               # factor 5 background
    bg = keys[keys[:, 3] == 0]
    on_rec0 = bg[bg[:, 0] == 0]
    assert not np.any((on_rec0[:, 2] > 100) & (on_rec0[:, 1] < 130))   # no background overlaps the seizure
    assert np.all(keys[:, 2] - keys[:, 1] == 2)


def test_sequential_labels_match_fifty_percent_rule():
    from seizelut.data.windows import window_labels
    events = [(10.0, 20.0), (50.0, 53.0)]
    lab = off.sequential_labels(100, events)
    assert np.array_equal(lab, window_labels(np.arange(100.0), 2.0, events))


def test_preprocess_resamples_to_250():
    x = np.random.default_rng(0).normal(0, 20, 256 * 30)
    y = off.preprocess_channel(x, 256)
    assert len(y) == 250 * 30
    assert off.window_rms(y).shape == (29,)


def test_cut_windows_zero_fills_out_of_range():
    ch = (np.arange(2500.0), np.arange(2500.0))
    w = off.cut_windows(ch, np.array([0.0, 8.0, 9.5, -1.0]))
    assert w.shape == (4, 500, 2) and w[0, 0, 0] == 0 and w[1, 0, 0] == 2000
    assert not w[2].any() and not w[3].any()


def test_chrononet_shapes_params_and_loss():
    torch = pytest.importorskip("torch")
    from seizelut.models.baselines.chrononet import ChronoNet, decay_schedule, weighted_focal_loss
    m = ChronoNet()
    trainable = sum(p.numel() for p in m.parameters())
    assert trainable == 129122 - 2 * 3 * 96          # Keras total minus BN moving mean/var
    p = m(torch.randn(4, 500, 2))
    assert p.shape == (4, 2) and torch.allclose(p.sum(1), torch.ones(4))
    y = torch.tensor([0, 0, 0, 1])
    assert float(weighted_focal_loss(p, y)) > 0
    lr = 0.01
    for e in range(20):
        lr = decay_schedule(e, lr)
    assert lr == pytest.approx(0.0025)
