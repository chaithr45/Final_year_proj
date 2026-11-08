"""Sample-level integer kernels of the golden model (numba-compiled; pure-Python fallback).

All arithmetic is int64 with explicit rounding shifts and saturation, mirroring the RTL
of Phase 2 (one adder tree per biquad, shift-add constant products).
"""
from __future__ import annotations

import numpy as np

try:
    from numba import njit
except ImportError:  # pragma: no cover - slow fallback keeps CI working without numba
    def njit(*a, **k):
        if a and callable(a[0]):
            return a[0]
        return lambda f: f


@njit(cache=True)
def biquad_int(x, b0, b1, b2, a1, a2, frac, sat_bits):
    """Direct form I biquad with second-order error feedback (noise shaping).

    acc = b0 x + b1 x1 + b2 x2 - a1 y1 - a2 y2 + 2 e1 - e2;  y = acc >> frac (floor);
    e = acc - (y << frac) (the discarded low bits). Without error feedback the rounding
    error of the low-cut high-passes is amplified ~1700x at DC (poles near z = 1); with it
    the error stays below one LSB. Cost: two frac-bit registers and two adders.
    Returns (y, number of saturation events)."""
    n = x.shape[0]
    y = np.empty(n, dtype=np.int64)
    lim = (1 << (sat_bits - 1)) - 1
    x1 = 0
    x2 = 0
    y1 = 0
    y2 = 0
    e1 = 0
    e2 = 0
    nsat = 0
    for i in range(n):
        x0 = x[i]
        acc = b0 * x0 + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2 + 2 * e1 - e2
        v = acc >> frac
        e2 = e1
        e1 = acc - (v << frac)
        if v > lim:
            v = lim
            nsat += 1
        elif v < -lim - 1:
            v = -lim - 1
            nsat += 1
        y[i] = v
        x2 = x1
        x1 = x0
        y2 = y1
        y1 = v
    return y, nsat


@njit(cache=True)
def ema_highpass_int(x, k, guard):
    """Offset removal: y = x - m, m += (x - m) >> k, with `guard` extra fractional bits in m.
    Cut-off about fs / (2 pi 2^k)."""
    n = x.shape[0]
    y = np.empty(n, dtype=np.int64)
    m = x[0] << guard if n > 0 else 0
    for i in range(n):
        xi = x[i] << guard
        y[i] = (xi - m) >> guard
        m += (xi - m) >> k
    return y


@njit(cache=True)
def block_stats(x, block):
    """Per block of `block` samples: sum|x|, sum|x[n]-x[n-1]|, zero crossings, local extrema.
    State (previous sample, previous sign, previous slope sign) carries across blocks."""
    nb = x.shape[0] // block
    mav = np.zeros(nb, dtype=np.int64)
    ll = np.zeros(nb, dtype=np.int64)
    zc = np.zeros(nb, dtype=np.int64)
    ext = np.zeros(nb, dtype=np.int64)
    prev = x[0] if x.shape[0] > 0 else 0
    psign = 1 if prev >= 0 else -1
    pslope = 0
    for b in range(nb):
        for j in range(block):
            v = x[b * block + j]
            mav[b] += abs(v)
            d = v - prev
            ll[b] += abs(d)
            s = 1 if v >= 0 else -1
            if s != psign:
                zc[b] += 1
            psign = s
            if d != 0:
                sl = 1 if d > 0 else -1
                if pslope != 0 and sl != pslope:
                    ext[b] += 1
                pslope = sl
            prev = v
    return mav, ll, zc, ext


@njit(cache=True)
def block_abs_sum(x, block):
    nb = x.shape[0] // block
    out = np.zeros(nb, dtype=np.int64)
    for b in range(nb):
        s = 0
        for j in range(block):
            s += abs(x[b * block + j])
        out[b] = s
    return out


@njit(cache=True)
def block_sign_agree(x1, x2, block):
    nb = min(x1.shape[0], x2.shape[0]) // block
    out = np.zeros(nb, dtype=np.int64)
    for b in range(nb):
        c = 0
        for j in range(block):
            i = b * block + j
            if (x1[i] >= 0) == (x2[i] >= 0):
                c += 1
        out[b] = c
    return out


@njit(cache=True)
def block_count_above(x, thr, block):
    nb = x.shape[0] // block
    out = np.zeros(nb, dtype=np.int64)
    for b in range(nb):
        c = 0
        for j in range(block):
            if x[b * block + j] > thr:
                c += 1
        out[b] = c
    return out


@njit(cache=True)
def rpeak_detect(e, integ, refractory, spk_shift, thr_shift, warmup):
    """Integer R-peak detector on a band-passed ECG (Pan-Tompkins style, multiplier-free).

    d[n] = e[n] - e[n-2]; r = |d|; m = moving sum of r over `integ` samples.
    A peak of m is accepted as a beat when it exceeds thr = npk + ((spk - npk) >> thr_shift)
    and at least `refractory` samples passed since the last beat. spk/npk are running
    peak levels updated by >> spk_shift, initialised over the first `warmup` samples.
    Returns beat sample indices.
    """
    n = e.shape[0]
    beats = np.empty(n // max(refractory, 1) + 1, dtype=np.int64)
    nbeats = 0
    m = 0
    r_hist = np.zeros(integ, dtype=np.int64)
    spk = 0
    npk = 0
    last_beat = -refractory
    cand = 0
    cand_i = -1
    rising = False
    prev_m = 0
    for i in range(n):
        d = e[i] - (e[i - 2] if i >= 2 else 0)
        r = abs(d)
        m += r - r_hist[i % integ]
        r_hist[i % integ] = r
        if i < warmup:               # warm-up: initial signal level = max of m, noise = 1/8 of it
            if m > spk:
                spk = m
                npk = spk >> 3
            prev_m = m
            continue
        if m > prev_m:
            rising = True
            if m > cand:
                cand = m
                cand_i = i
        elif rising and m < prev_m:   # local maximum of m just passed
            rising = False
            thr = npk + ((spk - npk) >> thr_shift)
            if cand > thr and cand_i - last_beat >= refractory:
                beats[nbeats] = cand_i
                nbeats += 1
                last_beat = cand_i
                spk += (cand - spk) >> spk_shift
            else:
                npk += (cand - npk) >> spk_shift
            cand = 0
        prev_m = m
    return beats[:nbeats]


@njit(cache=True)
def ema_context_int(f, valid, k, guard):
    """Context features: ctx[t] = f[t] - ema[t-1], ema[t] = ema[t-1] + ((f[t] << guard) - ema[t-1]) >> k.
    The EMA starts at the first valid value (ctx = 0 there) and holds while invalid (ctx = 0)."""
    n, nf = f.shape
    ctx = np.zeros((n, nf), dtype=np.int64)
    for j in range(nf):
        started = False
        e = 0
        for t in range(n):
            if not valid[t]:
                continue
            v = f[t, j] << guard
            if not started:
                e = v
                started = True
            ctx[t, j] = f[t, j] - (e >> guard)
            e += (v - e) >> k
    return ctx
