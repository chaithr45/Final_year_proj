#!/usr/bin/env python3
"""Signal-level audit of every SeizeIT2 EDF: flat-lines, saturation, artefact rate, gaps.

Works on a local copy of the dataset, or streams each file from the public S3
bucket (download -> measure -> delete), so it runs on a machine without the
126 GB of free disk. Resumable: files already in the output are skipped.

Usage:
  python scripts/audit_signals.py --stream                 # all modalities from S3
  python scripts/audit_signals.py --root data/raw/ds005873 # local copy
  python scripts/audit_signals.py --stream --modalities eeg --workers 3
Output: cache/audit/signal_stats.jsonl (one JSON object per EDF file)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
import traceback
import urllib.parse
import urllib.request
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np

from seizelut.data.edf import read_edf, record_onsets
from seizelut.data.montage import montage_type
from seizelut.data.quality import (flatline_summary, official_eeg_filter, rms_artefact_mask,
                                   saturation_fraction, window_rms)

BUCKET = "https://s3.amazonaws.com/openneuro.org"
PREFIX = "ds005873/"


def measure(path: Path, rel: str) -> dict:
    modality = rel.rsplit("_", 1)[1].split(".")[0]
    d = read_edf(path)
    h = d.header
    out = {
        "file": rel, "modality": modality, "edf_type": h.reserved or "EDF",
        "n_records": d.n_records_read, "record_s": h.record_duration, "duration_s": d.duration_s,
        "reader_warnings": d.warnings, "channels": {},
    }
    onsets = record_onsets(path)
    if onsets is not None and len(onsets):
        steps = np.diff(onsets[~np.isnan(onsets)])
        out["record_gaps"] = int(np.sum(np.abs(steps - h.record_duration) > 1e-6))
        out["gap_s"] = float(np.sum(np.clip(steps - h.record_duration, 0, None)))
        out["first_onset_s"] = float(onsets[0]) if not np.isnan(onsets[0]) else None
    if modality == "eeg":
        out["montage"] = montage_type(d.labels)
    eeg_flags = []
    for label in d.labels:
        sig, x = h.signal(label), d.digital[label]
        fs = d.fs[label]
        ch = {"fs": fs, "unit": sig.physical_dim, "gain": sig.gain,
              "phys_range": [sig.physical_min, sig.physical_max],
              "saturation": saturation_fraction(x, sig.digital_min, sig.digital_max),
              **flatline_summary(x, fs, 1.0)}
        ch["flat_10s_spans"] = flatline_summary(x, fs, 10.0)["flat_spans"]
        if modality == "eeg":
            rms = window_rms(official_eeg_filter(d.physical(label), fs), fs)
            flag = rms_artefact_mask(rms)
            eeg_flags.append(flag)
            ch.update(n_windows=int(rms.size), artefact_frac=float(flag.mean()) if rms.size else None,
                      rms_median=float(np.median(rms)) if rms.size else None,
                      rms_below13_frac=float(np.mean(rms <= 13)) if rms.size else None,
                      rms_above150_frac=float(np.mean(rms >= 150)) if rms.size else None)
        out["channels"][label] = ch
    if len(eeg_flags) == 2 and eeg_flags[0].size:
        out["artefact_any_frac"] = float(np.mean(eeg_flags[0] | eeg_flags[1]))
        out["artefact_both_frac"] = float(np.mean(eeg_flags[0] & eeg_flags[1]))
    return out


def _download(key: str, dest: Path, retries: int = 4) -> None:
    url = f"{BUCKET}/{urllib.parse.quote(key)}"
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(url, timeout=120) as resp, open(dest, "wb") as fh:
                while chunk := resp.read(1 << 22):
                    fh.write(chunk)
            return
        except Exception:
            if attempt == retries:
                raise
            time.sleep(2 ** (attempt + 1))


def job(rel: str, root: str | None, tmpdir: str) -> dict:
    t0 = time.time()
    try:
        if root:
            res = measure(Path(root) / rel, rel)
        else:
            dest = Path(tmpdir) / Path(rel).name
            try:
                _download(PREFIX + rel, dest)
                res = measure(dest, rel)
            finally:
                dest.unlink(missing_ok=True)
        res["seconds"] = round(time.time() - t0, 1)
        return res
    except Exception as exc:  # report, never hide, a failed file
        return {"file": rel, "error": f"{type(exc).__name__}: {exc}", "trace": traceback.format_exc()[-800:]}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--stream", action="store_true", help="stream each file from S3")
    src.add_argument("--root", help="local BIDS root holding the EDF files")
    ap.add_argument("--listing", default="cache/s3_listing.json")
    ap.add_argument("--modalities", nargs="+", default=["eeg", "ecg", "emg", "mov"])
    ap.add_argument("--out", default="cache/audit/signal_stats.jsonl")
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    ap.add_argument("--limit", type=int, default=None, help="only the first N files (smoke test)")
    args = ap.parse_args()

    if args.root:
        rels = sorted(str(p.relative_to(args.root)) for p in Path(args.root).glob("sub-*/ses-*/*/*.edf"))
    else:
        listing = json.loads(Path(args.listing).read_text())
        rels = sorted(o["key"][len(PREFIX):] for o in listing if o["key"].endswith(".edf"))
    rels = [r for r in rels if r.rsplit("_", 1)[1].split(".")[0] in args.modalities]
    # EEG first: it is the modality every result depends on.
    rels.sort(key=lambda r: (r.rsplit("_", 1)[1] != "eeg.edf", r))

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    done = set()
    if out.exists():
        for line in out.read_text().splitlines():
            rec = json.loads(line)
            if "error" not in rec:
                done.add(rec["file"])
    todo = [r for r in rels if r not in done][: args.limit]
    print(f"{len(rels)} files selected, {len(done)} already audited, {len(todo)} to do", flush=True)

    errors = 0
    with tempfile.TemporaryDirectory(dir=out.parent) as tmp, ProcessPoolExecutor(args.workers) as pool, \
            open(out, "a") as fh:
        futures = [pool.submit(job, r, args.root, tmp) for r in todo]
        for i, fut in enumerate(as_completed(futures), 1):
            res = fut.result()
            errors += "error" in res
            fh.write(json.dumps(res) + "\n")
            fh.flush()
            if i % 50 == 0 or "error" in res:
                print(f"  {i}/{len(todo)} {res['file']} {res.get('error', '')}", flush=True)
    print(f"done, {errors} errors", flush=True)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
