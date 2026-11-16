"""Analog impairment emulator: the Python golden model of the in-fabric block (Phase 1, MS_SPEC.md 1.1).

Takes one channel of the detector's integer input stream (int16; 0.25 uV/LSB for EEG/ECG/EMG at 256 Hz,
2^-12 g/LSB for motion at 25 Hz) and returns it as an analog front end with the configured impairments would
have delivered it. Every operation is integer and maps to adders, shifts, a sine table and registers, so the
RTL block can reproduce this model bit for bit (no multipliers: constant products are signed-power-of-two sums).

Chain, electrode to ADC (internal unit = input LSB / 16, i.e. 4 extra fractional bits):

    v  = x << 4
    v += mains            50 Hz harmonics from a phase accumulator and a 4096-entry sine table; a harmonic
                          above fs/2 aliases by itself; its amplitude includes the analog anti-alias filter's
                          attenuation at the TRUE frequency (computed in compile())
    v += offset + drift   constant offset; drift = Ornstein-Uhlenbeck process (leaky integrator, tau = 2^k samples)
    v += white + pink     input-referred amplifier noise; Gaussian = sum of 64 uniform 12-bit integers from
                          xoroshiro128+ (checked against randomgen); 1/f part by the Voss-McCartney method
    v  = v + gain_err*v   gain error as a signed-power-of-two product
    v  = HP(v), LP(v)     front-end bandwidth: 2nd-order Butterworth sections, the front end's own biquad kernel.
                          With the high-pass on, the front end is AC-coupled and the offset never reaches the ADC
    clip and quantise     input-referred clip level C and LSB q, both powers of two times the input LSB:
                          code = clip(round(v / q), -2^(N-1), 2^(N-1)-1),  N = log2(2C/q)
    y  = code * q         back on the int16 input grid for the unchanged golden front end

With every impairment off and q = 1 LSB, C = 2^15 LSB, y == x exactly (tested).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, asdict

import numpy as np

from seizelut.features.fixedpoint import csd, design_biquad, spt_quantize
from seizelut.features.kernels import biquad_int, njit

FRAC = 4                  # internal fractional bits below the input LSB
SCALE_F = 24              # fractional bits of the signed-power-of-two scale factors
SCALE_TERMS = 4           # at most 4 signed powers of two per scale factor (4 adders in the RTL)
N_UNIF = 64               # uniforms summed per Gaussian sample (16 generator steps)
UBITS = 12                # bits per uniform
SIN_BITS = 12             # sine table: 4096 entries of round(32767 sin)
VOSS_ROWS = 16            # 1/f rows: octave-spaced holds from 2 to 2^16 samples
MAINS_HARMONICS = 7
AFE_F = 24                # fractional bits of the front-end-bandwidth biquads

_M64 = (1 << 64) - 1
SIN_TABLE = np.round(32767 * np.sin(2 * np.pi * np.arange(1 << SIN_BITS) / (1 << SIN_BITS))).astype(np.int64)
# std of Z = 2*sum(u) - N_UNIF*(2^UBITS - 1); exact for i.i.d. uniform integers on [0, 2^UBITS)
SIGMA_Z = 2.0 * math.sqrt(N_UNIF * ((1 << UBITS) ** 2 - 1) / 12.0)


# ----------------------------------------------------------------------------- random numbers

def splitmix64(x: int) -> tuple[int, int]:
    """Seeding only (software, at configuration time): returns (next state, output)."""
    x = (x + 0x9E3779B97F4A7C15) & _M64
    z = x
    z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & _M64
    z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & _M64
    return x, z ^ (z >> 31)


def stream_state(*key: int) -> tuple[int, int]:
    """128-bit xoroshiro state for one noise stream, derived from integer keys (seed, segment, channel, kind)."""
    x = 0x5EED_1E7_0000
    for k in key:
        x, _ = splitmix64(x ^ (int(k) & _M64))
    x, s0 = splitmix64(x)
    x, s1 = splitmix64(x)
    if s0 == 0 and s1 == 0:          # the all-zero state is the generator's only fixed point
        s1 = 1
    return s0, s1


def xoroshiro128p_py(s0: int, s1: int, n: int) -> tuple[np.ndarray, int, int]:
    """Reference xoroshiro128+ (Blackman and Vigna 2018; a, b, c = 24, 16, 37) in plain Python ints."""
    out = np.empty(n, dtype=np.uint64)
    for i in range(n):
        r = (s0 + s1) & _M64
        s1 ^= s0
        s0 = (((s0 << 24) | (s0 >> 40)) & _M64) ^ s1 ^ ((s1 << 16) & _M64)
        s1 = ((s1 << 37) | (s1 >> 27)) & _M64
        out[i] = r
    return out, s0, s1


@njit(cache=True)
def _gauss_block(state, n_out):
    """n_out Gaussian integers Z (mean 0, std SIGMA_Z) from the xoroshiro128+ state (uint64[2], updated in place).
    Each generator output gives four 12-bit uniforms, from bits 63:52, 51:40, 39:28, 27:16 (the low 16 bits of
    xoroshiro128+ are its weakest and are not used). Z = 2*sum - 64*4095."""
    out = np.empty(n_out, dtype=np.int64)
    s0 = state[0]
    s1 = state[1]
    mask = np.uint64(0xFFF)
    for i in range(n_out):
        acc = np.int64(0)
        for _ in range(16):
            r = s0 + s1
            s1 = s1 ^ s0
            s0 = ((s0 << np.uint64(24)) | (s0 >> np.uint64(40))) ^ s1 ^ (s1 << np.uint64(16))
            s1 = (s1 << np.uint64(37)) | (s1 >> np.uint64(27))
            acc += np.int64((r >> np.uint64(52)) & mask) + np.int64((r >> np.uint64(40)) & mask) \
                + np.int64((r >> np.uint64(28)) & mask) + np.int64((r >> np.uint64(16)) & mask)
        out[i] = 2 * acc - 64 * 4095
    state[0] = s0
    state[1] = s1
    return out


@njit(cache=True)
def _scale(z, c, f):
    """Round-to-nearest (z * c) / 2^f; c is a signed-power-of-two integer (shift-add in the RTL)."""
    return (z * c + (np.int64(1) << (f - 1))) >> f


# ----------------------------------------------------------------------------- configuration

@dataclass
class Impairment:
    """One channel's impairments in physical, input-referred units (base unit = uV for biopotentials, the input
    LSB for motion). Defaults = no impairment and today's pipeline (q = 1 LSB, C = 2^15 LSB)."""
    lsb: float | None = None           # q in base units; None = the input LSB
    clip: float | None = None          # C in base units; None = 2^15 input LSBs (int16 full scale)
    white_density: float = 0.0         # amplifier white noise, base units per sqrt(Hz)
    pink_corner_hz: float = 0.0        # 1/f corner: 1/f PSD equals the white PSD at this frequency (needs white)
    gain_err: float = 0.0              # relative gain error (0.05 = +5 %)
    offset: float = 0.0                # DC offset, base units
    drift_rms: float = 0.0             # Ornstein-Uhlenbeck drift, stationary rms, base units
    drift_tau_s: float = 64.0          # its time constant (rounded to 2^k samples)
    mains_peak: tuple = ()             # peak amplitude of 50 Hz harmonics 1..7 at the electrode, base units
    mains_hz: float = 50.0
    aa_hz: float | None = None         # analog anti-alias filter (Butterworth) corner; None = none
    aa_order: int = 2
    hp_hz: float | None = None         # front-end high-pass corner (2nd-order Butterworth); None = DC-coupled
    lp_hz: float | None = None         # front-end low-pass corner (2nd-order Butterworth); None = none


