"""Golden fixed-point feature model (Section 5) and its float twin.

One function, two modes:
  mode="int"   the hardware reference: int16 inputs, SPT biquads, integer log2, shifts.
  mode="float" the same structure in float64 with the unquantised filters and exact log2,
               used only to show that integerisation does not cost detection performance.

Timing: blocks of 1 s (256 samples at 256 Hz, 25 at 25 Hz). Window t covers seconds
[t, t+2) and its features are available at the end of second t+1 (causal). Window sums
are the sum of two 1-s block accumulators; a 2 s mean is a shift by 9 at 256 Hz.

Feature order and meaning: FEATURES in src/features/spec.py.
"""
from __future__ import annotations

import numpy as np

from ..data.montage import eeg_channel_pair
from . import spec as S
from .fixedpoint import IntBiquad, ilog2
from .kernels import biquad_int, ema_context_int, ema_highpass_int, rpeak_detect


# ----------------------------------------------------------------- input conversion

def to_fixed(edf, label: str, lsb: float, bits: int = 16) -> np.ndarray:
    """Physical units -> integer at `lsb` per count, rounded, saturated (done by the replay
    software in Phase 2, so the FPGA sees a fixed-gain stream)."""
    x = edf.physical(label)
    if edf.header.signal(label).physical_dim.lower().startswith("10e-3"):
        x = x * 1e-3
    q = np.round(x / lsb)
    lim = (1 << (bits - 1)) - 1
    return np.clip(q, -lim - 1, lim).astype(np.int64)


# ----------------------------------------------------------------- primitives

class _Ops:
    def __init__(self, mode: str):
        assert mode in ("int", "float")
        self.mode = mode
        self.sat = {}

    def filt(self, x, bq: IntBiquad):
        if self.mode == "int":
            y, n = biquad_int(x, *bq.b, *bq.a, bq.frac_bits, S.FILTER_STATE_BITS)
            self.sat[bq.name] = self.sat.get(bq.name, 0) + int(n)
            return y
        from scipy.signal import lfilter
        return lfilter(bq.float_sos[:3], bq.float_sos[3:], x)

    def log(self, v):
        if self.mode == "int":
            return ilog2(v)
        v = np.asarray(v, dtype=np.float64)
        return np.where(v > 1, np.log2(np.maximum(v, 1)) * (1 << S.LOG_FRAC), 0.0)

    def hp_offset(self, x, k):
        if self.mode == "int":
            return ema_highpass_int(x, k, S.EMA_GUARD_BITS)
        y = np.empty_like(x, dtype=np.float64)
        m = float(x[0]) if len(x) else 0.0
        a = 2.0 ** -k
        for i, v in enumerate(x):      # float twin of the shift EMA (motion only: 25 Hz, short)
            y[i] = v - m
            m += (v - m) * a
        return y

    def mean2(self, a, b):
        return (a + b) >> 1 if self.mode == "int" else (a + b) / 2


def block_sum_abs(x, block):
    nb = len(x) // block
    return np.abs(x[: nb * block]).reshape(nb, block).sum(axis=1)


def block_stats(x, block):
    """Per 1-s block: sum|x|, line length sum|dx|, zero crossings, local extrema (slope sign changes)."""
    nb = len(x) // block
    x = x[: nb * block]
    d = np.diff(x, prepend=x[:1])
    s = x >= 0
    zc = np.concatenate(([False], s[1:] != s[:-1]))
    sl = np.sign(d)
    idx = np.where(sl != 0, np.arange(len(sl)), -1)
    last = np.maximum.accumulate(idx)
    prev_last = np.concatenate(([-1], last[:-1]))
    prev_sl = np.where(prev_last >= 0, sl[np.maximum(prev_last, 0)], 0)
    ext = (sl != 0) & (prev_sl != 0) & (sl != prev_sl)
    r = lambda a: a.reshape(nb, block).sum(axis=1)
    return r(np.abs(x)), r(np.abs(d)), r(zc.astype(np.int64)), r(ext.astype(np.int64))


