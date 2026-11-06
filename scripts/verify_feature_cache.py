#!/usr/bin/env python3
"""Check every cached feature file against the M1 audit (results/audit/runs.csv).

For each run: number of windows = EEG duration - 1, and, per modality, the number of windows marked
present matches that modality's EDF duration from the audit (a truncated download shows up as a
shorter `present` span). Prints the runs that disagree; with --fix deletes their cache files so the
next `scripts/extract_features.py` call re-extracts them.

Usage: python scripts/verify_feature_cache.py [--mode int] [--fix]
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import numpy as np

from seizelut.features import spec as S

REPO = Path(__file__).resolve().parents[1]
MODS = ["ecg", "emg", "mov"]          # present[:, 0..1] = ecg, emg; present[:, 2..3] = motion sensors


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--mode", default="int")
    ap.add_argument("--fix", action="store_true")
    args = ap.parse_args()
    rows = {f"{r['subject']}_{r['run']}": r for r in csv.DictReader(open(REPO / "results/audit/runs.csv"))}
    d = REPO / "cache" / "features" / args.mode
    bad, n = [], 0
    for p in sorted(d.glob("sub-*_run-*.npz")):
        if ".tmp" in p.name:
            continue
        key, r = p.stem, rows.get(p.stem)
        if r is None:
            bad.append((key, "not in audit"))
            continue
        n += 1
        z = np.load(p)
        n_win = len(z["X"])
        exp_win = int(float(r["duration_eeg_s"])) - 1
        problems = []
        if n_win != exp_win:
            problems.append(f"{n_win} windows, expected {exp_win}")
        pres = z["present"]
        for j, m in enumerate(MODS[:2]):
            if r[f"has_{m}"] == "1":
                exp = min(n_win, int(float(r[f"duration_{m}_s"])) - 1)
                if int(pres[:, j].sum()) < exp:
                    problems.append(f"{m} present {int(pres[:, j].sum())} < {exp}")
        mov_labels = set(r["mov_labels"].split("|"))
        chest = any(all(lb in mov_labels for lb in labs) for labs in (S.MOV_ACC_LABELS, S.MOV_GYR_LABELS))
        if r["has_mov"] == "1" and chest:      # head-module-only motion is unused by design
            exp = min(n_win, int(float(r["duration_mov_s"])) - 1)
            if int(pres[:, 2:].any(1).sum()) < exp:
                problems.append(f"mov present {int(pres[:, 2:].any(1).sum())} < {exp}")
        if problems:
            bad.append((key, "; ".join(problems)))
    for k, why in bad:
        print(f"{k}: {why}")
    print(f"{n} runs checked, {len(bad)} disagree with the audit")
    if args.fix:
        for k, _ in bad:
            (d / f"{k}.npz").unlink(missing_ok=True)
        print(f"deleted {len(bad)} cache files")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
