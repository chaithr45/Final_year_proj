#!/usr/bin/env python3
"""Cache the integer front-end inputs of every Phase 1 subset segment (cache/ms/subset_inputs/<id>.npz, git-ignored).

For each of the subset's recordings (training patients only): stream its EDFs from S3, run the golden extractor
once on the whole recording with inputs capture (exactly what the full pipeline reads), cut the inputs of every
segment of that recording, and check the whole-recording features against cache/features/int/<run>.npz when that
file exists (repeatability of the extraction). Resumable: recordings whose segments are all cached are skipped.

Usage: python ms/py/cache_subset_inputs.py [--workers 1]
"""
from __future__ import annotations

import argparse
import contextlib
import json
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "ms/py"))
from seizelut.data.bids import discover_runs     # noqa: E402
from seizelut.data.edf import read_edf          # noqa: E402
from seizelut.data.remote import local_edf      # noqa: E402
from seizelut.features import golden            # noqa: E402
from seizelut.features import spec as S         # noqa: E402

SUBSET = REPO / "ms/results/phase1/subset.json"
OUT = REPO / "cache/ms/subset_inputs"
TMP = REPO / "cache/ms/tmp"
FS = {"eeg": S.FS_BIO, "ecg": S.FS_BIO, "emg": S.FS_BIO, "mov": S.FS_MOV}


def process(run_key: str, segs: list[dict]) -> dict:
    t0 = time.time()
    subj = run_key.split("_")[0]
    run = [r for r in discover_runs(REPO / "data/raw/ds005873", [subj]) if r.key == run_key][0]
    inputs: dict = {}
    with contextlib.ExitStack() as st:
        sig = {m: read_edf(st.enter_context(local_edf(run, m, str(TMP)))) for m in run.modalities}
        n_sec = int(sig["eeg"].duration_s)
        res = golden.extract(sig, n_sec, "int", inputs=inputs)
    check = "no cache"
    cpath = REPO / "cache/features/int" / f"{run_key}.npz"
    if cpath.exists():
        ref = np.load(cpath)["X"]
        check = "equal" if np.array_equal(ref, res["X"].astype(np.int16)) else "DIFFERENT"
    for g in segs:
        arrs, keys = {}, []
        for k, v in inputs.items():
            mod = k.split("/", 1)[0]
            fs = FS[mod]
            key = k.replace("/", "|", 1)
            arrs[key] = v[g["start_s"] * fs: g["end_s"] * fs].astype(np.int16)
            keys.append(key)
        tmp = OUT / f"{g['id']:04d}.tmp.npz"
        np.savez_compressed(tmp, _keys=np.array(keys), **arrs)
        tmp.replace(OUT / f"{g['id']:04d}.npz")
    return {"run": run_key, "segments": len(segs), "seconds": round(time.time() - t0, 1), "check": check,
            "n_sec": n_sec}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--workers", type=int, default=1)
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    TMP.mkdir(parents=True, exist_ok=True)
    segs = json.loads(SUBSET.read_text())["segments"]
    by_run: dict[str, list[dict]] = {}
    for g in segs:
        assert int(g["subject"].split("-")[1]) <= 96, "training patients only"
        by_run.setdefault(g["run"], []).append(g)
    todo = {k: v for k, v in by_run.items() if not all((OUT / f"{g['id']:04d}.npz").exists() for g in v)}
    print(f"{len(todo)} of {len(by_run)} recordings to cache", flush=True)
    log = REPO / "cache/ms/cache_subset_inputs.jsonl"
    with ProcessPoolExecutor(args.workers) as pool, open(log, "a") as fh:
        futs = {pool.submit(process, k, v): k for k, v in sorted(todo.items())}
        for i, f in enumerate(as_completed(futs), 1):
            try:
                r = f.result()
            except Exception as exc:
                r = {"run": futs[f], "error": f"{type(exc).__name__}: {exc}"}
            fh.write(json.dumps(r) + "\n")
            fh.flush()
            print(f"  {i}/{len(todo)} {r}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