def win(a):
    """Two-block window sums: window t = blocks t and t+1."""
    return a[:-1] + a[1:]


def _fit(a, n, fill=0):
    out = np.full(n, fill, dtype=a.dtype if len(a) else np.int64)
    m = min(n, len(a))
    out[:m] = a[:m]
    return out


# ----------------------------------------------------------------- modalities

def eeg_channel_features(ops, q):
    F = S.FILTERS
    hp1 = ops.filt(q, F["eeg_hp1"])
    xbp = ops.filt(hp1, F["eeg_lp25"])
    bands = {
        "delta": ops.filt(hp1, F["eeg_lp4"]),
        "theta": ops.filt(ops.filt(q, F["eeg_hp4"]), F["eeg_lp8"]),
        "alpha": ops.filt(ops.filt(q, F["eeg_hp8"]), F["eeg_lp13"]),
        "beta": ops.filt(ops.filt(q, F["eeg_hp13"]), F["eeg_lp25"]),
        "hf": ops.filt(ops.filt(q, F["eeg_hp25"]), F["eeg_lp60"]),
    }
    broad = ops.filt(ops.filt(ops.filt(q, F["eeg_hp05"]), F["eeg_lp60"]), F["eeg_notch50"])
    B = S.BLOCK_BIO
    mav, ll, zc, ext = block_stats(xbp, B)
    out = {"mav": ops.log(win(mav)), "ll": ops.log(win(ll))}
    out["mob"] = out["ll"] - out["mav"]
    out["zc"], out["ext"] = win(zc), win(ext)
    for k, v in bands.items():
        out[k] = ops.log(win(block_sum_abs(v, B)))
    wb = win(block_sum_abs(broad, B))
    art = (wb < S.ART_LOW_SUM) | (wb > S.ART_HIGH_SUM)
    return out, art, xbp


def ecg_features(ops, q, n_win):
    F = S.FILTERS
    e = ops.filt(ops.filt(q, F["ecg_hp5"]), F["ecg_lp15"])
    e_int = e if ops.mode == "int" else np.round(e).astype(np.int64)
    beats = rpeak_detect(e_int, S.ECG_INTEG, S.ECG_REFRACTORY, S.ECG_SPK_SHIFT, S.ECG_THR_SHIFT, S.ECG_WARMUP)
    fs = S.FS_BIO
    rr = np.diff(beats)
    rr_t = beats[1:]                    # time stamp of each RR interval = its closing beat
    drr = np.abs(np.diff(rr))
    drr_t = rr_t[1:]
    ends = (np.arange(n_win) + 2) * fs  # window t ends at second t+2
    lo = ends - S.ECG_HR_WINDOW_S * fs

    def wsum(vals, ts):
        c = np.concatenate(([0], np.cumsum(vals)))
        i1 = np.searchsorted(ts, ends, side="right")
        i0 = np.searchsorted(ts, lo, side="right")
        return c[i1] - c[i0], i1 - i0

    s_rr, n_rr = wsum(rr, rr_t)
    s_d, n_d = wsum(drr, drr_t)
    bad = (rr < S.ECG_RR_MIN) | (rr > S.ECG_RR_MAX)
    n_bad, _ = wsum(bad.astype(np.int64), rr_t)
    last = np.searchsorted(beats, ends, side="right") - 1
    since = np.where(last >= 0, ends - beats[np.maximum(last, 0)], ends)
    quality_bad = (n_rr < S.ECG_MIN_RR) | (n_bad > 0) | (since > S.ECG_MAX_GAP_S * fs)
    log_rr = np.where(n_rr > 0, ops.log(s_rr) - ops.log(n_rr), 0)
    log_masrd = np.where(n_d > 0, ops.log(np.maximum(s_d, 1)) - ops.log(np.maximum(n_d, 1)), 0)
    return {"log_rr": log_rr, "log_masrd": log_masrd, "quality_bad": quality_bad.astype(np.int64)}, beats


