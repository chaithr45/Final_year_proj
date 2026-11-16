#!/usr/bin/env python3
"""Why the motion LSB limit and the motion white-noise limit disagree (ms/results/phase1/consistency.md, row mov).

The textbook model treats rounding to a step q as white noise of rms q/sqrt(12). It needs a signal that moves over
many steps between samples. The motion channels mostly do not: their median rms is 3.2 LSB (signal_levels.json)
against q = 16 or 32 LSB. On such a signal the rounded output stays on one code for long stretches, so rounding
REMOVES the small sample-to-sample movement instead of adding noise, while white noise ADDS movement to every sample.

The motion features that move most in the sweep (tolerance_table.md) are mag (sum |x - offset|) and jerk (line
length, sum |x[n] - x[n-1]|), both per 1-s block over the three axes of a sensor. This script measures, with the
frozen front end's own integer code (offset removal hp_offset, block_stats), how each impairment changes the jerk
sum of a sensor in quiet seconds (clean jerk at or below the median of its channel set) and in active seconds (at
or above the 90th percentile): the median of log2(impaired / clean), so +1 = doubled, -1 = halved. The impairments
are the sweep's own (impair.apply, same registers), at the LSB limit and first failing LSB (16, 32 LSB) and at the
white-noise limit and first failing level (2, 4 LSB rms). One noise realisation (seed 0) on every 4th subset
segment (training patients only).

Usage: python ms/py/mov_quant_vs_white.py -> ms/results/phase1/mov_quant_vs_white.json
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "ms/py"))
import impair as IMP                                  # noqa: E402
from seizelut.features import golden as G             # noqa: E402
from seizelut.features import spec as S               # noqa: E402

FS = 25.0
CONDITIONS = {"lsb_16": {"lsb": 16.0}, "lsb_32": {"lsb": 32.0},
              "white_2LSBrms": {"white_density": 2 / math.sqrt(FS / 2)},
              "white_4LSBrms": {"white_density": 4 / math.sqrt(FS / 2)}}
STEP = 4


def jerk(ops, axes):
    hp = [ops.hp_offset(a, S.MOV_OFFSET_SHIFT) for a in axes]
    return sum(G.block_stats(h, S.BLOCK_MOV)[1] for h in hp).astype(np.float64)


def main() -> int:
    ops = G._Ops("int")
    comp = {k: IMP.compile_impairment(IMP.Impairment(**v), FS, 1.0) for k, v in CONDITIONS.items()}
    segs = sorted((REPO / "cache/ms/subset_inputs").glob("*.npz"))[::STEP]
    clean = {"acc": [], "gyr": []}
    imp = {s: {k: [] for k in CONDITIONS} for s in clean}
    for si, p in enumerate(segs):
        z = np.load(p)
        keys = [k for k in z["_keys"] if k.startswith("mov|")]
        for sensor, tag in (("acc", "ACC"), ("gyr", "GYR")):
            ks = [k for k in keys if f" {tag} " in k]
            if len(ks) != 3:
                continue
            xs = [z[k].astype(np.int64) for k in ks]
            clean[sensor].append(jerk(ops, xs))
            for name, c in comp.items():
                ys = [IMP.apply(x, c, (0, int(p.stem), keys.index(k)))[0].astype(np.int64) for x, k in zip(xs, ks)]
                imp[sensor][name].append(jerk(ops, ys))
    out = {"what": "median log2(impaired / clean) of the per-second motion jerk sum (3 axes); see script header",
           "segments": len(segs), "every_nth_segment": STEP, "noise_seed": 0, "sensors": {}}
    for sensor in clean:
        c = np.concatenate(clean[sensor])
        q50, q90 = np.percentile(c, 50), np.percentile(c, 90)
        quiet, active = c <= q50, c >= q90
        r = {"seconds": int(len(c)), "clean_jerk_median": float(q50), "clean_jerk_p90": float(q90),
             "clean_jerk_per_sample_median": float(q50 / S.BLOCK_MOV)}
        for name in CONDITIONS:
            y = np.concatenate(imp[sensor][name])
            lr = np.log2((y + 1.0) / (c + 1.0))
            r[name] = {"quiet_median_log2_ratio": float(np.median(lr[quiet])),
                       "active_median_log2_ratio": float(np.median(lr[active])),
                       "quiet_fraction_zero_jerk": float(np.mean(y[quiet] == 0)),
                       "clean_quiet_fraction_zero_jerk": float(np.mean(c[quiet] == 0))}
        out["sensors"][sensor] = r
    (REPO / "ms/results/phase1/mov_quant_vs_white.json").write_text(json.dumps(out, indent=1) + "\n")
    for sensor, r in out["sensors"].items():
        print(f"{sensor}: {r['seconds']} s; clean jerk per sample (median second) {r['clean_jerk_per_sample_median']:.2f} LSB")
        for name in CONDITIONS:
            v = r[name]
            print(f"  {name:14s} quiet {v['quiet_median_log2_ratio']:+.2f}  active {v['active_median_log2_ratio']:+.2f}"
                  f"  quiet seconds with zero jerk {100 * v['quiet_fraction_zero_jerk']:.0f} %"
                  f" (clean {100 * v['clean_quiet_fraction_zero_jerk']:.0f} %)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
