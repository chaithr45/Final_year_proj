"""Signal-quality statistics for the data audit (float, offline; not the golden model).

The integer artefact flag of the golden model is built in M3 (src/features/).
These functions only describe the raw data.
"""
from __future__ import annotations

import numpy as np


def constant_runs(x: np.ndarray, min_len: int) -> np.ndarray:
    """(start, length) of every run of >= `min_len` identical consecutive samples."""
    x = np.asarray(x)
    if x.size == 0:
        return np.zeros((0, 2), dtype=np.int64)
    change = np.flatnonzero(np.diff(x) != 0) + 1
    starts = np.concatenate(([0], change))
    lengths = np.diff(np.concatenate((starts, [x.size])))
    keep = lengths >= min_len
    return np.stack([starts[keep], lengths[keep]], axis=1).astype(np.int64)


def flatline_summary(x: np.ndarray, fs: float, min_s: float = 1.0) -> dict:
    runs = constant_runs(x, max(2, int(round(min_s * fs))))
    lengths_s = runs[:, 1] / fs if len(runs) else np.zeros(0)
    return {
        "flat_spans": int(len(runs)),
        "flat_s": float(lengths_s.sum()),
        "longest_flat_s": float(lengths_s.max()) if len(runs) else 0.0,
    }


def saturation_fraction(digital: np.ndarray, digital_min: int, digital_max: int) -> float:
    if digital.size == 0:
        return 0.0
    return float(np.mean((digital <= digital_min) | (digital >= digital_max)))


def official_eeg_filter(x_uv: np.ndarray, fs: float) -> np.ndarray:
    """Pre-processing of the official baseline (biomedepi/seizeit2 net/utils.py::pre_process_ch):
    4th-order Butterworth 0.5 Hz high-pass, 60 Hz low-pass, 49.5-50.5 Hz band-stop, zero-phase.
    Applied at the file's own rate (the official code first resamples to 250 Hz)."""
    from scipy import signal

    y = x_uv
    for sos in (
        signal.butter(4, 0.5, "high", fs=fs, output="sos"),
        signal.butter(4, 60.0, "low", fs=fs, output="sos"),
        signal.butter(4, [49.5, 50.5], "bandstop", fs=fs, output="sos"),
    ):
        y = signal.sosfiltfilt(sos, y)
    return y


def window_rms(x: np.ndarray, fs: float, length_s: float = 2.0, hop_s: float = 1.0) -> np.ndarray:
    """RMS of each window on the regular grid (same grid as windows.window_starts)."""
    n_len, n_hop = int(round(length_s * fs)), int(round(hop_s * fs))
    if x.size < n_len:
        return np.zeros(0)
    cs = np.concatenate(([0.0], np.cumsum(np.asarray(x, dtype=np.float64) ** 2)))
    starts = np.arange(0, x.size - n_len + 1, n_hop)
    return np.sqrt((cs[starts + n_len] - cs[starts]) / n_len)


def rms_artefact_mask(rms: np.ndarray, low: float = 13.0, high: float = 150.0) -> np.ndarray:
    """True where the official rule flags an artefact (RMS outside (low, high) uV)."""
    return ~((rms > low) & (rms < high))
