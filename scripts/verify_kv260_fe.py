#!/usr/bin/env python3
"""Kit v6: end-to-end check of the KV260 core with the front end in the fabric (core version 3), in Verilator.

The testbench hw/kv260/sim/tb_seizelut_fe.v drives raw samples through the AXI4-Lite registers exactly as the board
software does (FE window writes, FE_CTRL events, FE_STATUS polling); the core's feature engine computes the 38
features, the core copies them into the classifier and classifies; every window's features (read back from the feature
registers), score, decision and alarm are compared with the golden vectors of the exported model. After the recording
it restores the engine's register file through the FE window and replays the first 30 seconds.
Needs hw/kv260/sim/fe_vectors (python scripts/verify_fe_engine.py --tb) and hw/kv260/sim/vectors.
Usage: python scripts/verify_kv260_fe.py [--rec sub-097_run-10 ...] [--jobs 2]
Output: hw/kv260/results/fe_core_verification.json
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
HW = REPO / "hw/kv260"
SRCS = ["sim/tb_seizelut_fe.v", "rtl/seizelut_axi.v", "rtl/lutnet_classifier.v", "rtl/seizelut_bist_rom.v",
        "rtl/fe_engine_inline.v"]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rec", nargs="*")
    ap.add_argument("--jobs", type=int, default=2)
    args = ap.parse_args()
    recs = args.rec or sorted(p.name[:-5] for p in (HW / "sim/fe_vectors").glob("*.json"))
    subprocess.run(["verilator", "--binary", "--timing", "-j", "4", "-Wno-fatal", "-Wno-lint", "-Wno-style",
                    "-Wno-WIDTHEXPAND", "-Wno-WIDTHTRUNC", "--top-module", "tb_seizelut_fe", "-Irtl/fe", *SRCS,
                    "-Mdir", "build/vcore_fe", "-o", "tb"], cwd=HW, check=True, capture_output=True)
    n_ram = json.loads((HW / "rtl/seizelut_regs.json").read_text())["fe"]["n_ram"]

    def run(rec):
        info = json.loads((HW / f"sim/fe_vectors/{rec}.json").read_text())
        pres = sum(b << i for i, b in enumerate(info["presence"]))
        t0 = time.time()
        r = subprocess.run(["build/vcore_fe/tb", f"+samples=sim/fe_vectors/{rec}.samples.hex",
                            f"+vec=sim/vectors/{rec}.hex", f"+nsec={info['seconds']}", f"+nwin={info['windows']}",
                            f"+pres={pres}", "+ram=rtl/fe/fe_ram.hex", f"+nram={n_ram}", "+replay=30"],
                           cwd=HW, capture_output=True, text=True)
        out = r.stdout
        ok = re.search(r"^PASS (\d+) windows, 0 mismatches", out, re.M)
        eng = re.search(r"ENGINE (\d+) busy cycles for (\d+) seconds \((\d+) per second\)", out)
        bus = re.search(r"BUS (\d+) us of simulated time per second", out)
        rep = re.search(r"REPLAY (\d+) windows checked", out)
        res = {"seconds": info["seconds"], "windows": info["windows"],
               "sensors_present": dict(zip(("ecg", "emg", "acc", "gyr"), info["presence"])), "pass": bool(ok),
               "windows_checked": int(ok.group(1)) if ok else None,
               "engine_busy_cycles_per_second": int(eng.group(3)) if eng else None,
               "axi_us_per_second_of_signal": int(bus.group(1)) if bus else None,
               "replay_windows_after_restore": int(rep.group(1)) if rep else None,
               "seconds_sim": round(time.time() - t0, 1)}
        if not ok:
            res["log_tail"] = out[-3000:]
        print(rec, res, flush=True)
        return rec, res

    with ThreadPoolExecutor(args.jobs) as ex:
        runs = dict(ex.map(run, recs))
    summary = {"what": "core version 3 (seizelut_axi.v with fe_engine_inline.v) driven through AXI4-Lite from raw "
                       "samples: per window the 38 features in the feature registers, score, decision and alarm "
                       "against the golden vectors; engine register file restored through the FE window and the "
                       "first 30 s replayed",
               "simulator": "Verilator", "recordings": len(runs),
               "windows": sum(r["windows"] for r in runs.values()),
               "all_pass": all(r["pass"] for r in runs.values()), "runs": runs}
    (HW / "results/fe_core_verification.json").write_text(json.dumps(summary, indent=1))
    print(json.dumps({k: v for k, v in summary.items() if k != "runs"}, indent=1))
    return 0 if summary["all_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
