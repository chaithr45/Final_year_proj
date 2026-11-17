#!/usr/bin/env python3
"""Synthesise the fabric feature engine (hw/kv260/rtl/fe_engine.v with rtl/fe/*.hex) with the same Yosys flow as the
classifiers and write results/tables/fe_engine_hw.json, including the whole detector (feature engine + classifier).
Usage: python scripts/synth_fe_engine.py
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
RTL = REPO / "hw/kv260/rtl"


def stat(text: str) -> dict:
    return {k: int(n) for n, k in re.findall(r"^\s+(\d+)\s+(\S+)$", text, re.M) if k[0].isupper()}


def main() -> int:
    work = REPO / "hw/kv260/build/yosys_fe"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    for f in (RTL / "fe_engine.v", RTL / "fe/fe_rom.hex", RTL / "fe/fe_ram.hex"):
        shutil.copy(f, work / f.name)
    ys = "read_verilog fe_engine.v; synth_xilinx -family xcup -top fe_engine -flatten -abc9; tee -o stat.txt stat"
    subprocess.run(["yowasp-yosys", "-q", "-p", ys], cwd=work, check=True, capture_output=True, timeout=3000)
    cells = stat((work / "stat.txt").read_text())
    luts = sum(v for k, v in cells.items() if k.startswith("LUT"))
    ffs = sum(v for k, v in cells.items() if k.startswith("FD"))
    bram36 = cells.get("RAMB36E2", 0) + 0.5 * cells.get("RAMB18E2", 0)
    cls = json.loads((REPO / "results/tables/hw_synthesis_yosys.json").read_text())["models"]["dwn_n4_distill"]
    meta = json.loads((RTL / "fe/fe_engine.json").read_text())
    out = {"tool": "Yosys (yowasp-yosys), read_verilog; synth_xilinx -family xcup -flatten -abc9; stat",
           "feature_engine": {"luts": luts, "ffs": ffs, "carry4": cells.get("CARRY4", 0), "dsp": cells.get("DSP48E2", 0),
                              "ramb36": cells.get("RAMB36E2", 0), "ramb18": cells.get("RAMB18E2", 0),
                              "bram36_equivalent": bram36, "cells": cells, "rom_instructions": meta["n_rom"],
                              "ram_words": meta["n_ram"], "datapath_bits": meta["dw"]},
           "classifier": {"luts": cls["luts"], "ffs": cls["ffs"], "dsp": 0, "bram36_equivalent": 0},
           "whole_detector": {"luts": luts + cls["luts"], "ffs": ffs + cls["ffs"], "dsp": cells.get("DSP48E2", 0),
                              "bram36_equivalent": bram36},
           "note": "luts counts LUT1-LUT6 cells as for the classifiers (INV not counted); the engine computes the 38 "
                   "features the classifier reads from raw samples; no multiplier (coefficients are shift-add terms)"}
    (REPO / "results/tables/fe_engine_hw.json").write_text(json.dumps(out, indent=1))
    print(json.dumps({k: (v if k != "feature_engine" else {kk: vv for kk, vv in v.items() if kk != "cells"})
                      for k, v in out.items() if k != "note"}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
