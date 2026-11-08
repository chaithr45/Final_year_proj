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
import time
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, ThreadPoolExecutor, wait
from pathlib import Path

import numpy as np
import yaml

from seizelut.data.bids import discover_runs
from seizelut.data.edf import read_edf
from seizelut.data.remote import fetch_edf, local_edf
from seizelut.eval.runlog import require_test_access, resolve_subjects
from seizelut.models.baselines import official as off

REPO = Path(__file__).resolve().parents[2]


def _cut(args):
    run, starts, tmp = args
    with local_edf(run, "eeg", tmp) as p:
        size = p.stat().st_size
        chans = off.preprocess_eeg(read_edf(p))
    return off.cut_windows(chans, starts), size


def _cut_file(args):
    path, starts = args
    chans = off.preprocess_eeg(read_edf(path))
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
    ap.add_argument("--workers", type=int, default=1,
                    help="recordings pre-processed at once; each needs up to ~3 GB for the longest "
                         "recordings (whole-record FFT resample), so keep 1 on an 8 GB machine")
    ap.add_argument("--downloads", type=int, default=4, help="EDF downloads running ahead of processing")
    ap.add_argument("--final-test", action="store_true", help="allow test patients (official epoch selection)")
    args = ap.parse_args()
    import scipy
    if tuple(int(v) for v in scipy.__version__.split(".")[:2]) < (1, 18):
        print(f"WARNING: scipy {scipy.__version__}: its FFT needs up to ~5 GB for the longest recordings "
              "(1.2 GB with scipy 1.18); on an 8 GB machine run  pip install scipy==1.18.1  first", flush=True)
    cfg = yaml.safe_load(Path(args.config).read_text())
    ds = yaml.safe_load((REPO / "configs/dataset.yaml").read_text())
    root = REPO / ds["dataset"]["root"]
    out = REPO / cfg["data"]["cache_dir"]
    out.mkdir(parents=True, exist_ok=True)
    tmp = REPO / "cache" / "tmp" / "chrononet"
    if tmp.exists():                     # downloads left behind by an interrupted run
        import shutil
        shutil.rmtree(tmp)
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

    # Resumable: recordings already cut are listed in train_progress.txt (written only after the
    # memmap is flushed), so an interrupted run continues where it stopped; COMPLETE skips everything.
    done_f, prog_f = out / "COMPLETE", out / "train_progress.txt"
    sig = f"{cfg['seed']} {cfg['data']['factor']} {len(runs)} {len(keys)} {int(keys[:, 3].sum())}"
    if done_f.exists() and done_f.read_text().strip() == sig:
        print("ChronoNet data already complete for this config; nothing to do")
        return 0
    have = out / "train_x.npy"
    resume = prog_f.exists() and have.exists() and prog_f.read_text().split("\n", 1)[0] == sig
    if resume:
        x = np.load(have, mmap_mode="r+")
        assert x.shape == (len(keys), 500, 2)
        finished = {int(v) for v in prog_f.read_text().split("\n")[1:] if v.strip()}
    else:
        x = np.lib.format.open_memmap(have, mode="w+", dtype=np.float32, shape=(len(keys), 500, 2))
        prog_f.write_text(sig + "\n")
        finished = set()
    jobs = []
    for i in sorted(set(keys[:, 0].astype(int))):
        if i in finished:
            continue
        sel = np.flatnonzero(keys[:, 0] == i)
        jobs.append((i, sel, runs[i], keys[sel, 1]))
    n_rec = len(set(keys[:, 0].astype(int)))
    if resume:
        print(f"resuming: {len(finished)} of {n_rec} recordings already cut", flush=True)
    # recordings are stored as soon as each one finishes (any order); progress is saved every 5
    # recordings or 2 minutes, and the speed / time left is printed every 10 recordings
    dur = {i: rec_events[i][2] for i in set(keys[:, 0].astype(int))}
    total_h = sum(dur.values()) / 3600
    done_h = sum(dur[i] for i in finished) / 3600
    pending, t0, last, mb, h_now = [], time.time(), time.time(), 0.0, 0.0
    print(f"  {len(jobs)} recordings to cut ({total_h - done_h:.0f} of {total_h:.0f} EEG hours), "
          f"{args.downloads} downloads ahead of {args.workers} processing", flush=True)

    def finished_cuts():
        """Yield (i, sel, windows, bytes) as recordings finish. At most downloads + workers EDFs
        are on disk or in flight at once, and only `workers` are being pre-processed (memory)."""
        it = iter(jobs)
        dl_f, pr_f = {}, {}
        with ThreadPoolExecutor(args.downloads) as dl, ProcessPoolExecutor(args.workers) as pr:
            def top_up():
                while len(dl_f) + len(pr_f) < args.downloads + args.workers:
                    nxt = next(it, None)
                    if nxt is None:
                        return
                    i, sel, run, starts = nxt
                    dl_f[dl.submit(fetch_edf, run, "eeg", str(tmp))] = (i, sel, starts)
            top_up()
            while dl_f or pr_f:
                done, _ = wait(list(dl_f) + list(pr_f), return_when=FIRST_COMPLETED)
                for f in done:
                    if f in dl_f:
                        i, sel, starts = dl_f.pop(f)
                        path, is_tmp = f.result()
                        pr_f[pr.submit(_cut_file, (str(path), starts))] = (i, sel, path, is_tmp)
                    else:
                        i, sel, path, is_tmp = pr_f.pop(f)
                        w = f.result()
                        size = path.stat().st_size
                        if is_tmp:
                            path.unlink(missing_ok=True)
                        yield i, sel, w, size
                top_up()

    for n, (i, sel, w, size) in enumerate(finished_cuts(), 1):
        x[sel] = w
        pending.append(i)
        mb += size / 1e6
        h_now += dur[i] / 3600
        if len(pending) >= 5 or time.time() - last > 120 or n == len(jobs):
            x.flush()
            with open(prog_f, "a") as fh:
                fh.write("".join(f"{v}\n" for v in pending))
            pending, last = [], time.time()
        if n % 10 == 0 or n == len(jobs):
            el = time.time() - t0
            left = el * (total_h - done_h - h_now) / max(h_now, 1e-9)
            print(f"  {len(finished) + n}/{n_rec} recordings ({100 * (done_h + h_now) / total_h:.0f}% of the EEG), "
                  f"{mb / el:.1f} MB/s, about {left / 3600:.1f} h left", flush=True)
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
            w, _ = _cut((truns[ri], allstarts, str(tmp)))
            k = 0
            for bi, s, lab in items:
                xs.append(w[k:k + len(s)]); ys.append(lab); bs.append(np.full(len(s), bi)); k += len(s)
        np.save(out / "sel_x.npy", np.concatenate(xs))
        np.save(out / "sel_y.npy", np.concatenate(ys).astype(np.uint8))
        np.save(out / "sel_block.npy", np.concatenate(bs))
        print(f"selection set: {len(blocks)} blocks around test-patient seizures (official protocol)")
    done_f.write_text(sig + "\n")
    print("done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
