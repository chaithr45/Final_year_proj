#!/usr/bin/env python3
"""Cut the training windows (and, for the official protocol, the epoch-selection windows)
of the ChronoNet baseline, exactly as the official SegmentedGenerator does.

Keys are generated globally from the annotations (official subsample rule, seeded),
then each recording is loaded (locally, or streamed from S3), pre-processed
(256 -> 250 Hz FFT resample, 0.5-60 Hz + 50 Hz notch, zero-phase) and cut.

Usage:  python scripts/baselines/chrononet_data.py --config configs/baselines/chrononet_official.yaml
Output: <cache_dir>/train_x.npy (n, 500, 2) float32, train_y.npy, and for selection=official_test
        sel_x.npy, sel_y.npy, sel_block.npy (10-min blocks around test-patient seizures).
"""
from __future__ import annotations

import argparse
import random
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import yaml

from seizelut.data.bids import discover_runs
from seizelut.data.edf import read_edf
from seizelut.data.remote import local_edf
from seizelut.eval.runlog import require_test_access, resolve_subjects
from seizelut.models.baselines import official as off

REPO = Path(__file__).resolve().parents[2]


def _cut(args):
    run, starts, tmp = args
    with local_edf(run, "eeg", tmp) as p:
        chans = off.preprocess_eeg(read_edf(p))
    return off.cut_windows(chans, starts)


def selection_blocks(runs, block_s=600):
    """One 600 x 1 s block centred on every seizure (approximates generate_data_keys_sequential_window)."""
    out = []
    for ri, r in enumerate(runs):
        ann = r.read_annotations()
        dur = int(np.floor(ann.recording_duration)) - off.FRAME
        for a, b in ann.seizure_intervals():
            centre = int((a + b) / 2)
            s0 = int(np.clip(centre - block_s // 2, 0, max(0, dur - block_s)))
            starts = np.arange(s0, min(s0 + block_s, dur + 1), 1.0)
            labels = off.sequential_labels(len(starts) + s0, [(a, b)])[s0:s0 + len(starts)]
            out.append((ri, starts, labels))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", required=True)
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--final-test", action="store_true", help="allow test patients (official epoch selection)")
    args = ap.parse_args()
    cfg = yaml.safe_load(Path(args.config).read_text())
    ds = yaml.safe_load((REPO / "configs/dataset.yaml").read_text())
    root = REPO / ds["dataset"]["root"]
    out = REPO / cfg["data"]["cache_dir"]
    out.mkdir(parents=True, exist_ok=True)
    tmp = REPO / "cache" / "tmp"
    tmp.mkdir(parents=True, exist_ok=True)

    train_subjects = resolve_subjects(cfg["train_subjects"])
    require_test_access(train_subjects, False)
    runs = discover_runs(root, train_subjects)
    rec_events = []
    for i, r in enumerate(runs):
        ann = r.read_annotations()
        rec_events.append((i, [(e.onset, e.end) for e in sorted(ann.seizures, key=lambda e: e.onset)],
                           ann.recording_duration))
    keys = off.subsample_keys(rec_events, random.Random(cfg["seed"]), factor=cfg["data"]["factor"])
    if cfg["train"].get("max_windows"):
        keys = keys[: cfg["train"]["max_windows"]]
    print(f"{len(runs)} training recordings, {len(keys)} windows ({int(keys[:, 3].sum())} seizure)", flush=True)

    x = np.lib.format.open_memmap(out / "train_x.npy", mode="w+", dtype=np.float32, shape=(len(keys), 500, 2))
    jobs = []
    for i in sorted(set(keys[:, 0].astype(int))):
        sel = np.flatnonzero(keys[:, 0] == i)
        jobs.append((sel, (runs[i], keys[sel, 1], str(tmp))))
    with ProcessPoolExecutor(args.workers) as pool:
        for n, ((sel, _), w) in enumerate(zip(jobs, pool.map(_cut, [j[1] for j in jobs]))):
            x[sel] = w
            if n % 50 == 0:
                print(f"  {n}/{len(jobs)} recordings", flush=True)
    x.flush()
    np.save(out / "train_y.npy", keys[:, 3].astype(np.uint8))
    np.save(out / "train_keys.npy", keys)

    if cfg["train"]["selection"] == "official_test":
        test_subjects = resolve_subjects("official_test")
        require_test_access(test_subjects, args.final_test)
        truns = discover_runs(root, test_subjects)
        blocks = selection_blocks(truns)
        xs, ys, bs = [], [], []
        by_run = {}
        for bi, (ri, starts, labels) in enumerate(blocks):
            by_run.setdefault(ri, []).append((bi, starts, labels))
        for ri, items in by_run.items():
            allstarts = np.concatenate([s for _, s, _ in items])
            w = _cut((truns[ri], allstarts, str(tmp)))
            k = 0
            for bi, s, lab in items:
                xs.append(w[k:k + len(s)]); ys.append(lab); bs.append(np.full(len(s), bi)); k += len(s)
        np.save(out / "sel_x.npy", np.concatenate(xs))
        np.save(out / "sel_y.npy", np.concatenate(ys).astype(np.uint8))
        np.save(out / "sel_block.npy", np.concatenate(bs))
        print(f"selection set: {len(blocks)} blocks around test-patient seizures (official protocol)")
    print("done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
