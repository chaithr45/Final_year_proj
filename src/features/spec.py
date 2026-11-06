"""Single source of truth for the golden model's constants, filters and feature list.

spec/fixed_point.md is generated from this file (scripts/make_fixed_point_spec.py) and the
tests check the golden model against the widths declared here.
"""
from __future__ import annotations

import math

from .fixedpoint import design_biquad

# ---------------------------------------------------------------- inputs
FS_BIO = 256                 # EEG/ECG/EMG sampling rate in every SeizeIT2 file (M1 audit)
FS_MOV = 25
BLOCK_BIO = FS_BIO           # 1-s block
BLOCK_MOV = FS_MOV
LSB_BIO = 0.25               # uV per count, int16 -> +/- 8191 uV (max seen in the data: 6665 uV)
LSB_MOV = 2.0 ** -12         # g (or the GYR unit) per count, int16 -> +/- 8
INPUT_BITS = 16

# ---------------------------------------------------------------- arithmetic
FILTER_FRAC_BITS = 16        # biquad coefficient scale 2^16
FILTER_STATE_BITS = 20       # biquad outputs saturate to signed 20 bit
LOG_FRAC = 3                 # integer log2: 3 fractional bits
EMA_GUARD_BITS = 6           # extra fractional bits in EMA registers
CONTEXT_SHIFT = 6            # context EMA: alpha = 2^-6, time constant 64 s (~60 s)
MOV_OFFSET_SHIFT = 5         # motion offset removal EMA: 2^-5 at 25 Hz (cut-off ~0.12 Hz)

# ---------------------------------------------------------------- artefact flag
# Official rule: window RMS outside 13-150 uV. Multiplier-free equivalent: window MAV of the
# official 0.5-60 Hz + 50 Hz notch signal outside RMS * sqrt(2/pi) (exact for Gaussian signals).
ART_RMS_UV = (13.0, 150.0)
_MAV = math.sqrt(2 / math.pi)
ART_LOW_SUM = int(round(ART_RMS_UV[0] * _MAV / LSB_BIO * 2 * BLOCK_BIO))    # window sum threshold
ART_HIGH_SUM = int(round(ART_RMS_UV[1] * _MAV / LSB_BIO * 2 * BLOCK_BIO))

# ---------------------------------------------------------------- ECG R-peak detector
ECG_INTEG = 32               # moving integration 125 ms
ECG_REFRACTORY = 51          # 200 ms
ECG_SPK_SHIFT = 3
ECG_THR_SHIFT = 2
ECG_WARMUP = 2 * FS_BIO
ECG_HR_WINDOW_S = 10
ECG_RR_MIN = 77              # 0.30 s (200 bpm)
ECG_RR_MAX = 512             # 2.0 s (30 bpm)
ECG_MIN_RR = 3
ECG_MAX_GAP_S = 3

# ---------------------------------------------------------------- motion
MOV_ACC_LABELS = ("ECGEMG SD ACC X", "ECGEMG SD ACC Y", "ECGEMG SD ACC Z")
MOV_GYR_LABELS = ("ECGEMG SD GYR A", "ECGEMG SD GYR B", "ECGEMG SD GYR C")
MOV_ACT_THR = int(round(0.05 / LSB_MOV))    # 0.05 units above offset

