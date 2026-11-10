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
                lines.append(f"{v:0{(pos + 4) // 4}x}")
            (tb / f"{rec}.hex").write_text("\n".join(lines) + "\n")
        print(rec, len(F), "windows")
    (out / "index.json").write_text(json.dumps(index, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
