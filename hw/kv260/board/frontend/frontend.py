"""ctypes wrapper of the integer front end in C (seizelut_fe.c), compiled on first use with gcc.

extract(raw, n_win) -> (X, art): X (n_win, 117) int64 features in spec order, art (n_win, 2) uint8 artefact flags.
raw: dict of int16 arrays with keys eeg1, eeg2 (required), ecg, emg, acc_x/y/z, gyr_x/y/z (optional).
"""
from __future__ import annotations

import ctypes
import subprocess
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
_LIB = None


def _lib():
    global _LIB
    if _LIB is None:
        so = HERE / "libseizelut_fe.so"
        src = HERE / "seizelut_fe.c"
        if not so.exists() or so.stat().st_mtime < src.stat().st_mtime:
            subprocess.run(["gcc", "-O2", "-shared", "-fPIC", "-o", str(so), str(src)], check=True,
                           capture_output=True, cwd=HERE)
        lib = ctypes.CDLL(str(so))
        p, i64 = ctypes.c_void_p, ctypes.c_int64
        lib.fe_extract.argtypes = [i64, p, p, i64, p, i64, p, i64, p, p, p, i64, p, p, p, i64, p, p]
        lib.fe_extract.restype = ctypes.c_int
        lib.fe_n_features.restype = ctypes.c_int
        _LIB = lib
    return _LIB


def extract(raw: dict, n_win: int):
    lib = _lib()
    nf = lib.fe_n_features()
    arrs = {k: np.ascontiguousarray(v, dtype=np.int16) for k, v in raw.items() if v is not None}

    def ptr(k):
        return arrs[k].ctypes.data if k in arrs else None

    def n(*ks):
        return int(min(len(arrs[k]) for k in ks)) if all(k in arrs for k in ks) else 0

    X = np.zeros((n_win, nf), dtype=np.int64)
    art = np.zeros((n_win, 2), dtype=np.uint8)
    rc = lib.fe_extract(n_win, ptr("eeg1"), ptr("eeg2"), n("eeg1", "eeg2"), ptr("ecg"), n("ecg"), ptr("emg"), n("emg"),
                        ptr("acc_x"), ptr("acc_y"), ptr("acc_z"), n("acc_x", "acc_y", "acc_z"),
                        ptr("gyr_x"), ptr("gyr_y"), ptr("gyr_z"), n("gyr_x", "gyr_y", "gyr_z"),
                        X.ctypes.data, art.ctypes.data)
    if rc != 0:
        raise RuntimeError(f"fe_extract failed ({rc})")
    return X, art