def emg_features(ops, q):
    F = S.FILTERS
    g = ops.filt(q, F["emg_hp20"])
    B = S.BLOCK_BIO
    mav, ll, zc, _ = block_stats(g, B)
    low = win(block_sum_abs(ops.filt(g, F["emg_lp60"]), B))
    high = win(block_sum_abs(ops.filt(g, F["emg_hp60"]), B))
    return {"mav": ops.log(win(mav)), "ll": ops.log(win(ll)), "zc": win(zc),
            "hl_ratio": ops.log(high) - ops.log(low)}


def motion_features(ops, axes):
    """axes: list of 3 int arrays (one sensor, 25 Hz)."""
    F = S.FILTERS
    B = S.BLOCK_MOV
    hp = [ops.hp_offset(a, S.MOV_OFFSET_SHIFT) for a in axes]
    l1 = np.abs(hp[0]) + np.abs(hp[1]) + np.abs(hp[2])
    nb = len(l1) // B
    jerk = sum(block_stats(h, B)[1] for h in hp)
    act = (l1[: nb * B] > S.MOV_ACT_THR).reshape(nb, B).sum(axis=1).astype(np.int64)
    band = sum(block_sum_abs(ops.filt(ops.filt(a, F["mov_hp1"]), F["mov_lp5"]), B) for a in axes)
    return {"mag": ops.log(win(block_sum_abs(l1, B))), "jerk": ops.log(win(jerk)), "act": win(act),
            "band": ops.log(win(band))}


# ----------------------------------------------------------------- run level

