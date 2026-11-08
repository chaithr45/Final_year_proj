#!/usr/bin/env python3
"""Reference Verilog check (Section 8.5): generate plain Verilog-2001 from an export package and drive it
with the test vectors of scripts/make_test_vectors.py in Icarus Verilog, one simulation per recording
(the post-processing state starts from reset in each). Score, decision and alarm must agree with the
golden model on every second: 100 % or the check fails.

Usage:  python scripts/verify_verilog.py --export export/<model_id> [--max-windows 20000]
Output: <export>/rtl/lutnet_classifier.v and <export>/verilog_check.json
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

import numpy as np

from seizelut.features import spec as S
from seizelut.hw.export import load_export
from seizelut.hw.verilog import generate, make_testbench, simulate, write_vectors


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--export", required=True)
    ap.add_argument("--max-windows", type=int, default=0, help="per recording, 0 = all (simulation time)")
    args = ap.parse_args()
    exp = Path(args.export)
    pkg = load_export(exp)
    vec = exp / "vectors"
    man = json.loads((vec / "manifest.json").read_text())
    (exp / "rtl").mkdir(exist_ok=True)
    info = generate(pkg, exp / "rtl" / "lutnet_classifier.v")
    out = {"rtl": "rtl/lutnet_classifier.v", "recordings": {}, "all_pass": True}
    for key, rec in man["recordings"].items():
        n = rec["n_windows"] if not args.max_windows else min(rec["n_windows"], args.max_windows)
        X = np.fromfile(vec / key / "features.i16", dtype=np.int16).reshape(-1, len(S.FEATURES))[:n]
        art = np.fromfile(vec / key / "artefact.u8", dtype=np.uint8).reshape(-1, 2)[:n].astype(bool)
        golden = {"score": np.fromfile(vec / key / "score.i32", dtype=np.int32)[:n],
                  "decision": np.fromfile(vec / key / "decision.u8", dtype=np.uint8)[:n],
                  "alarm": np.fromfile(vec / key / "alarm.u8", dtype=np.uint8)[:n]}
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            nv = write_vectors(pkg, info, X, art, golden, td / "vectors.hex", full_features=True)
            make_testbench(pkg, info, td / "vectors.hex", nv, td / "tb.v")
            ok, log = simulate(td, exp / "rtl" / "lutnet_classifier.v", td / "tb.v")
        out["recordings"][key] = {"windows": int(n), "pass": bool(ok), "simulator_output": log.strip().splitlines()[-3:]}
        out["all_pass"] &= bool(ok)
        print(f"{key}: {n} windows {'PASS' if ok else 'FAIL'}", flush=True)
    (exp / "verilog_check.json").write_text(json.dumps(out, indent=1))
    print("ALL PASS" if out["all_pass"] else "FAILED")
    return 0 if out["all_pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
