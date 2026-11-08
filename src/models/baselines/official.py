"""Data handling of the official SeizeIT2 deep-learning baseline (biomedepi/seizeit2).

Ported from net/utils.py (pre-processing) and net/key_generator.py (segment keys).
Used only to reproduce the published ChronoNet baseline; our own pipeline is in
src/features/.
"""
from __future__ import annotations

import random

import numpy as np

from ...data.montage import eeg_channel_pair

FS = 250          # official working rate (files are 256 Hz and get resampled)
FRAME = 2         # s
STRIDE = 1        # s, background
STRIDE_S = 0.5    # s, seizure (training only)
BOUNDARY = 0.5
FACTOR = 5


def preprocess_channel(x: np.ndarray, fs_in: float, fs_out: int = FS) -> np.ndarray:
    """net/utils.py::pre_process_ch: FFT resample, Butterworth(4) 0.5 Hz HP, 60 Hz LP,
    49.5-50.5 Hz band-stop, all zero-phase (filtfilt, non-causal)."""
    from scipy import signal
    x = np.asarray(x, dtype=np.float64)
    if fs_out != fs_in:
        x = signal.resample(x, int(fs_out * len(x) / fs_in))
    b, a = signal.butter(4, 0.5 / (fs_out / 2), "high")
    x = signal.filtfilt(b, a, x)
    b, a = signal.butter(4, 60 / (fs_out / 2), "low")
    x = signal.filtfilt(b, a, x)
    b, a = signal.butter(4, [49.5 / (fs_out / 2), 50.5 / (fs_out / 2)], "bandstop")
    return signal.filtfilt(b, a, x)


def preprocess_eeg(edf_data) -> tuple[np.ndarray, np.ndarray]:
    """net/utils.py::apply_preprocess_eeg: returns (focal, cross) channels at 250 Hz, in uV."""
    ch1, ch2 = eeg_channel_pair(edf_data.labels)
    return (preprocess_channel(edf_data.physical(ch1), edf_data.fs[ch1]),
            preprocess_channel(edf_data.physical(ch2), edf_data.fs[ch2]))


def window_rms(x: np.ndarray, fs: int = FS, frame: int = 2, step: int = 1) -> np.ndarray:
    """RMS per 2 s window, 1 s step, as in net/main_func.py::evaluate."""
    n, h = frame * fs, step * fs
    if len(x) < n:
        return np.zeros(0)
    cs = np.concatenate(([0.0], np.cumsum(x.astype(np.float64) ** 2)))
    starts = np.arange(0, len(x) - n + 1, h)
    return np.sqrt((cs[starts + n] - cs[starts]) / n)


def subsample_keys(rec_events: list[tuple[int, list[tuple[float, float]], float]], rng: random.Random,
                   frame=FRAME, stride=STRIDE, stride_s=STRIDE_S, boundary=BOUNDARY, factor=FACTOR):
    """Port of net/key_generator.py::generate_data_keys_subsample.

    rec_events: (recording index, seizure events [(start, stop)], recording duration s).
    Returns shuffled keys [rec_idx, start_s, stop_s, label]: every seizure segment
    (0.5 s stride) plus factor x as many random background segments (1 s stride).
    """
    seg_s, seg_ns = [], []
    for idx, events, rec_dur in rec_events:
        if not events:
            n = int(np.floor((np.floor(rec_dur) - frame) / stride))
            st = np.arange(0, n) * stride
            seg_ns.extend(np.column_stack(([idx] * n, st, st + frame, np.zeros(n))))
            continue
        for e, ev in enumerate(events):
            n = int(((ev[1] + frame * (1 - boundary)) - (ev[0] - frame * (1 - boundary)) - frame) / stride_s)
            st = np.arange(0, n) * stride_s + ev[0] - frame * (1 - boundary)
            seg_s.extend(np.column_stack(([idx] * n, st, st + frame, np.ones(n))))
            if e == 0:
                n = max(int(np.floor(ev[0] / stride) - 1), 0)
                st = np.arange(0, n) * stride
            else:
                n = max(int(np.floor((ev[0] - events[e - 1][1]) / stride) - 1), 0)
                st = np.arange(0, n) * stride + events[e - 1][1]
            seg_ns.extend(np.column_stack(([idx] * n, st, st + frame, np.zeros(n))))
            if e == len(events) - 1:
                n = max(int(np.floor((np.floor(rec_dur) - ev[1]) / stride) - 1), 0)
                st = np.arange(0, n) * stride + ev[1]
                seg_ns.extend(np.column_stack(([idx] * n, st, st + frame, np.zeros(n))))
    out = list(seg_s) + rng.sample(seg_ns, min(len(seg_ns), factor * len(seg_s)))
    rng.shuffle(out)
    return np.array(out, dtype=np.float64).reshape(-1, 4)


def cut_windows(chans: tuple[np.ndarray, np.ndarray], starts_s: np.ndarray, fs: int = FS, frame: int = FRAME) -> np.ndarray:
    """(n, frame*fs, 2) float32; out-of-range windows are zero, like SegmentedGenerator."""
    n_len = frame * fs
    out = np.zeros((len(starts_s), n_len, 2), dtype=np.float32)
    total = len(chans[0])
    for i, s in enumerate(starts_s):
        a = int(s * fs)
        if a < 0 or a + n_len > total:
            continue
        out[i, :, 0] = chans[0][a:a + n_len]
        out[i, :, 1] = chans[1][a:a + n_len]
    return out


def sequential_labels(n_windows: int, events: list[tuple[float, float]], frame=FRAME, stride=STRIDE) -> np.ndarray:
    """Labels of the 1 s prediction grid. For integer-second annotations (all of SeizeIT2,
    see the M2 notes) this equals generate_data_keys_sequential: window [s, s+2) is
    seizure when s in [onset-1, end-1], i.e. >= 50 % overlap."""
    starts = np.arange(n_windows) * stride
    lab = np.zeros(n_windows, dtype=np.uint8)
    for a, b in events:
        lab[(starts >= a - stride) & (starts <= b - stride)] = 1
    return lab
