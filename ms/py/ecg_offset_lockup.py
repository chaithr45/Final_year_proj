#!/usr/bin/env python3
"""Mechanism behind the ECG DC-offset limit (MS_SPEC.md step 6): the R-peak detector of the frozen front end.

The ECG path (src/features/golden.py ecg_features) is 5 Hz high-pass -> 15 Hz low-pass -> rpeak_detect
(src/features/kernels.py). The detector sets its peak level spk from the maximum of its moving sum over the first
2 s (ECG_WARMUP) and afterwards moves spk only on accepted beats; rejected peaks pull the noise level npk towards
them. The threshold is npk + ((spk - npk) >> 2). A DC offset present from sample 0 is a step for the high-pass
filter, whose state starts at zero, so the warm-up sees the step's transient. If that transient is much larger than
the R peaks, spk starts far above them, npk climbs to the R-peak level, and the threshold stays above the R peaks:
beats stop being detected for the rest of the segment.

This script measures it on the 899 subset segments (training patients only; cache/ms/subset_inputs): for clean data
and for offsets of 0.1 and 0.3 of C (8192 uV, the levels of the sweep), the minutes (after the first 2) in which
fewer than 20 beats are detected, and the largest |filtered ECG| in the warm-up. The ECG chain is the frozen
front end's own integer code, imported unchanged.

Usage: python ms/py/ecg_offset_lockup.py -> ms/results/phase1/ecg_offset_lockup.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from seizelut.features import golden as G           # noqa: E402
from seizelut.features import spec as S             # noqa: E402
from seizelut.features.kernels import rpeak_detect  # noqa: E402

OFFSETS_C = (0.0, 0.1, 0.3)
C_UV, UV_PER_LSB = 8192.0, 0.25
LOW_BEATS_PER_MIN = 20
SKIP_MIN = 2


def ecg_chain(x: np.ndarray):
    ops = G._Ops("int")
    F = S.FILTERS
    e = ops.filt(ops.filt(x, F["ecg_hp5"]), F["ecg_lp15"])
    b = rpeak_detect(e, S.ECG_INTEG, S.ECG_REFRACTORY, S.ECG_SPK_SHIFT, S.ECG_THR_SHIFT, S.ECG_WARMUP)
    return b, int(np.abs(e[:S.ECG_WARMUP]).max())


def low_minutes(beats: np.ndarray, n_min: int) -> int:
    per_min = np.bincount((beats / S.FS_BIO // 60).astype(int), minlength=n_min)[:n_min][SKIP_MIN:]
    return int((per_min < LOW_BEATS_PER_MIN).sum())


def main() -> int:
    segs = sorted((REPO / "cache/ms/subset_inputs").glob("*.npz"))
    tot = {f: {"minutes": 0, "low_minutes": 0, "segments_half_low": 0, "beats": 0, "warmup_max_median": []}
           for f in OFFSETS_C}
    per_seg, n_used = [], 0
    for p in segs:
        z = np.load(p)
        k = [c for c in z.keys() if c.startswith("ecg|")]
        if not k:
            continue
        x = z[k[0]].astype(np.int64)
        n_min = int(len(x) / S.FS_BIO // 60)
        if n_min <= SKIP_MIN:
            continue
        n_used += 1
        row = {"segment": p.stem, "minutes": n_min - SKIP_MIN}
        for f in OFFSETS_C:
            b, wmax = ecg_chain(np.clip(x + int(round(f * C_UV / UV_PER_LSB)), -32768, 32767))
            lo = low_minutes(b, n_min)
            t = tot[f]
            t["minutes"] += n_min - SKIP_MIN; t["low_minutes"] += lo; t["beats"] += len(b)
            t["segments_half_low"] += int(lo >= 0.5 * (n_min - SKIP_MIN)); t["warmup_max_median"].append(wmax)
            row[f"{f:g}C"] = {"beats": int(len(b)), "low_minutes": lo, "warmup_max_abs": wmax}
        per_seg.append(row)
    for t in tot.values():
        t["low_fraction"] = t["low_minutes"] / t["minutes"]
        t["warmup_max_median"] = float(np.median(t["warmup_max_median"]))
    out = {"what": "ECG R-peak detector vs a DC offset from sample 0 (frozen front-end code); see script header",
           "segments": n_used, "low_beats_per_min": LOW_BEATS_PER_MIN, "skip_first_minutes": SKIP_MIN,
           "offsets_fraction_of_C": list(OFFSETS_C), "C_uV": C_UV,
           "totals": {f"{f:g}C": v for f, v in tot.items()}, "per_segment": per_seg}
    (REPO / "ms/results/phase1/ecg_offset_lockup.json").write_text(json.dumps(out, indent=1) + "\n")
    for f, t in tot.items():
        print(f"offset {f:.1f} C ({f * C_UV:.0f} uV): {t['low_minutes']}/{t['minutes']} minutes "
              f"({100 * t['low_fraction']:.1f} %) with < {LOW_BEATS_PER_MIN} beats; {t['segments_half_low']} of "
              f"{n_used} segments at least half such minutes; {t['beats']} beats; median warm-up max |e| "
              f"{t['warmup_max_median']:.0f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
