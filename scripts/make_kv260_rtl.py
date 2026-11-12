#!/usr/bin/env python3
"""Generate the KV260 RTL kit (hw/kv260/rtl/) from the exported final model.

The BIST ROM opens with the coverage-selected self-test vectors of scripts/fault_analysis.py (training patients) and
is filled with a seizure stretch of an exported recording; the same vectors with their golden outputs go to
hw/kv260/board/seizelut_bist_vectors.npz for the board's fault campaign and the register emulator.
Usage: python scripts/make_kv260_rtl.py [--no-selected]
"""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from seizelut.hw.kv260 import build

REPO = Path(__file__).resolve().parents[1]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--export", default=str(REPO / "export/n4_distill_s0"))
    ap.add_argument("--bist-run", default="sub-098_run-03")
    ap.add_argument("--no-selected", action="store_true", help="BIST from the recording only (kit v4 behaviour)")
    args = ap.parse_args()
    sel = None if args.no_selected else REPO / "cache/fault/selected_vectors.npz"
    rtl = REPO / "hw/kv260/rtl"
    cfg = build(Path(args.export), Path(args.export) / "vectors", rtl, args.bist_run, bist_selected=sel)
    shutil.copy(rtl / "seizelut_regs.json", REPO / "hw/kv260/board/seizelut_regs.json")
    shutil.copy(rtl / "seizelut_bist_vectors.npz", REPO / "hw/kv260/board/seizelut_bist_vectors.npz")
    print(cfg["bist"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
