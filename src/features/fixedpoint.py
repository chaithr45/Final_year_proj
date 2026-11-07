"""Fixed-point building blocks of the golden model (Section 5, spec/fixed_point.md).

Everything here maps to adders, shifters, comparators and counters:
* coefficients are sums of a few signed powers of two (SPT/CSD), so x*c is a shift-add;
* biquads use direct form I, integer products, one rounding shift by F, saturation;
* log2 is the leading-one position plus a few mantissa bits.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

LOG_FRAC = 3   # fractional bits of the integer log2


def ilog2(v: np.ndarray, frac: int = LOG_FRAC) -> np.ndarray:
    """Integer log2 with `frac` fractional bits: 8*floor(log2 v) + next 3 mantissa bits.
    ilog2(0) = ilog2(1) = 0. Vectorised, exact for v < 2^62."""
    v = np.asarray(v, dtype=np.int64)
    out = np.zeros(v.shape, dtype=np.int64)
    pos = v > 0
    vp = v[pos]
    p = np.floor(np.log2(vp.astype(np.float64))).astype(np.int64)
    # guard against float rounding at exact powers of two
    p = np.where((np.left_shift(np.int64(1), p) > vp), p - 1, p)
    p = np.where((np.left_shift(np.int64(1), p + 1) <= vp), p + 1, p)
    mant = np.where(p >= frac, np.right_shift(vp, np.maximum(p - frac, 0)), np.left_shift(vp, np.maximum(frac - p, 0)))
    mant = mant & ((1 << frac) - 1)
    out[pos] = (p << frac) + mant
    return out


def csd(value: int) -> list[tuple[int, int]]:
    """Canonical signed-digit decomposition of an integer: [(sign, shift), ...], MSB first."""
    digits, k, v = [], 0, int(value)
    while v != 0:
        if v & 1:
            d = 2 - (v & 3)        # +1 or -1
            v -= d
            digits.append((d, k))
        v >>= 1
        k += 1
    return sorted(digits, key=lambda t: -t[1])


def spt_quantize(c: float, frac_bits: int, max_terms: int) -> int:
    """Round c * 2^frac_bits to an integer with at most `max_terms` signed powers of two."""
    target = c * (1 << frac_bits)
    v = int(round(target))
    terms = csd(v)
    if len(terms) <= max_terms:
        return v
    # greedy: keep the largest terms, then re-fit the residual with what is left
    out = 0
    for _ in range(max_terms):
        r = target - out
        if r == 0:
            break
        k = int(round(np.log2(abs(r)))) if abs(r) >= 1 else 0
        out += int(np.sign(r)) * (1 << k)
    return out


def spt_terms(v: int) -> int:
    return len(csd(v))


@dataclass(frozen=True)
class IntBiquad:
    """y = (b0 x + b1 x1 + b2 x2 - a1 y1 - a2 y2 + 2 e1 - e2) >> F with second-order error
    feedback of the discarded bits e, saturated (see kernels.biquad_int)."""
    name: str
    b: tuple[int, int, int]
    a: tuple[int, int]             # a1, a2 (a0 = 2^F)
    frac_bits: int
    float_sos: tuple[float, ...]   # the unquantised design (b0 b1 b2 1 a1 a2) for the float twin

    @property
    def adders(self) -> int:
        """Shift-add terms = adders needed for the five constant products (plus 4 to sum them)."""
        return sum(spt_terms(c) for c in (*self.b, *self.a)) + 4 + 2   # +2: error feedback


def design_biquad(name: str, kind: str, freq: float, fs: float, frac_bits: int = 16,
                  b_terms: int = 4, a_terms: int = 5) -> IntBiquad:
    """2nd-order Butterworth section ('low', 'high', or 'notch' with freq=centre), SPT-quantised."""
    from scipy import signal
    if kind == "notch":
        b, a = signal.iirnotch(freq, Q=freq / 1.0, fs=fs)
    else:
        b, a = signal.butter(2, freq, kind, fs=fs)
    b, a = b / a[0], a / a[0]
    if kind in ("low", "high"):
        # keep the double zero exactly at z=-1 (low-pass) or z=+1 (high-pass): b = b0 * (1, -/+2, 1)
        q0 = spt_quantize(b[0], frac_bits, b_terms)
        qb = (q0, 2 * q0 if kind == "low" else -2 * q0, q0)
    else:
        qb = tuple(spt_quantize(x, frac_bits, b_terms) for x in b)
    qa = tuple(spt_quantize(x, frac_bits, a_terms) for x in a[1:])
    return IntBiquad(name, qb, qa, frac_bits, tuple(float(x) for x in (*b, *a)))


def biquad_response_db(bq: IntBiquad, freqs: np.ndarray, fs: float, quantised: bool = True) -> np.ndarray:
    from scipy import signal
    if quantised:
        s = 1 << bq.frac_bits
        b = np.array(bq.b) / s
        a = np.array([1.0, bq.a[0] / s, bq.a[1] / s])
    else:
        b, a = np.array(bq.float_sos[:3]), np.array(bq.float_sos[3:])
    _, h = signal.freqz(b, a, worN=freqs, fs=fs)
    return 20 * np.log10(np.maximum(np.abs(h), 1e-12))


def is_stable(bq: IntBiquad) -> bool:
    s = 1 << bq.frac_bits
    return bool(np.all(np.abs(np.roots([1.0, bq.a[0] / s, bq.a[1] / s])) < 1))


def saturate(x: np.ndarray, bits: int) -> np.ndarray:
    lim = (1 << (bits - 1)) - 1
    return np.clip(x, -lim - 1, lim)
