#!/usr/bin/env python3
"""Signal levels of the recordings themselves (Phase 1 honesty note, MS_SPEC.md 1.1), from the cached CLEAN subset
inputs (training patients only).

Per channel, on the 0.5-100 Hz band (4th-order Butterworth, zero phase, float; analysis only):
  * rms_median: median over 1-s blocks of the block RMS (typical signal level);
  * floor_p1: 1st percentile of the 1-s block RMS over blocks that are not flat (any non-zero difference).
    This is an UPPER BOUND on the recording's own noise floor (electrode + amplifier + ADC): the quietest
    second still contains some signal. It is not a measurement of the original device's noise.
Motion is reported in input LSBs (2^-12 g) on 0.5-12 Hz.

Usage: python ms/py/signal_levels.py [--max-segments N] -> ms/results/phase1/signal_levels.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from scipy.signal import butter, sosfiltfilt

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "ms/py"))
import subset_fe as FE   # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--max-segments", type=int, default=None)
    args = ap.parse_args()
    segs = json.loads((REPO / "ms/results/phase1/subset.json").read_text())["segments"]
    have = [g for g in segs if (FE.CACHE / f"{g['id']:04d}.npz").exists()]
    if args.max_segments:
        have = have[: args.max_segments]
    sos = {256: butter(4, [0.5, 100], "bandpass", fs=256, output="sos"),
           25: butter(4, [0.5, 12], "bandpass", fs=25, output="sos")}
    per = {}
    for g in have:
        chans = FE.split_inputs(FE.load_segment(g["id"]))
        for mod, ch in chans.items():
            fs = FE.FS[mod]
            unit = FE.LSB[mod] if mod != "mov" else 1.0
            for label, x in ch.items():
                n = (len(x) // fs) * fs
                if n < 60 * fs:
                    continue
                y = sosfiltfilt(sos[fs], x[:n].astype(np.float64)) * unit
                blocks = y.reshape(-1, fs)
                raw = x[:n].reshape(-1, fs)
                live = np.any(np.diff(raw, axis=1) != 0, axis=1)
                r = np.sqrt((blocks ** 2).mean(1))
                if live.sum() < 60:
                    continue
                per.setdefault(mod, []).append((float(np.median(r[live])), float(np.percentile(r[live], 1))))
    out = {"segments_used": len(have), "unit": {"eeg": "uV", "ecg": "uV", "emg": "uV", "mov": "LSB (2^-12 g)"}}
    for mod, v in per.items():
        a = np.array(v)
        out[mod] = {"channels": len(a), "rms_median_of_medians": float(np.median(a[:, 0])),
                    "rms_iqr": [float(np.percentile(a[:, 0], 25)), float(np.percentile(a[:, 0], 75))],
                    "floor_p1_median": float(np.median(a[:, 1])), "floor_p1_min": float(a[:, 1].min())}
    p = REPO / "ms/results/phase1/signal_levels.json"
    p.write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
