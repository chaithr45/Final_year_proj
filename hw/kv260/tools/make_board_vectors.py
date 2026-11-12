#!/usr/bin/env python3
"""Board test vectors for the KV260 kit (run in the project repository, not on the board).

From the exported model's golden test vectors (export/<model>/vectors/, scripts/make_test_vectors.py) and the
feature cache's window labels, writes per recording board/vectors/<recording>.npz with
  feats     (n, n_features) int16   the classifier's input features, in register order
  art       (n, 2) uint8            EEG artefact flags
  score     (n,) int8, decision (n,) uint8, alarm (n,) uint8   golden outputs (software model)
  y         (n,) uint8              window label (1 = window overlaps an annotated seizure)
  seizures  (k, 2) float64          seizure onsets/offsets in seconds
plus board/vectors/index.json, and the AXI testbench vectors sim/vectors/<recording>.hex (optional, --tb).

Usage: python hw/kv260/tools/make_board_vectors.py [--export export/n4_distill_s0] [--tb]
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

KIT = Path(__file__).resolve().parents[1]
REPO = KIT.parents[1]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--export", default=str(REPO / "export/n4_distill_s0"))
    ap.add_argument("--tb", action="store_true", help="also write testbench hex vectors")
    ap.add_argument("--raw", nargs="*", default=["sub-100_run-03", "sub-099_run-02", "sub-097_run-10"],
                    help="recordings whose raw integer samples go to board/raw/ (end-to-end test)")
    args = ap.parse_args()
    import sys
    sys.path.insert(0, str(REPO / "src"))
    from seizelut.data.featureset import FeatureStore
    from seizelut.hw.export import load_export
    from seizelut.hw.kv260 import model_features

    pkg = load_export(Path(args.export))
    vd = Path(args.export) / "vectors"
    man = json.loads((vd / "manifest.json").read_text())
    ns = len(man["feature_names"])
    store = FeatureStore("int")
    out = KIT / "board" / "vectors"
    out.mkdir(parents=True, exist_ok=True)
    index = {"export": man["export"].get("training_run"), "features": [f["name"] for f in pkg["thresholds"]["features"]],
             "recordings": {}}
    for rec, meta in sorted(man["recordings"].items()):
        X = np.fromfile(vd / rec / "features.i16", dtype=np.int16).reshape(-1, ns)
        F = model_features(X, pkg)
        art = np.fromfile(vd / rec / "artefact.u8", dtype=np.uint8).reshape(-1, 2)
        score = np.fromfile(vd / rec / "score.i32", dtype=np.int32).astype(np.int8)
        dec = np.fromfile(vd / rec / "decision.u8", dtype=np.uint8)
        alarm = np.fromfile(vd / rec / "alarm.u8", dtype=np.uint8)
        y = store.load_labels(rec).astype(np.uint8)
        assert len(y) == len(F) == meta["n_windows"], rec
        sz = np.array(meta["seizures_s"], dtype=np.float64).reshape(-1, 2)
        p = out / f"{rec}.npz"
        np.savez_compressed(p, feats=F, art=art, score=score, decision=dec, alarm=alarm, y=y, seizures=sz)
        index["recordings"][rec] = {"windows": int(len(F)), "seizures": int(len(sz)), "alarm_windows": int(alarm.sum()),
                                    "decision_windows": int(dec.sum()),
                                    "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
        if args.tb:
            nb = len(pkg["thresholds"]["input_bits"])
            nl = pkg["mapping"]["layers"][-1]["n_luts"]
            bits = np.fromfile(vd / rec / "bits.u8", dtype=np.uint8).reshape(-1, nb)
            luts = np.fromfile(vd / rec / f"lut_l{len(pkg['mapping']['layers']) - 1}.u8", dtype=np.uint8).reshape(-1, nl)
            tb = KIT / "sim" / "vectors"
            tb.mkdir(parents=True, exist_ok=True)
            lines = []
            for t in range(len(F)):
                v = 0
                for c in range(F.shape[1]):
                    v |= (int(F[t, c]) & 0xFFFF) << (16 * c)
                pos = 16 * F.shape[1]
                v |= (int(art[t, 0]) | (int(art[t, 1]) << 1)) << pos
                pos += 2
                v |= (int(score[t]) & 0xFF) << pos
                pos += 8
                v |= int(dec[t]) << pos
                pos += 1
                v |= int(alarm[t]) << pos
                pos += 1
                for j in range(bits.shape[1]):          # golden comparator bits, then LUT outputs (debug taps)
                    v |= int(bits[t, j]) << (pos + j)
                pos += bits.shape[1]
                for j in range(luts.shape[1]):
                    v |= int(luts[t, j]) << (pos + j)
                pos += luts.shape[1]
                lines.append(f"{v:0{(pos + 3) // 4}x}")
            (tb / f"{rec}.hex").write_text("\n".join(lines) + "\n")
        print(rec, len(F), "windows")
    (out / "index.json").write_text(json.dumps(index, indent=1))
    # raw integer samples for the end-to-end test (front end on the ARM, classifier in the fabric)
    raw_dir = KIT / "board" / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    keymap = {"ecg_ECG_SD": "ecg", "emg_EMG_SD": "emg", "mov_ECGEMG_SD_ACC_X": "acc_x", "mov_ECGEMG_SD_ACC_Y": "acc_y",
              "mov_ECGEMG_SD_ACC_Z": "acc_z", "mov_ECGEMG_SD_GYR_A": "gyr_x", "mov_ECGEMG_SD_GYR_B": "gyr_y",
              "mov_ECGEMG_SD_GYR_C": "gyr_z", "eeg_CROSStop_SD": "eeg2"}
    for rec in args.raw:
        files = {p.stem: p for p in (vd / rec / "inputs").glob("*.i16")}
        raw = {}
        for stem, p in files.items():
            key = "eeg1" if stem.startswith("eeg_BTE") else keymap.get(stem)
            if key:
                raw[key] = np.fromfile(p, dtype=np.int16)
        X = np.fromfile(vd / rec / "features.i16", dtype=np.int16).reshape(-1, ns)
        art = np.fromfile(vd / rec / "artefact.u8", dtype=np.uint8).reshape(-1, 2)
        np.savez_compressed(raw_dir / f"{rec}.npz", golden_features=X, golden_art=art,
                            n_win=np.int64(man["recordings"][rec]["n_windows"]), **raw)
        print("raw", rec, sorted(raw))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
