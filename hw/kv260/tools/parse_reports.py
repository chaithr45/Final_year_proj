#!/usr/bin/env python3
"""Collect the Vivado build results (out/*.rpt, out/build_summary.txt) into out/build_results.json.

Reads only what the reports say; a missing report or row is recorded as null, never guessed.
Usage: python tools/parse_reports.py [--out out]
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

KIT = Path(__file__).resolve().parents[1]
ROWS = {"lut": ["CLB LUTs", "Slice LUTs"], "ff": ["CLB Registers", "Slice Registers"], "carry8": ["CARRY8"],
        "bram_tile": ["Block RAM Tile"], "dsp": ["DSPs"], "lut_as_logic": ["LUT as Logic"],
        "lut_as_memory": ["LUT as Memory"]}


def _num(s: str):
    s = s.strip().replace(",", "")
    try:
        return float(s) if "." in s else int(s)
    except ValueError:
        return None


def utilization(path: Path) -> dict | None:
    if not path.exists():
        return None
    out = {}
    for line in path.read_text(errors="replace").splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 2:
            continue
        name = cells[0].rstrip("*").strip()
        for key, names in ROWS.items():
            if key not in out and name in names:
                out[key] = _num(cells[1])
                # "Available" is the column before "Util%" in every Vivado layout
                if len(cells) >= 3:
                    out[key + "_available"] = _num(cells[-2])
    return out


def power(path: Path) -> dict | None:
    if not path.exists():
        return None
    txt = path.read_text(errors="replace")
    out = {}
    for key, label in (("total_w", "Total On-Chip Power (W)"), ("dynamic_w", "Dynamic (W)"),
                       ("static_w", "Device Static (W)"), ("confidence", "Confidence Level")):
        m = re.search(r"\|\s*" + re.escape(label) + r"\s*\|\s*([^|]+)\|", txt)
        out[key] = (_num(m.group(1)) if key != "confidence" else m.group(1).strip()) if m else None
    return out


def power_of_cell(path: Path, cell: str) -> float | None:
    """Dynamic power of a hierarchy row (power_hier.rpt) whose name is `cell`."""
    if not path.exists():
        return None
    for line in path.read_text(errors="replace").splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if cells and cells[0] == cell and len(cells) >= 2:
            return _num(cells[1])
    return None


def timing(path: Path) -> dict | None:
    if not path.exists():
        return None
    txt = path.read_text(errors="replace")
    m = re.search(r"WNS\(ns\)\s+TNS\(ns\).*?\n\s*-+.*?\n\s*([-\d.]+)\s+([-\d.]+)\s+\d+\s+\d+\s+([-\d.]+)\s+([-\d.]+)",
                  txt, re.S)
    if not m:
        return None
    return {"wns_ns": float(m.group(1)), "tns_ns": float(m.group(2)), "whs_ns": float(m.group(3)),
            "ths_ns": float(m.group(4))}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=str(KIT / "out"))
    o = Path(ap.parse_args().out)
    summ = {}
    if (o / "build_summary.txt").exists():
        for line in (o / "build_summary.txt").read_text().splitlines():
            if "=" in line and " " not in line.split("=", 1)[0]:
                k, v = line.split("=", 1)
                summ[k] = v
    res = {"summary": summ,
           "classifier_in_design": utilization(o / "utilization_classifier.rpt"),
           "seizelut_core_in_design": utilization(o / "utilization_seizelut_core.rpt"),
           "whole_design": utilization(o / "utilization.rpt"),
           "classifier_out_of_context": utilization(o / "ooc_classifier_utilization.rpt"),
           "timing_design": timing(o / "timing_summary.rpt"),
           "timing_classifier_ooc": timing(o / "ooc_classifier_timing.rpt"),
           "power_design": power(o / "power.rpt"),
           "power_classifier_ooc": power(o / "ooc_classifier_power.rpt"),
           "power_u_cls_dynamic_w": power_of_cell(o / "power_hier.rpt", "u_cls"),
           "bitstream": (o / "seizelut.bit").exists(), "hwh": (o / "seizelut.hwh").exists()}
    (o / "build_results.json").write_text(json.dumps(res, indent=1))
    print(json.dumps({k: res[k] for k in ("classifier_in_design", "classifier_out_of_context", "timing_design",
                                          "power_design")}, indent=1))
    print(f"written {o / 'build_results.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
