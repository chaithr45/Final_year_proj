"""Tests of the impairment emulator's golden model (ms/py/impair.py). Run: pytest -q ms/py/tests"""
import math

import numpy as np
import pytest
from scipy.signal import welch
from scipy.stats import norm

import impair as I

FS = 256.0
UV = 0.25          # uV per input LSB (biopotentials)


def _x(n=200_000, seed=0):
    r = np.random.default_rng(seed)
    return np.clip(np.round(r.normal(0, 40, n)), -32768, 32767).astype(np.int16)   # ~10 uV rms EEG-like


def test_identity_is_bit_exact():
    x = _x()
    c = I.compile_impairment(I.Impairment(), FS, UV)
    assert c.is_identity() and c.bits == 16
    y, st = I.apply(x, c, (0, 0, 0))
    assert np.array_equal(y, x) and st["clipped"] == 0
    # the arithmetic path itself (not the shortcut) is also the identity at q = 1 LSB, C = 2^15
    q, nclip = I._clip_quant(x.astype(np.int64) << I.FRAC, 0, 1 << 15)
    assert np.array_equal(q, x) and nclip == 0


def test_xoroshiro_matches_reference():
    s0, s1 = I.stream_state(7, 1, 2)
    ref, _, _ = I.xoroshiro128p_py(s0, s1, 5000)
    st = np.array([s0, s1], dtype=np.uint64)
    assert np.array_equal(I._raw(st, 5000), ref)
    rg = pytest.importorskip("randomgen")
    g = rg.Xoroshiro128(0, plusplus=False)
    g.state = {"bit_generator": "randomgen.xoroshiro128.Xoroshiro128", "s": np.array([s0, s1], dtype=np.uint64),
               "plusplus": False, "has_uint32": 0, "uinteger": 0}
    assert np.array_equal(g.random_raw(5000), ref)


def _exact_sum_pmf():
    """Exact pmf of the sum of 64 uniform 12-bit integers (FFT convolution)."""
    from scipy.fft import irfft, next_fast_len, rfft
    n, m = I.N_UNIF, 1 << I.UBITS
    L = next_fast_len(n * (m - 1) + 1)
    p = irfft(rfft(np.ones(m) / m, L) ** n, L)[: n * (m - 1) + 1]
    p = np.clip(p, 0, None)
    return p / p.sum()


def test_gaussian_generator_distribution():
    n = 1 << 21
    z = I._gauss_block(np.array(I.stream_state(1, 2, 3, 1), dtype=np.uint64), n)
    assert z.dtype == np.int64 and np.all(z % 2 == 0)               # Z = 2*sum - const: even values only
    se = I.SIGMA_Z / math.sqrt(n)
    assert abs(z.mean()) < 5 * se
    assert abs(z.std() / I.SIGMA_Z - 1) < 0.005
    # against the EXACT distribution of the algorithm: checks the uniforms are uniform and independent
    p = _exact_sum_pmf()
    s = (z + I.N_UNIF * 4095) // 2
    cdf = np.cumsum(p)
    probs = np.linspace(0.0005, 0.9995, 200)
    cuts = np.searchsorted(cdf, probs)
    emp = np.searchsorted(np.sort(s), cuts, side="right") / n
    expect = cdf[cuts]
    assert np.max(np.abs(emp - expect)) < 5 * math.sqrt(0.25 / n) + 1e-4
    # against a true Gaussian: the documented deviation of a 64-uniform sum (computed exactly, see LOG.md)
    k = np.arange(len(p))
    mu, sd = (len(p) - 1) / 2, math.sqrt(I.N_UNIF * (4096**2 - 1) / 12)
    ks = np.max(np.abs(cdf - norm.cdf((k + 0.5 - mu) / sd)))
    assert ks < 5e-4
    tail4 = p[np.abs(k - mu) > 4 * sd].sum() / (2 * norm.sf(4))
    assert 0.80 < tail4 < 0.87


def test_white_noise_density_is_achieved():
    dens = 0.1                                      # uV/sqrt(Hz) = 100 nV/sqrt(Hz)
    c = I.compile_impairment(I.Impairment(white_density=dens), FS, UV)
    assert abs(c.achieved["white_density"] / dens - 1) < 0.01
    x = np.zeros(1 << 20, dtype=np.int16)
    # measure before quantisation: run the chain on finer internal units
    z = I._gauss_block(np.array(I.stream_state(0, 0, 0, 1), dtype=np.uint64), len(x))
    v = I._scale(z, c.white_c, I.SCALE_F) / (16 / UV)              # back to uV
    f, s = welch(v, fs=FS, nperseg=4096)
    meas = math.sqrt(np.mean(s[(f > 1) & (f < 120)]))
    assert abs(meas / c.achieved["white_density"] - 1) < 0.02
    y, _ = I.apply(x, c, (0, 0, 0))
    assert abs(y.std() * UV / (dens * math.sqrt(FS / 2)) - 1) < 0.05   # 1.13 uV rms vs 0.25 uV LSB


