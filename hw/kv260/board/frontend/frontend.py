"""ctypes wrapper of the integer front end in C (seizelut_fe.c, seizelut_fe_stream.c), compiled on first use with gcc.

extract(raw, n_win) -> (X, art): X (n_win, 117) int64 features in spec order, art (n_win, 2) uint8 artefact flags.
raw: dict of int16 arrays with keys eeg1, eeg2 (required), ecg, emg, acc_x/y/z, gyr_x/y/z (optional).

Stream(): the same front end one second at a time (live demo). push(block) -> (window index or None, X row, art,
viz), where block holds one second of every present sensor (256 samples per biopotential channel, 25 per motion
axis) and viz the second's filtered signals, R-peaks and motion magnitude. The window of seconds [w, w+2) comes out
one second after it ends (R-peak look-ahead); flush() returns the last one.
"""
from __future__ import annotations

import ctypes
import subprocess
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
_LIB = None


def _prebuilt() -> Path | None:
    """Library built in the project repository for this platform (used when there is no gcc here)."""
    import platform
    import sys
    mach = platform.machine().lower()
    if sys.platform.startswith("win"):
        p = HERE / "prebuilt" / "windows-amd64" / "seizelut_fe.dll"
    elif sys.platform.startswith("linux") and mach in ("x86_64", "amd64"):
        p = HERE / "prebuilt" / "linux-x86_64" / "libseizelut_fe.so"
    elif sys.platform.startswith("linux") and mach in ("aarch64", "arm64"):
        p = HERE / "prebuilt" / "linux-aarch64" / "libseizelut_fe.so"
    else:
        return None
    return p if p.exists() else None


def _lib():
    global _LIB
    if _LIB is None:
        so = HERE / "libseizelut_fe.so"
        srcs = [HERE / "seizelut_fe_stream.c", HERE / "seizelut_fe.c", HERE / "seizelut_fe_params.h"]
        path = so
        if not so.exists() or so.stat().st_mtime < max(p.stat().st_mtime for p in srcs):
            try:
                subprocess.run(["gcc", "-O2", "-shared", "-fPIC", "-o", str(so), str(srcs[0])], check=True,
                               capture_output=True, cwd=HERE)
            except (OSError, subprocess.CalledProcessError):
                pre = _prebuilt()
                if pre is None:
                    raise RuntimeError("cannot compile the C front end and no prebuilt library for this platform: "
                                       "install gcc (sudo apt install -y gcc)")
                path = pre
        lib = ctypes.CDLL(str(path))
        p, i64 = ctypes.c_void_p, ctypes.c_int64
        lib.fe_extract.argtypes = [i64, p, p, i64, p, i64, p, i64, p, p, p, i64, p, p, p, i64, p, p]
        lib.fe_extract.restype = ctypes.c_int
        lib.fe_n_features.restype = ctypes.c_int
        lib.fes_new.restype = p
        lib.fes_free.argtypes = [p]
        lib.fes_push.argtypes = [p] * 11 + [p, p, p] + [p] * 8
        lib.fes_push.restype = ctypes.c_int
        lib.fes_flush.argtypes = [p, p, p, p]
        lib.fes_flush.restype = ctypes.c_int
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


SENSORS = ("eeg1", "eeg2", "ecg", "emg", "acc_x", "acc_y", "acc_z", "gyr_x", "gyr_y", "gyr_z")


class Stream:
    """Streaming front end (seizelut_fe_stream.c): one second per push, bit-exact with extract()."""

    def __init__(self):
        self.lib = _lib()
        self.nf = self.lib.fe_n_features()
        self.h = self.lib.fes_new()
        self.X = np.zeros(self.nf, dtype=np.int64)
        self.art = np.zeros(2, dtype=np.uint8)
        self.w = np.zeros(1, dtype=np.int64)
        self.v = {k: np.zeros(n, dtype=np.int32) for k, n in
                  (("eeg1_f", 256), ("eeg2_f", 256), ("ecg_f", 256), ("emg_f", 256), ("acc_m", 25), ("gyr_m", 25),
                   ("beats", 16), ("n_beats", 1))}

    def __del__(self):
        try:
            self.lib.fes_free(self.h)
        except Exception:
            pass

    def push(self, block: dict):
        arrs = {k: np.ascontiguousarray(block[k], dtype=np.int16) for k in SENSORS if block.get(k) is not None}
        for k, n in (("eeg1", 256), ("eeg2", 256), ("ecg", 256), ("emg", 256)):
            if k in arrs and len(arrs[k]) != n:
                raise ValueError(f"{k}: {len(arrs[k])} samples, expected {n}")
        for k in SENSORS[4:]:
            if k in arrs and len(arrs[k]) != 25:
                raise ValueError(f"{k}: {len(arrs[k])} samples, expected 25")
        ptr = [arrs[k].ctypes.data if k in arrs else None for k in SENSORS]
        v = self.v
        ok = self.lib.fes_push(self.h, *ptr, self.X.ctypes.data, self.art.ctypes.data, self.w.ctypes.data,
                               v["eeg1_f"].ctypes.data, v["eeg2_f"].ctypes.data, v["ecg_f"].ctypes.data,
                               v["emg_f"].ctypes.data, v["acc_m"].ctypes.data, v["gyr_m"].ctypes.data,
                               v["beats"].ctypes.data, v["n_beats"].ctypes.data)
        viz = {"eeg1_f": v["eeg1_f"].copy(), "eeg2_f": v["eeg2_f"].copy(),
               "ecg_f": v["ecg_f"].copy() if "ecg" in arrs else None,
               "emg_f": v["emg_f"].copy() if "emg" in arrs else None,
               "acc_m": v["acc_m"].copy() if "acc_x" in arrs else None,
               "gyr_m": v["gyr_m"].copy() if "gyr_x" in arrs else None,
               "beats": v["beats"][: int(v["n_beats"][0])].copy()}
        if ok:
            return int(self.w[0]), self.X.copy(), self.art.copy(), viz
        return None, None, None, viz

    def flush(self):
        if self.lib.fes_flush(self.h, self.X.ctypes.data, self.art.ctypes.data, self.w.ctypes.data):
            return int(self.w[0]), self.X.copy(), self.art.copy()
        return None, None, None