@dataclass
class Compiled:
    """Integer register values of one channel (what the RTL block's registers hold) plus achieved values."""
    fs: float
    q_shift: int                      # q = 2^q_shift input LSBs
    clip_code: int                    # 2^(N-1)
    white_c: int
    pink_c: int
    gain_c: int
    offset_i: int                     # internal units
    drift_c: int
    drift_k: int
    mains_inc: list = field(default_factory=list)
    mains_c: list = field(default_factory=list)
    hp: tuple | None = None           # (b0, b1, b2, a1, a2, frac)
    lp: tuple | None = None
    achieved: dict = field(default_factory=dict)

    @property
    def bits(self) -> int:
        return int(math.log2(self.clip_code)) + 1

    def is_identity(self) -> bool:
        return (self.q_shift == 0 and self.clip_code == 1 << 15 and not (self.white_c or self.pink_c or self.gain_c
                or self.offset_i or self.drift_c or any(self.mains_c) or self.hp or self.lp))


def _pow2_shift(value_lsb: float, what: str) -> int:
    k = math.log2(value_lsb)
    if abs(k - round(k)) > 1e-9 or round(k) < 0:
        raise ValueError(f"{what} must be a power of two times the input LSB, got {value_lsb} LSB")
    return int(round(k))


def _spt(v: float) -> int:
    return spt_quantize(v, SCALE_F, SCALE_TERMS) if v != 0 else 0