def test_quantise_and_clip():
    x = _x()
    c = I.compile_impairment(I.Impairment(lsb=4 * UV, clip=1024 * UV), FS, UV)   # q = 4 LSB, N = 9 bits
    assert c.bits == 9
    y, st = I.apply(x, c, (0, 0, 0))
    assert np.all(y % 4 == 0)
    ref = np.clip(np.floor((x.astype(np.int64) + 2) / 4), -256, 255) * 4
    assert np.array_equal(y, ref) and st["clipped"] == int(np.sum((np.floor((x + 2) / 4) > 255) | (np.floor((x + 2) / 4) < -256)))
    with pytest.raises(ValueError):
        I.compile_impairment(I.Impairment(lsb=3 * UV), FS, UV)


def test_gain_error():
    # large amplitude, so the final rounding to the input LSB (correlated with x at small amplitudes) is negligible
    x = np.clip(np.round(np.random.default_rng(1).normal(0, 4000, 200_000)), -30000, 30000).astype(np.int16)
    for eps in (0.05, -0.2, 0.01):
        c = I.compile_impairment(I.Impairment(gain_err=eps), FS, UV)
        y, _ = I.apply(x, c, (0, 0, 0))
        g = np.dot(y.astype(float), x) / np.dot(x.astype(float), x)
        assert abs(g - (1 + c.achieved["gain_err"])) < 2e-5
        assert abs(c.achieved["gain_err"] / eps - 1) < 0.01      # 4 signed powers of two: 0.4 % at 5 %


def test_mains_harmonic_aliases_to_6_hz_and_aa_attenuates():
    x = np.zeros(1 << 16, dtype=np.int16)
    c = I.compile_impairment(I.Impairment(mains_peak=(0, 0, 0, 0, 100.0)), FS, UV)      # 250 Hz, 100 uV peak
    y, _ = I.apply(x, c, (1, 0, 0))
    f, s = welch(y * UV, fs=FS, nperseg=4096)
    assert abs(f[np.argmax(s)] - 6.0) < 0.1
    assert abs(y.std() * UV * math.sqrt(2) / 100 - 1) < 0.01
    assert c.achieved["mains_h5"]["alias_hz"] == 6.0
    c2 = I.compile_impairment(I.Impairment(mains_peak=(0, 0, 0, 0, 100.0), aa_hz=40, aa_order=2), FS, UV)
    att = c2.achieved["mains_h5"]["aa_attenuation"]
    assert abs(att - 1 / math.sqrt(1 + (250 / 40) ** 4)) < 1e-12
    y2, _ = I.apply(x, c2, (1, 0, 0))
    assert abs(y2.std() / y.std() - att) < 0.05


def test_offset_and_drift():
    x = np.zeros(1 << 21, dtype=np.int16)              # 2.3 h at 256 Hz
    c = I.compile_impairment(I.Impairment(offset=100.0), FS, UV)
    y, _ = I.apply(x, c, (0, 0, 0))
    assert np.all(y == 400)
    c = I.compile_impairment(I.Impairment(drift_rms=50.0, drift_tau_s=16.0), FS, UV)
    y, _ = I.apply(x, c, (3, 0, 0))
    d = y[20 * 4096:] * UV                              # skip the start-up transient
    assert abs(d.mean()) < 5.0                          # ~500 independent tau-intervals: se ~ 50/sqrt(500) = 2.2
    assert abs(d.std() / c.achieved["drift_rms"] - 1) < 0.1


def test_pink_corner():
    x = np.zeros(1 << 22, dtype=np.int16)
    imp = I.Impairment(white_density=0.2, pink_corner_hz=2.0)
    c = I.compile_impairment(imp, FS, UV)
    assert abs(c.achieved["pink_corner_hz"] / 2.0 - 1) < 0.05
    y, _ = I.apply(x, c, (5, 0, 0))
    f, s = welch(y * UV, fs=FS, nperseg=1 << 16)
    white = c.achieved["white_density"] ** 2                  # one-sided PSD of the white part (uV^2/Hz)
    lo = (f > 0.1) & (f < 0.2)
    ratio = np.mean(s[lo] * f[lo]) / (white * c.achieved["pink_corner_hz"])  # 1/f part: white * corner / f
    assert 0.85 < ratio < 1.2


def test_voss_coefficient_reproduces():
    assert abs(I.voss_calibration(n=1 << 22, seed=9) / I._VOSS_C - 1) < 0.02


@pytest.mark.parametrize("kind,fc", [("hp", 0.5), ("lp", 40.0), ("hp", 0.05)])
def test_afe_filter_corner(kind, fc):
    imp = I.Impairment(hp_hz=fc) if kind == "hp" else I.Impairment(lp_hz=fc)
    c = I.compile_impairment(imp, FS, UV)
    n = 1 << 18 if fc > 0.1 else 1 << 21
    t = np.arange(n) / FS
    x = np.round(4000 * np.sin(2 * np.pi * fc * t)).astype(np.int16)
    y, _ = I.apply(x, c, (0, 0, 0))
    tail = slice(n // 2, None)
    gain_db = 20 * math.log10(y[tail].std() / x[tail].std())
    assert abs(gain_db + 3.01) < 0.3, gain_db


def test_streams_are_independent_and_reproducible():
    c = I.compile_impairment(I.Impairment(white_density=0.5), FS, UV)
    x = np.zeros(50_000, dtype=np.int16)
    a, _ = I.apply(x, c, (1, 2, 3))
    b, _ = I.apply(x, c, (1, 2, 3))
    d, _ = I.apply(x, c, (1, 2, 4))
    assert np.array_equal(a, b)
    assert abs(np.corrcoef(a, d)[0, 1]) < 0.02