# ---------------------------------------------------------------- filters
_F = [
    ("eeg_hp05", "high", 0.5, FS_BIO), ("eeg_hp1", "high", 1, FS_BIO), ("eeg_lp4", "low", 4, FS_BIO),
    ("eeg_hp4", "high", 4, FS_BIO), ("eeg_lp8", "low", 8, FS_BIO), ("eeg_hp8", "high", 8, FS_BIO),
    ("eeg_lp13", "low", 13, FS_BIO), ("eeg_hp13", "high", 13, FS_BIO), ("eeg_lp25", "low", 25, FS_BIO),
    ("eeg_hp25", "high", 25, FS_BIO), ("eeg_lp60", "low", 60, FS_BIO), ("eeg_notch50", "notch", 50, FS_BIO),
    ("ecg_hp5", "high", 5, FS_BIO), ("ecg_lp15", "low", 15, FS_BIO),
    ("emg_hp20", "high", 20, FS_BIO), ("emg_lp60", "low", 60, FS_BIO), ("emg_hp60", "high", 60, FS_BIO),
    ("mov_hp1", "high", 1, FS_MOV), ("mov_lp5", "low", 5, FS_MOV),
]
FILTERS = {name: design_biquad(name, kind, f, fs, FILTER_FRAC_BITS) for name, kind, f, fs in _F}
FILTER_USE = {   # biquads instantiated per channel in the datapath
    "eeg": ["eeg_hp1", "eeg_lp25", "eeg_lp4", "eeg_hp4", "eeg_lp8", "eeg_hp8", "eeg_lp13", "eeg_hp13",
            "eeg_lp25", "eeg_hp25", "eeg_lp60", "eeg_hp05", "eeg_lp60", "eeg_notch50"],
    "ecg": ["ecg_hp5", "ecg_lp15"],
    "emg": ["emg_hp20", "emg_lp60", "emg_hp60"],
    "mov": ["mov_hp1", "mov_lp5"],
}

# ---------------------------------------------------------------- features
EEG_CH_FEATURES = ["mav", "ll", "mob", "zc", "ext", "delta", "theta", "alpha", "beta", "hf"]
ECG_FEATURES = ["log_rr", "log_masrd", "quality_bad"]
EMG_FEATURES = ["mav", "ll", "zc", "hl_ratio"]
MOV_FEATURES = ["mag", "jerk", "act", "band"]
PRESENT_NAMES = ["present_ecg", "present_emg", "present_mov_acc", "present_mov_gyr"]

EEG_CROSS = [f"eeg_{k}_{agg}" for k in EEG_CH_FEATURES for agg in ("mean", "max", "absdiff")]
EEG_PER_CH = [f"eeg_ch{i}_{k}" for i in (1, 2) for k in EEG_CH_FEATURES]
BASE = (EEG_CROSS + EEG_PER_CH + ["eeg_sign_agree", "eeg_art_ch1", "eeg_art_ch2"]
        + [f"ecg_{k}" for k in ECG_FEATURES] + [f"emg_{k}" for k in EMG_FEATURES]
        + [f"mov_{s}_{k}" for s in ("acc", "gyr") for k in MOV_FEATURES] + PRESENT_NAMES)
CONTEXT_SOURCES = (EEG_CROSS + ["eeg_sign_agree", "ecg_log_rr", "ecg_log_masrd"]
                   + [f"emg_{k}" for k in EMG_FEATURES] + [f"mov_{s}_{k}" for s in ("acc", "gyr") for k in MOV_FEATURES])
FEATURES = BASE + [f"{k}_ctx" for k in CONTEXT_SOURCES]
FLAG_FEATURES = ["eeg_art_ch1", "eeg_art_ch2", "ecg_quality_bad"] + PRESENT_NAMES


def modality_index(name: str) -> int:
    """Index into the present mask (ecg, emg, mov_acc, mov_gyr), -1 for EEG (always present)."""
    for j, p in enumerate(("ecg_", "emg_", "mov_acc_", "mov_gyr_")):
        if name.startswith(p):
            return j
    return -1


# ---------------------------------------------------------------- declared widths (signed bits)
# Window sums of 512 samples of a 20-bit filter output fit in 29 bits; logs of such sums are < 29*8;
# counts are <= 512. Every feature is stored as int16 in the cache.
def declared_bits(name: str) -> int:
    if name in FLAG_FEATURES:
        return 2                     # 0/1 as signed
    if name.endswith("_zc") or name.endswith("_ext") or name.endswith("sign_agree") or name.endswith("_act") \
            or "_zc_" in name or "_ext_" in name:
        return 11                    # 0..512 (+/- for context)
    return 10                        # log2 values and their differences: |v| < 29*8 = 232 -> 9 bits + sign


FEATURE_BITS = {n: declared_bits(n) + (1 if n.endswith("_ctx") else 0) for n in FEATURES}