def voss_psd_coefficient() -> float:
    """One-sided PSD of the Voss-McCartney sum, per unit row variance, times f/fs (dimensionless; 1/f region).
    Measured once, deterministically, by voss_calibration(); see tests/test_impair.py."""
    return _VOSS_C


# Measured 16 Nov 2026 with voss_calibration() (2^24 samples): seeds 1, 2, 3 gave 1.37368, 1.37534, 1.37658; mean
# below. S*f is flat within about +-5 % from fs/8192 to fs/64 (0.03-4 Hz at 256 Hz) and falls 8 % and 20 % below in
# the two octaves up to fs/8 (the Voss sum has no row updated every sample). tests/test_impair.py re-measures it.
_VOSS_C = 1.3752


def compile_impairment(imp: Impairment, fs: float, base_per_lsb: float) -> Compiled:
    """Physical settings -> integer registers. base_per_lsb: base units per input LSB (0.25 for uV, 1 for motion)."""
    u = (1 << FRAC) / base_per_lsb                       # internal units per base unit
    q_lsb = 1.0 if imp.lsb is None else imp.lsb / base_per_lsb
    c_lsb = float(1 << 15) if imp.clip is None else imp.clip / base_per_lsb
    qs = _pow2_shift(q_lsb, "lsb")
    cs = _pow2_shift(c_lsb, "clip")
    if cs > 15 or cs <= qs:
        raise ValueError("need input LSB <= q < C <= 2^15 input LSBs")
    ach: dict = {"lsb": (1 << qs) * base_per_lsb, "clip": (1 << cs) * base_per_lsb, "bits": cs - qs + 1}

    sigma_w = imp.white_density * math.sqrt(fs / 2) * u            # per-sample std, internal units
    white_c = _spt(sigma_w / SIGMA_Z)
    ach["white_density"] = white_c / 2**SCALE_F * SIGMA_Z / u / math.sqrt(fs / 2)
    pink_c = 0
    if imp.pink_corner_hz > 0:
        if not math.isfinite(_VOSS_C):
            raise RuntimeError("Voss coefficient not calibrated yet")
        if sigma_w == 0:
            raise ValueError("pink_corner_hz needs white_density > 0")
        # white one-sided PSD = 2 sigma_w^2 / fs; Voss PSD = C sigma_row^2 fs / f / fs ... equal at f = corner:
        # 2 sigma_w^2 / fs = VOSS_C * sigma_row^2 / corner  ->  sigma_row = sigma_w * sqrt(2 corner / (fs VOSS_C))
        sigma_row = sigma_w * math.sqrt(2 * imp.pink_corner_hz / (fs * _VOSS_C))
        pink_c = _spt(sigma_row / SIGMA_Z)
        ach["pink_corner_hz"] = (pink_c / 2**SCALE_F * SIGMA_Z) ** 2 * fs * _VOSS_C / (2 * (white_c / 2**SCALE_F * SIGMA_Z) ** 2)
    gain_c = _spt(imp.gain_err)
    ach["gain_err"] = gain_c / 2**SCALE_F
    offset_i = int(round(imp.offset * u))
    ach["offset"] = offset_i / u
    drift_c, drift_k = 0, 0
    if imp.drift_rms > 0:
        drift_k = max(1, int(round(math.log2(imp.drift_tau_s * fs))))
        a = 2.0 ** -drift_k
        sigma_in = imp.drift_rms * u * math.sqrt(2 * a - a * a)        # stationary std of d = (1-a) d + w
        drift_c = _spt(sigma_in / SIGMA_Z)
        ach["drift_rms"] = drift_c / 2**SCALE_F * SIGMA_Z / math.sqrt(2 * a - a * a) / u
        ach["drift_tau_s"] = 2**drift_k / fs
    inc, mc = [], []
    for h, amp in enumerate(imp.mains_peak, start=1):
        if h > MAINS_HARMONICS:
            raise ValueError("at most 7 mains harmonics")
        f = h * imp.mains_hz
        att = 1.0 if imp.aa_hz is None else 1.0 / math.sqrt(1.0 + (f / imp.aa_hz) ** (2 * imp.aa_order))
        inc.append(int(round(f / fs * 2**32)) & 0xFFFFFFFF)
        mc.append(_spt(amp * att * u / 32767.0))
        f_alias = abs(f - round(f / fs) * fs)
        ach[f"mains_h{h}"] = {"true_hz": f, "alias_hz": f_alias, "aa_attenuation": att,
                              "peak_at_adc": mc[-1] / 2**SCALE_F * 32767.0 / u}
    hp = lp = None
    if imp.hp_hz:      # 24 fractional bits: corners down to 0.05 Hz at 256 Hz put the poles within 1e-3 of z = 1
        b = design_biquad("afe_hp", "high", imp.hp_hz, fs, frac_bits=AFE_F, b_terms=6, a_terms=8)
        hp = (*b.b, *b.a, b.frac_bits)
        ach["hp_hz_design"] = imp.hp_hz
    if imp.lp_hz:
        b = design_biquad("afe_lp", "low", imp.lp_hz, fs, frac_bits=AFE_F, b_terms=6, a_terms=8)
        lp = (*b.b, *b.a, b.frac_bits)
        ach["lp_hz_design"] = imp.lp_hz
    return Compiled(fs, qs, 1 << (cs - qs), white_c, pink_c, gain_c, offset_i, drift_c, drift_k, inc, mc, hp, lp, ach)


