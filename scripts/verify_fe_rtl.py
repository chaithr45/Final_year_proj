#!/usr/bin/env python3
"""N10: RTL check of the fabric feature engine. Builds hw/kv260/rtl/fe_engine.v with its testbench
(hw/kv260/sim/tb_fe_engine.v) in Verilator, streams each recording of hw/kv260/sim/fe_vectors/ through it sample by
sample and compares the 38 features of every window with the C front end. Also reports the busy cycles per second of
signal, which sets the lowest clock at which the engine keeps up with the sensors.
Needs the vectors from `python scripts/verify_fe_engine.py --tb`.
Usage: python scripts/verify_fe_rtl.py [--rec sub-097_run-10 ...]
Output: hw/kv260/results/fe_engine_rtl_verification.json
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
HW = REPO / "hw/kv260"
VEC = HW / "sim/fe_vectors"
VERILATOR = ["verilator", "--binary", "--timing", "-j", "4", "-Wno-fatal", "-Wno-lint", "-Wno-style",
             "-Wno-WIDTHEXPAND", "-Wno-WIDTHTRUNC", "--top-module", "tb_fe_engine", "-Irtl/fe",
             "sim/tb_fe_engine.v", "rtl/fe_engine.v", "-Mdir", "build/vfe", "-o", "tb_fe"]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rec", nargs="*", help="recordings (default: every one in hw/kv260/sim/fe_vectors)")
    args = ap.parse_args()
    recs = args.rec or sorted(p.name[:-5] for p in VEC.glob("*.json"))
    if not recs:
        raise SystemExit("no vectors: run python scripts/verify_fe_engine.py --tb first")
    subprocess.run(VERILATOR, cwd=HW, check=True, capture_output=True)
    meta = json.loads((HW / "rtl/fe/fe_engine.json").read_text())
    runs = {}
    for rec in recs:
        info = json.loads((VEC / f"{rec}.json").read_text())
        pres = sum(b << i for i, b in enumerate(info["presence"]))
        t0 = time.time()
        res = subprocess.run([str(HW / "build/vfe/tb_fe"), f"+samples=../../sim/fe_vectors/{rec}.samples.hex",
                              f"+feats=../../sim/fe_vectors/{rec}.feats.hex", f"+nsec={info['seconds']}",
                              f"+nwin={info['windows']}", f"+pres={pres}"],
                             cwd=HW / "rtl/fe", capture_output=True, text=True, check=True)
        cyc = re.search(r"CYCLES (\d+) busy cycles for (\d+) seconds \((\d+) per second\)", res.stdout)
        ok = re.search(r"PASS (\d+) windows, 0 mismatches", res.stdout)
        runs[rec] = {"seconds": info["seconds"], "windows_expected": info["windows"],
                     "sensors_present": dict(zip(("ecg", "emg", "acc", "gyr"), info["presence"])),
                     "windows_checked": int(ok.group(1)) if ok else None, "bit_exact": bool(ok),
                     "busy_cycles": int(cyc.group(1)), "busy_cycles_per_second": int(cyc.group(3)),
                     "seconds_sim": round(time.time() - t0, 1)}
        if not ok:
            runs[rec]["log_tail"] = res.stdout[-2000:]
        print(rec, runs[rec], flush=True)
    worst = max(r["busy_cycles_per_second"] for r in runs.values())
    out = {"what": "fe_engine.v (Verilator, cycle accurate) fed sample by sample through its host port; 38 classifier "
                   "features of every window compared with the C front end",
           "rom_instructions": meta["n_rom"], "ram_words": meta["n_ram"], "datapath_bits": meta["dw"],
           "cycles_per_instruction": 3, "worst_busy_cycles_per_second": worst,
           "min_clock_mhz_real_time": round(worst / 1e6, 3),
           "note": "busy cycles exclude host writes and reads; the KV260 fabric clock (100 MHz) leaves a margin of "
                   f"about {round(100e6 / worst)}x",
           "all_bit_exact": all(r["bit_exact"] and r["windows_checked"] == r["windows_expected"] for r in runs.values()),
           "runs": runs}
    (HW / "results/fe_engine_rtl_verification.json").write_text(json.dumps(out, indent=1))
    print(json.dumps({k: v for k, v in out.items() if k != "runs"}, indent=1))
    return 0 if out["all_bit_exact"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
