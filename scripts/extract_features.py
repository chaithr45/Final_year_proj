#!/usr/bin/env python3
"""Run the golden integer feature model (and optionally its float twin) on every recording.

Streams each run's EDFs from S3 when they are not local, so it needs no 126 GB copy.
Resumable: runs already in the cache are skipped.

Usage:
  python scripts/extract_features.py                         # all 125 patients, integer model
  python scripts/extract_features.py --mode float --subjects sub-001 sub-002
  python scripts/extract_features.py --workers 3
Output: cache/features/<mode>/<sub>_<run>.npz with
  X (n_win, 117) int16 (float32 for the twin), y (window labels, >=50 % overlap),
  artefact (n_win, 2), present (n_win, 4), seizures (k, 2), duration_s, sat (json)
and cache/features/<mode>/maxabs.json (largest |value| per feature, for the width test).
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
import yaml

from seizelut.data.bids import discover_runs
from seizelut.data.edf import read_edf
from seizelut.data.remote import local_edf
from seizelut.data.split import official_test_subjects, official_train_subjects
from seizelut.data.windows import window_labels, window_starts
from seizelut.features import spec as S
from seizelut.features.golden import extract

REPO = Path(__file__).resolve().parents[1]


def process(run, out_dir: str, mode: str, tmp: str) -> dict:
    t0 = time.time()
    dest = Path(out_dir) / f"{run.key}.npz"
    try:
        with contextlib.ExitStack() as st:
            sig = {m: read_edf(st.enter_context(local_edf(run, m, tmp))) for m in run.modalities}
            for m, d in sig.items():         # a truncated file must never become a silently shorter run
                bad = [w for w in d.warnings if "header says" in w or "trailing bytes" in w]
                if bad:
                    raise IOError(f"{m}: {'; '.join(bad)}")
            ann = run.read_annotations()
            n_sec = int(sig["eeg"].duration_s)
            res = extract(sig, n_sec, mode)
        X = res["X"]
        if mode == "int":
            lim = np.array([(1 << (S.FEATURE_BITS[n] - 1)) - 1 for n in S.FEATURES])
            if np.any(np.abs(X) > lim):
                bad = [S.FEATURES[j] for j in np.flatnonzero(np.abs(X).max(0) > lim)]
                raise OverflowError(f"declared width exceeded: {bad}")
            X = X.astype(np.int16)
        else:
            X = X.astype(np.float32)
        starts = window_starts(n_sec, 2.0, 1.0)[: len(X)]
        sz = np.array(ann.seizure_intervals(), dtype=np.float64).reshape(-1, 2)
        y = window_labels(starts, 2.0, [tuple(s) for s in sz])
        tmp_dest = dest.with_suffix(".tmp.npz")
        np.savez_compressed(tmp_dest, X=X, y=y, artefact=res["artefact"], present=res["present"], seizures=sz,
                            duration_s=float(ann.recording_duration), n_beats=len(res["beats"]),
                            sat=json.dumps(res["sat"]))
        tmp_dest.replace(dest)
        return {"run": run.key, "n_win": len(X), "seconds": round(time.time() - t0, 1),
                "maxabs": np.abs(res["X"]).max(0).tolist(), "sat": res["sat"]}
    except Exception as exc:
        return {"run": run.key, "error": f"{type(exc).__name__}: {exc}"}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mode", choices=["int", "float"], default="int")
    ap.add_argument("--subjects", nargs="*", default=None, help="default: all 125")
    ap.add_argument("--split", choices=["train", "test", "all"], default="all")
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--root", default=None)
    args = ap.parse_args()
    ds = yaml.safe_load((REPO / "configs/dataset.yaml").read_text())
    root = Path(args.root or REPO / ds["dataset"]["root"])
    subjects = args.subjects or {"train": official_train_subjects(), "test": official_test_subjects(),
                                 "all": official_train_subjects() + official_test_subjects()}[args.split]
    out = REPO / "cache" / "features" / args.mode
    out.mkdir(parents=True, exist_ok=True)
    tmp = REPO / "cache" / "tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    runs = [r for r in discover_runs(root, subjects) if not (out / f"{r.key}.npz").exists()]
    print(f"{len(runs)} runs to extract ({args.mode})", flush=True)
    maxabs_path = out / "maxabs.json"
    maxabs = json.loads(maxabs_path.read_text()) if maxabs_path.exists() else {}
    errors = 0
    with ProcessPoolExecutor(args.workers) as pool:
        futs = [pool.submit(process, r, str(out), args.mode, str(tmp)) for r in runs]
        for i, f in enumerate(as_completed(futs), 1):
            res = f.result()
            if "error" in res:
                errors += 1
                print(f"ERROR {res['run']}: {res['error']}", flush=True)
                continue
            for n, v in zip(S.FEATURES, res["maxabs"]):
                maxabs[n] = max(maxabs.get(n, 0), float(v))
            if i % 20 == 0 or i == len(runs):
                maxabs_path.write_text(json.dumps(maxabs, indent=1))
                print(f"  {i}/{len(runs)} {res['run']} {res['n_win']} windows {res['seconds']} s", flush=True)
    maxabs_path.write_text(json.dumps(maxabs, indent=1))
    print(f"done, {errors} errors")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
