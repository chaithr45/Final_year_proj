"""Run the UNCHANGED golden integer front end (src/features/golden.py) on cached subset inputs, optionally impaired.

golden.extract() reads its inputs through EdfData-like objects and converts them with to_fixed():
round(physical / lsb), clipped to int16. IntSignals returns physical = int * lsb, which to_fixed() maps back to the
same integers exactly (lsb = 0.25 uV or 2^-12 g, both exact in float64), so cached or impaired integer samples
enter the front end without touching any FCCM file.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from seizelut.features import golden
from seizelut.features import spec as S

import impair as IMP

REPO = Path(__file__).resolve().parents[2]
CACHE = REPO / "cache/ms/subset_inputs"
FS = {"eeg": S.FS_BIO, "ecg": S.FS_BIO, "emg": S.FS_BIO, "mov": S.FS_MOV}
LSB = {"eeg": S.LSB_BIO, "ecg": S.LSB_BIO, "emg": S.LSB_BIO, "mov": S.LSB_MOV}
UNIT = {"eeg": "uV", "ecg": "uV", "emg": "uV", "mov": "g"}
MODS = ("eeg", "ecg", "emg", "mov")


@dataclass
class _Sig:
    physical_dim: str


class _Header:
    def __init__(self, dim: str):
        self._s = _Sig(dim)

    def signal(self, label: str) -> _Sig:
        return self._s


class IntSignals:
    """Minimal stand-in for seizelut.data.edf.EdfData holding integer samples on the front end's input grid."""

    def __init__(self, arrays: dict[str, np.ndarray], lsb: float, dim: str):
        self.digital = arrays
        self._lsb = lsb
        self.header = _Header(dim)

    @property
    def labels(self) -> list[str]:
        return list(self.digital)

    def physical(self, label: str) -> np.ndarray:
        return self.digital[label].astype(np.float64) * self._lsb


def load_segment(seg_id: int) -> dict:
    z = np.load(CACHE / f"{seg_id:04d}.npz", allow_pickle=False)
    return {k: z[k] for k in z.files}


def split_inputs(arrs: dict) -> dict[str, dict[str, np.ndarray]]:
    """'eeg|<label>' keys (as cached) -> {modality: {label: int array}} in the cached channel order."""
    out: dict[str, dict[str, np.ndarray]] = {}
    for k in arrs["_keys"]:
        mod, label = str(k).split("|", 1)
        out.setdefault(mod, {})[label] = arrs[str(k)].astype(np.int64)
    return out


def run_segment(seg: dict, arrs: dict, impairments: dict | None = None, seed: int = 0) -> dict:
    """As run_segment_full, restricted to the scored windows."""
    r = run_segment_full(seg, arrs, impairments, seed)
    k0 = seg["score_start_s"] - seg["start_s"]
    return {"X": r["X"][k0:], "artefact": r["artefact"][k0:], "present": r["present"][k0:],
            "first_window_s": seg["score_start_s"], "clipped": r["clipped"]}


def run_segment_full(seg: dict, arrs: dict, impairments: dict | None = None, seed: int = 0) -> dict:
    """Features of one subset segment. impairments: {modality: impair.Compiled} (missing = clean).
    Noise streams are keyed by (seed, segment id, channel index), so every channel and segment is independent and
    every run is reproducible. Returns the golden output restricted to the scored windows plus clip counts."""
    chans = split_inputs(arrs)
    signals, clipped, ci = {}, {}, 0
    for mod in MODS:
        if mod not in chans:
            continue
        arrays = {}
        for label, x in chans[mod].items():
            c = (impairments or {}).get(mod)
            if c is not None:
                y, st = IMP.apply(x, c, (seed, seg["id"], ci))
                clipped[f"{mod}|{label}"] = st["clipped"]
                x = y.astype(np.int64)
            arrays[label] = x
            ci += 1
        signals[mod] = IntSignals(arrays, LSB[mod], UNIT[mod])
    n_sec = seg["end_s"] - seg["start_s"]
    res = golden.extract(signals, n_sec, "int")
    return {"X": res["X"], "artefact": res["artefact"], "present": res["present"], "clipped": clipped}