def extract(signals: dict, n_seconds: int, mode: str = "int") -> dict:
    """signals: {'eeg': EdfData, 'ecg': EdfData|None, 'emg': ..., 'mov': ...}.

    Returns dict with 'X' (n_win, n_features) int64 (or float64), 'artefact' (n_win, 2) bool,
    'present' (n_win, 4) bool, 'names', 'sat' (saturation counts), 'beats'.
    """
    ops = _Ops(mode)
    n_win = n_seconds - 1
    cols: dict[str, np.ndarray] = {}

    eeg = signals["eeg"]
    ch = eeg_channel_pair(eeg.labels)
    per, arts, xbps = [], [], []
    for c in ch:
        q = to_fixed(eeg, c, S.LSB_BIO)
        f, art, xbp = eeg_channel_features(ops, q if mode == "int" else q.astype(np.float64))
        per.append({k: _fit(v, n_win) for k, v in f.items()})
        arts.append(_fit(art, n_win, False))
        xbps.append(xbp)
    for k in S.EEG_CH_FEATURES:
        a, b = per[0][k], per[1][k]
        cols[f"eeg_{k}_mean"] = ops.mean2(a, b)
        cols[f"eeg_{k}_max"] = np.maximum(a, b)
        cols[f"eeg_{k}_absdiff"] = np.abs(a - b)
    for i in range(2):
        for k in S.EEG_CH_FEATURES:
            cols[f"eeg_ch{i + 1}_{k}"] = per[i][k]
    s = (xbps[0] >= 0) == (xbps[1] >= 0)
    nb = len(s) // S.BLOCK_BIO
    cols["eeg_sign_agree"] = _fit(win(s[: nb * S.BLOCK_BIO].reshape(nb, -1).sum(axis=1).astype(np.int64)), n_win)
    artefact = np.stack(arts, axis=1)
    cols["eeg_art_ch1"], cols["eeg_art_ch2"] = artefact[:, 0].astype(np.int64), artefact[:, 1].astype(np.int64)

    present = np.zeros((n_win, 4), dtype=bool)
    beats = np.zeros(0, dtype=np.int64)
    # ECG
    ecg = signals.get("ecg")
    if ecg is not None and ecg.labels:
        f, beats = ecg_features(ops, to_fixed(ecg, ecg.labels[0], S.LSB_BIO), n_win)
        n_ok = min(n_win, len(ecg.digital[ecg.labels[0]]) // S.FS_BIO - 1)
        present[:n_ok, 0] = True
        for k, v in f.items():
            cols[f"ecg_{k}"] = _fit(v, n_win)
    for k in S.ECG_FEATURES:
        cols.setdefault(f"ecg_{k}", np.zeros(n_win, dtype=np.int64))
    # EMG
    emg = signals.get("emg")
    if emg is not None and emg.labels:
        q = to_fixed(emg, emg.labels[0], S.LSB_BIO)
        f = emg_features(ops, q if mode == "int" else q.astype(np.float64))
        present[: min(n_win, len(q) // S.FS_BIO - 1), 1] = True
        for k, v in f.items():
            cols[f"emg_{k}"] = _fit(v, n_win)
    for k in S.EMG_FEATURES:
        cols.setdefault(f"emg_{k}", np.zeros(n_win, dtype=np.int64))
    # Motion (chest module)
    mov = signals.get("mov")
    for j, (sensor, labels) in enumerate((("acc", S.MOV_ACC_LABELS), ("gyr", S.MOV_GYR_LABELS))):
        if mov is not None and all(lb in mov.labels for lb in labels):
            axes = [to_fixed(mov, lb, S.LSB_MOV) for lb in labels]
            if mode == "float":
                axes = [a.astype(np.float64) for a in axes]
            f = motion_features(ops, axes)
            present[: min(n_win, len(axes[0]) // S.FS_MOV - 1), 2 + j] = True
            for k, v in f.items():
                cols[f"mov_{sensor}_{k}"] = _fit(v, n_win)
        for k in S.MOV_FEATURES:
            cols.setdefault(f"mov_{sensor}_{k}", np.zeros(n_win, dtype=np.int64))

    # Missing-modality rule: absent -> feature bits zero
    for j, prefix in enumerate(("ecg_", "emg_", "mov_acc_", "mov_gyr_")):
        for k in list(cols):
            if k.startswith(prefix):
                cols[k] = np.where(present[:, j], cols[k], 0)
    for j, name in enumerate(S.PRESENT_NAMES):
        cols[name] = present[:, j].astype(np.int64)

    # Context: difference from a causal 64-s EMA (shift 6) of the same recording
    base = np.stack([cols[k] for k in S.CONTEXT_SOURCES], axis=1)
    valid_by_src = np.stack([present[:, S.modality_index(k)] if S.modality_index(k) >= 0 else np.ones(n_win, bool)
                             for k in S.CONTEXT_SOURCES], axis=1)
    if mode == "int":
        ctx = np.zeros_like(base)
        for j in range(base.shape[1]):     # per column so each modality's validity is respected
            ctx[:, j] = ema_context_int(base[:, j:j + 1].astype(np.int64), valid_by_src[:, j],
                                        S.CONTEXT_SHIFT, S.EMA_GUARD_BITS)[:, 0]
    else:
        ctx = np.zeros_like(base, dtype=np.float64)
        a = 2.0 ** -S.CONTEXT_SHIFT
        for j in range(base.shape[1]):
            e, started = 0.0, False
            for t in range(n_win):
                if not valid_by_src[t, j]:
                    continue
                if not started:
                    e, started = float(base[t, j]), True
                ctx[t, j] = base[t, j] - e
                e += (base[t, j] - e) * a
    for j, k in enumerate(S.CONTEXT_SOURCES):
        cols[f"{k}_ctx"] = ctx[:, j]

    X = np.stack([cols[k] for k in S.FEATURES], axis=1)
    if mode == "int":
        X = X.astype(np.int64)
    return {"X": X, "artefact": artefact, "present": present, "names": list(S.FEATURES),
            "sat": dict(ops.sat), "beats": beats}
