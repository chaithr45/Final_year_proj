#!/usr/bin/env python3
"""Export package of a final model (Section 8.2): the model of one seed of an M6 final run
(checkpoints/<final run>/seed_<s>.pkl) with the operating point of its inner-CV run, written as
export/<config>_s<seed>/ (thresholds, mapping, LUT truth tables, head, manifest; src/hw/export.py).

Usage:  python scripts/export_model.py --final-run results/runs/<id>_final_s0 --seed 0 [--op best_f1]
Then:   python scripts/make_test_vectors.py --export export/<config>_s<seed> --final-test
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pickle
import sys
from pathlib import Path

import yaml

from seizelut.hw.export import export_dwn

REPO = Path(__file__).resolve().parents[1]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--final-run", required=True)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--op", default="best_f1", choices=["best_f1", "sens_at_1fah"])
    ap.add_argument("--out", default=None, help="repository-like root holding checkpoints/ and runs (tests)")
    ap.add_argument("--export-dir", default=None, help="default: export/<config>_s<seed>")
    args = ap.parse_args()
    root = Path(args.out) if args.out else REPO
    run = Path(args.final_run)
    cfg_text = (run / "config.yaml").read_text()
    cfg = yaml.safe_load(cfg_text)
    cv_dir = run.parent / cfg["cv_run"]
    op = json.loads((cv_dir / "metrics.json").read_text())["operating_points"][args.op]
    with open(root / "checkpoints" / run.name / f"seed_{args.seed}.pkl", "rb") as fh:
        obj = pickle.load(fh)
    model = obj["model"]
    if getattr(model, "name", "") != "dwn":
        raise SystemExit(f"export of model type {getattr(model, 'name', type(model).__name__)} is not implemented yet")
    out = Path(args.export_dir) if args.export_dir else REPO / "export" / f"{cfg['name']}_s{args.seed}"
    meta = {"training_run": run.name, "seed": args.seed, "cv_run": cfg["cv_run"], "operating_point_name": args.op,
            "config_sha256_16": hashlib.sha256(cfg_text.encode()).hexdigest()[:16], "config": cfg}
    export_dwn(model, obj["features"], op, out, meta)
    print(f"exported to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
