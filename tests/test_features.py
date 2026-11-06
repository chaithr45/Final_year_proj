import numpy as np
import pytest

from seizelut.data.bids import discover_runs
from seizelut.features import spec as S
from seizelut.features.fixedpoint import csd, ilog2, is_stable, spt_quantize, spt_terms
from seizelut.features.golden import block_stats, extract
from seizelut.features.kernels import biquad_int, ema_context_int, ema_highpass_int, rpeak_detect


def test_ilog2_exact():
    v = np.array([0, 1, 2, 3, 4, 5, 7, 8, 15, 16, 17, 1000, 2 ** 20, 2 ** 20 + 2 ** 17, 2 ** 40 - 1])
    want = [0, 0, 8, 12, 16, 18, 22, 24, 31, 32, 32]
    got = ilog2(v)
    assert got[:11].tolist() == want
    assert got[12] == 160 and got[13] == 161
    ref = [int(np.floor(np.log2(x))) * 8 + int(((x / 2 ** np.floor(np.log2(x))) - 1) * 8) if x > 1 else 0 for x in v]
    assert got.tolist()[:-1] == ref[:-1]


def test_csd_and_spt():
    for v in [1, 3, 7, 151, -151, 64416, 12345]:
        assert sum(s * (1 << k) for s, k in csd(v)) == v
    assert spt_terms(spt_quantize(0.00226, 16, 3)) <= 3


def test_all_filters_stable_and_spt():
    for bq in S.FILTERS.values():
        assert is_stable(bq), bq.name
        assert all(spt_terms(c) <= 5 for c in (*bq.b, *bq.a)), bq.name


def test_biquad_error_feedback_tracks_float():
    from scipy.signal import lfilter
    rng = np.random.default_rng(0)
    x = np.round(np.cumsum(rng.normal(0, 3, 256 * 120)) + rng.normal(0, 40, 256 * 120)).astype(np.int64)
    for name in ("eeg_hp05", "eeg_hp1", "eeg_lp4", "eeg_notch50"):
        bq = S.FILTERS[name]
        y, nsat = biquad_int(x, *bq.b, *bq.a, bq.frac_bits, S.FILTER_STATE_BITS)
        s = 1 << bq.frac_bits
        f = lfilter(np.array(bq.b) / s, [1.0, bq.a[0] / s, bq.a[1] / s], x.astype(float))
        tol = 2.5 if name == "eeg_notch50" else 1.5   # notch poles at 50 Hz sit where the shaped noise is
        assert nsat == 0 and np.std(y - f) < tol, name


def test_biquad_saturates():
    bq = S.FILTERS["eeg_lp25"]
    y, nsat = biquad_int(np.full(1000, 30000, dtype=np.int64), *bq.b, *bq.a, bq.frac_bits, 14)
    assert nsat > 0 and y.max() == (1 << 13) - 1


def test_ema_highpass_removes_offset():
    x = np.full(2000, 500, dtype=np.int64)
    assert ema_highpass_int(x, 5, 8)[-1] == 0


def test_block_stats_counts():
    x = np.array([1, -1, 2, 2, -3, 4, 4, 4], dtype=np.int64)
    mav, ll, zc, ext = block_stats(x, 4)
    assert mav.tolist() == [6, 15] and zc.tolist() == [2, 2]
    assert ll.tolist() == [2 + 3 + 0, 5 + 7 + 0 + 0]
    assert ext.tolist() == [1, 2]


def test_context_is_causal_and_starts_at_zero():
    f = np.array([[10], [10], [20], [20]], dtype=np.int64)
    ctx = ema_context_int(f, np.ones(4, bool), 1, 6)[:, 0]
    assert ctx.tolist() == [0, 0, 10, 5]
    ctx2 = ema_context_int(f, np.array([False, True, True, True]), 1, 6)[:, 0]
    assert ctx2[0] == 0 and ctx2[1] == 0


def test_rpeak_on_synthetic_ecg():
    fs = 256
    t = np.arange(fs * 60) / fs
    ecg = np.zeros_like(t)
    for b in np.arange(0.5, 60, 0.8):                     # 75 bpm
        ecg += 1000 * np.exp(-((t - b) / 0.01) ** 2)
    ecg += np.random.default_rng(1).normal(0, 20, len(t))
    q = np.round(ecg / S.LSB_BIO).astype(np.int64)
    from seizelut.features.golden import _Ops
    ops = _Ops("int")
    e = ops.filt(ops.filt(q, S.FILTERS["ecg_hp5"]), S.FILTERS["ecg_lp15"])
    beats = rpeak_detect(e, S.ECG_INTEG, S.ECG_REFRACTORY, S.ECG_SPK_SHIFT, S.ECG_THR_SHIFT, S.ECG_WARMUP)
    rr = np.diff(beats)
    assert 70 <= len(beats) <= 75 and abs(np.median(rr) - 0.8 * fs) <= 2


def test_feature_list_consistent():
    assert len(S.FEATURES) == len(set(S.FEATURES)) == 117
    assert all(n in S.FEATURE_BITS for n in S.FEATURES)


@pytest.fixture(scope="module")
def fixture_features(bids_root):
    runs = discover_runs(bids_root)
    outs = {}
    for r in runs:
        sig = {m: r.read_signals(m) for m in r.modalities}
        n = int(sig["eeg"].duration_s)
        outs[r.key] = (extract(sig, n, "int"), extract(sig, n, "float"))
    return outs


def test_golden_widths_and_missing_modalities(fixture_features):
    for key, (gi, _) in fixture_features.items():
        X = gi["X"]
        assert X.shape[1] == 117 and X.dtype == np.int64
        for j, n in enumerate(S.FEATURES):
            assert np.abs(X[:, j]).max() <= (1 << (S.FEATURE_BITS[n] - 1)) - 1, (key, n)
        assert not any(gi["sat"].values()), key
    gi, _ = fixture_features["sub-001_run-02"]        # EEG only
    names = gi["names"]
    for n in names:
        if n.startswith(("ecg_", "emg_", "mov_", "present_")) or n.startswith(("ecg", "emg", "mov")):
            assert not gi["X"][:, names.index(n)].any(), n


def test_float_twin_close_to_golden(fixture_features):
    gi, gf = fixture_features["sub-001_run-01"]
    names = gi["names"]
    for n in ("eeg_mav_mean", "eeg_beta_mean", "emg_mav", "mov_acc_mag"):
        j = names.index(n)
        assert np.median(np.abs(gi["X"][5:, j] - gf["X"][5:, j])) <= 2.0, n


def test_seizure_raises_eeg_power(fixture_features):
    gi, _ = fixture_features["sub-001_run-01"]          # synthetic seizure at 40-70 s
    j = gi["names"].index("eeg_theta_mean")
    assert gi["X"][45:65, j].mean() > gi["X"][80:100, j].mean() + 8   # > 2x in log2 units
