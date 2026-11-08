#!/usr/bin/env python3
"""Test vectors for Phase 2 (Section 8.4): every stage of the golden model, per second, on recordings
that contain seizures, for an exported classifier (export/<model_id>/, src/hw/export.py).

Per recording, in <out>/<run>/ (little-endian, row-major):
  inputs/<modality>_<label>.i16   integer input samples after the fixed-gain conversion (spec/fixed_point.md)
  features.i16                    (n_windows, 117) golden integer features, spec order
  artefact.u8                     (n_windows, 2) EEG artefact flags (channel 1, channel 2)
  bits.u8                         (n_windows, n_input_bits) thermometer bits (thresholds.json order)
  lut_l<i>.u8                     (n_windows, n_luts) LUT outputs of layer i
  score.i32, gate.u8, decision.u8, alarm.u8   (n_windows,)
  sample.csv                      60 s around the first seizure: second, used features, score, decision, alarm
plus <out>/manifest.json (shapes, dtypes, sha256 of every file, sampling rates, the export it belongs to).
Phase 2's RTL must reproduce bits through alarm bit for bit.

Test recordings are test patients: --final-test is required and the access is logged in the export.
Usage:  python scripts/make_test_vectors.py --export export/<model_id> --n 10 --final-test
        python scripts/make_test_vectors.py --export export/<model_id> --runs sub-001_run-03   (any recording)
"""
from __future__ import annotations

import argparse
import contextlib
import csv
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import yaml

from seizelut.data.bids import discover_runs
from seizelut.data.edf import read_edf
from seizelut.data.remote import local_edf
from seizelut.eval.runlog import log_test_access, require_test_access
from seizelut.features import spec as S
from seizelut.features.golden import extract
from seizelut.hw.export import golden_from_export, load_export

REPO = Path(__file__).resolve().parents[1]


def default_runs(n: int) -> list[str]:
    """The first n test recordings (subject, run order) that contain at least one seizure."""
    keys = []
    for r in csv.DictReader(open(REPO / "results/audit/seizures.csv")):
        k = f"{r['subject']}_{r['run']}"
        if r["split"] == "test" and k not in keys:
            keys.append(k)
    return sorted(keys)[:n]


def _save(path: Path, a: np.ndarray, files: dict, root: Path):
    a = np.ascontiguousarray(a)
    path.parent.mkdir(parents=True, exist_ok=True)
    a.tofile(path)
    files[str(path.relative_to(root))] = {"dtype": str(a.dtype), "shape": list(a.shape),
                                          "sha256": hashlib.sha256(a.tobytes()).hexdigest()}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--export", required=True)
    ap.add_argument("--n", type=int, default=10)
    ap.add_argument("--runs", nargs="*", default=None, help="run keys (default: the first n test recordings with seizures)")
    ap.add_argument("--out", default=None, help="default: <export>/vectors")
    ap.add_argument("--dataset-root", default=None)
    ap.add_argument("--final-test", action="store_true")
    args = ap.parse_args()
    exp = Path(args.export)
    pkg = load_export(exp)
    keys = args.runs or default_runs(args.n)
    subjects = sorted({k.split("_")[0] for k in keys})
    require_test_access(subjects, args.final_test)
    if args.final_test:
        log_test_access(exp, f"test vectors on {len(keys)} recordings")
    ds = yaml.safe_load((REPO / "configs/dataset.yaml").read_text())
    root = Path(args.dataset_root) if args.dataset_root else REPO / ds["dataset"]["root"]
    runs = {r.key: r for r in discover_runs(root, subjects)}
    out = Path(args.out) if args.out else exp / "vectors"
    out.mkdir(parents=True, exist_ok=True)
    used = [f["name"] for f in pkg["thresholds"]["features"]]
    manifest = {"export": pkg["manifest"], "feature_names": list(S.FEATURES), "used_features": used,
                "fs": {"eeg": S.FS_BIO, "ecg": S.FS_BIO, "emg": S.FS_BIO, "mov": S.FS_MOV},
                "lsb": {"bio_uV": S.LSB_BIO, "mov": S.LSB_MOV}, "window_s": 2, "hop_s": 1,
                "window_t_covers_seconds": "[t, t + 2)", "recordings": {}}
    tmp = REPO / "cache" / "tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    for key in keys:
        r = runs[key]
        with contextlib.ExitStack() as st:
            sig = {m: read_edf(st.enter_context(local_edf(r, m, tmp))) for m in r.modalities}
            ann = r.read_annotations()
            inputs = {}
            res = extract(sig, int(sig["eeg"].duration_s), "int", inputs=inputs)
        X = res["X"].astype(np.int16)
        g = golden_from_export(pkg, X, res["artefact"], full_features=True)
        d = out / key
        files = {}
        for name, a in inputs.items():
            _save(d / "inputs" / (name.replace("/", "_").replace(" ", "_") + ".i16"), a.astype(np.int16), files, out)
        _save(d / "features.i16", X, files, out)
        _save(d / "artefact.u8", res["artefact"].astype(np.uint8), files, out)
        _save(d / "bits.u8", g["bits"], files, out)
        for i, lo in enumerate(g["lut_out"]):
            _save(d / f"lut_l{i}.u8", lo.astype(np.uint8), files, out)
        _save(d / "score.i32", g["score"].astype(np.int32), files, out)
        for k in ("gate", "decision", "alarm"):
            _save(d / f"{k}.u8", g[k], files, out)
        sz = ann.seizure_intervals()
        t0 = int(max(0, (sz[0][0] if sz else 0) - 20))
        cols = [S.FEATURES.index(n) for n in used]
        with open(d / "sample.csv", "w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["second"] + used + ["score", "gate", "decision", "alarm"])
            for t in range(t0, min(len(X), t0 + 60)):
                w.writerow([t] + X[t, cols].tolist() + [int(g["score"][t]), int(g["gate"][t]), int(g["decision"][t]),
                                                        int(g["alarm"][t])])
        manifest["recordings"][key] = {"n_windows": int(len(X)), "seizures_s": [list(map(float, s)) for s in sz],
                                       "files": files}
        print(f"{key}: {len(X)} windows, {int(g['alarm'].sum())} alarm seconds", flush=True)
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