# ----------------------------------------------------------------------------- the chain

@njit(cache=True)
def _voss(z_rows, n, rows):
    """Voss-McCartney: the rows start with the first `rows` values of z_rows; then at sample i (counted from 1)
    row ctz(i) takes the next value (if ctz(i) < rows); output = sum of the held row values."""
    held = np.zeros(rows, dtype=np.int64)
    out = np.empty(n, dtype=np.int64)
    total = np.int64(0)
    for r in range(rows):
        held[r] = z_rows[r]
        total += z_rows[r]
    j = rows
    for i in range(n):
        idx = i + 1
        r = 0
        while (idx & 1) == 0 and r < 63:
            idx >>= 1
            r += 1
        if r < rows:
            total += z_rows[j] - held[r]
            held[r] = z_rows[j]
            j += 1
        out[i] = total
    return out


@njit(cache=True)
def _ou(w, k):
    """d[i] = d[i-1] - round(d[i-1] / 2^k) + w[i], 8 extra fractional bits, output rounded to internal units.
    (A floor shift here would leave a bias of about 2^(k-1) / 256 internal units.)"""
    n = w.shape[0]
    out = np.empty(n, dtype=np.int64)
    d = np.int64(0)
    half = np.int64(1) << (k - 1)
    for i in range(n):
        d = d - ((d + half) >> k) + (w[i] << 8)
        out[i] = (d + 128) >> 8
    return out


@njit(cache=True)
def _mains(n, inc, coef, phase0, table):
    out = np.zeros(n, dtype=np.int64)
    for h in range(inc.shape[0]):
        if coef[h] == 0:
            continue
        ph = phase0[h]
        for i in range(n):
            s = table[ph >> 20]
            out[i] += (s * coef[h] + (np.int64(1) << 23)) >> 24
            ph = (ph + inc[h]) & 0xFFFFFFFF
    return out


@njit(cache=True)
def _clip_quant(v, qs, clip_code):
    n = v.shape[0]
    out = np.empty(n, dtype=np.int64)
    sh = qs + 4
    half = np.int64(1) << (sh - 1)
    nclip = 0
    for i in range(n):
        code = (v[i] + half) >> sh
        if code > clip_code - 1:
            code = clip_code - 1
            nclip += 1
        elif code < -clip_code:
            code = -clip_code
            nclip += 1
        out[i] = code << qs
    return out, nclip


def apply(x: np.ndarray, c: Compiled, key: tuple[int, ...]) -> tuple[np.ndarray, dict]:
    """Impair one channel. x: int16/int64 samples on the input grid. key: (seed, segment, channel) integers that
    select independent noise streams and the mains phases. Returns (int16 samples, stats)."""
    x = np.asarray(x, dtype=np.int64)
    if c.is_identity():
        return x.astype(np.int16), {"clipped": 0}
    n = x.shape[0]
    v = x << FRAC
    if any(c.mains_c):
        st = np.array(stream_state(*key, 4), dtype=np.uint64)
        ph = np.array([int(v_) >> 32 for v_ in _raw(st, MAINS_HARMONICS)], dtype=np.int64)
        v = v + _mains(n, np.array(c.mains_inc, dtype=np.int64), np.array(c.mains_c, dtype=np.int64),
                       ph[: len(c.mains_c)], SIN_TABLE)
    if c.offset_i:
        v = v + c.offset_i
    if c.drift_c:
        z = _gauss_block(np.array(stream_state(*key, 3), dtype=np.uint64), n)
        v = v + _ou(_scale(z, c.drift_c, SCALE_F), c.drift_k)
    if c.white_c:
        z = _gauss_block(np.array(stream_state(*key, 1), dtype=np.uint64), n)
        v = v + _scale(z, c.white_c, SCALE_F)
    if c.pink_c:
        n_upd = VOSS_ROWS + sum(n // (1 << (r + 1)) + 1 for r in range(VOSS_ROWS))
        z = _gauss_block(np.array(stream_state(*key, 2), dtype=np.uint64), n_upd)
        v = v + _voss(_scale(z, c.pink_c, SCALE_F), n, VOSS_ROWS)
    if c.gain_c:
        v = v + _scale(v, c.gain_c, SCALE_F)
    for sec in (c.hp, c.lp):
        if sec is not None:
            b0, b1, b2, a1, a2, frac = sec
            v, _ = biquad_int(v, b0, b1, b2, a1, a2, frac, 48)
    y, nclip = _clip_quant(v, c.q_shift, c.clip_code)
    return y.astype(np.int16), {"clipped": int(nclip)}


@njit(cache=True)
def _raw_nb(state, n):
    out = np.empty(n, dtype=np.uint64)
    s0 = state[0]
    s1 = state[1]
    for i in range(n):
        out[i] = s0 + s1
        s1 = s1 ^ s0
        s0 = ((s0 << np.uint64(24)) | (s0 >> np.uint64(40))) ^ s1 ^ (s1 << np.uint64(16))
        s1 = (s1 << np.uint64(37)) | (s1 >> np.uint64(27))
    state[0] = s0
    state[1] = s1
    return out


def _raw(state: np.ndarray, n: int) -> np.ndarray:
    return _raw_nb(state, n)


def voss_calibration(n: int = 1 << 24, seed: int = 1) -> float:
    """Measure the Voss-McCartney PSD coefficient: mean of S(f) * f / fs over the 1/f region, unit row variance."""
    from scipy.signal import welch
    z = _gauss_block(np.array(stream_state(seed, 0, 0, 2), dtype=np.uint64), n) / SIGMA_Z
    zi = np.round(z * 4096).astype(np.int64)        # integer rows, std 4096
    p = _voss(zi, n, VOSS_ROWS) / 4096.0
    f, s = welch(p, fs=1.0, nperseg=1 << 18)
    band = (f > 2.0 ** -(VOSS_ROWS - 3)) & (f < 2.0 ** -5)
    return float(np.mean(s[band] * f[band]))


def describe(c: Compiled) -> dict:
    d = asdict(c)
    d["bits"] = c.bits
    return d


__all__ = ["Impairment", "Compiled", "compile_impairment", "apply", "stream_state", "xoroshiro128p_py",
           "SIGMA_Z", "N_UNIF", "voss_calibration", "describe", "csd"]
