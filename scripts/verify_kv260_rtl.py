#!/usr/bin/env python3
"""Verify the KV260 core (hw/kv260/rtl) with Verilator through its AXI4-Lite registers.

Runs the testbench hw/kv260/sim/tb_seizelut_axi.v on every exported recording (hw/kv260/sim/vectors/*.hex, written
by hw/kv260/tools/make_board_vectors.py --tb) at two programmable operating points: score, decision, alarm, the
programmable path, debug taps, LEDs, button and one BIST pass per run. One extra run injects every single fault
listed in hw/kv260/sim/fi_cases.hex (scripts/make_fault_list.py) and checks each BIST error count and first failing
vector against the software prediction. Output: hw/kv260/results/simulation_verification.json
Usage: python scripts/verify_kv260_rtl.py [--jobs 2] [--quick]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
KIT = REPO / "hw/kv260"
OPS = ((2, 10), (-7, 10))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--jobs", type=int, default=2)
    ap.add_argument("--quick", action="store_true", help="only the bundled recording")
    args = ap.parse_args()
    build = KIT / "build/verilator"
    build.mkdir(parents=True, exist_ok=True)
    srcs = [KIT / "sim/tb_seizelut_axi.v"] + [KIT / "rtl" / f for f in
                                              ("seizelut_axi.v", "lutnet_classifier.v", "seizelut_bist_rom.v")]
    t0 = time.time()
    subprocess.run(["verilator", "--binary", "--timing", "-j", "4", "-Wno-fatal", "-Wno-lint", "-Wno-style",
                    "--top-module", "tb_seizelut_axi", "-Mdir", str(build), "-o", "tb", *map(str, srcs)],
                   check=True, capture_output=True)
    exe = build / "tb"
    print(f"built in {time.time() - t0:.0f} s", flush=True)
    vecs = sorted((KIT / "sim/vectors").glob("*.hex"))
    if args.quick:
        vecs = [v for v in vecs if v.name == "sub-097_run-10.hex"]
    n_lines = {v: sum(1 for _ in open(v)) for v in vecs}
    fi = KIT / "sim/fi_cases.hex"
    n_fi = sum(1 for _ in open(fi)) if fi.exists() else 0
    jobs = [(v, thr, k, 0) for v in vecs for thr, k in OPS]
    small = KIT / "sim/vectors/sub-097_run-10.hex"
    if n_fi:
        jobs.append((small, 2, 10, n_fi))

    def run(job):
        v, thr, k, nfi = job
        cmd = [str(exe), f"+vec={v}", f"+n={n_lines[v]}", f"+thr2={thr}", f"+k2={k}"]
        if nfi:
            cmd += [f"+fi={fi}", f"+nfi={nfi}"]
        t = time.time()
        r = subprocess.run(cmd, capture_output=True, text=True)
        lines = [l for l in r.stdout.splitlines() if l.strip() and "$finish" not in l]
        ok = any(l.startswith("PASS") for l in lines)
        key = f"{v.stem}|{thr}|{k}" + (f"|faults{nfi}" if nfi else "")
        print(key, "PASS" if ok else "FAIL", f"{time.time() - t:.0f} s", flush=True)
        return key, {"windows": n_lines[v], "fault_cases": nfi, "pass": ok, "output": lines[-12:]}

    with ThreadPoolExecutor(args.jobs) as ex:
        runs = dict(ex.map(run, jobs))
    window_checks = sum(r["windows"] for k, r in runs.items() if not r["fault_cases"])
    out = {"simulator": "Verilator (testbench sim/tb_seizelut_axi.v; the same testbench runs on Icarus Verilog 12)",
           "rtl": "rtl/seizelut_axi.v (core version 2: PMOD I/O, debug taps, fault injection, coverage-selected BIST) "
                  "+ rtl/lutnet_classifier.v + rtl/seizelut_bist_rom.v",
           "recordings": len(vecs), "windows_per_pass": window_checks // max(1, len(OPS)),
           "operating_points_programmable": [f"thr {t}, k {k}" for t, k in OPS], "window_checks": window_checks,
           "fault_cases": n_fi, "all_pass": all(r["pass"] for r in runs.values()),
           "checks": ("per window: score, decision, alarm (frozen) and decision2, alarm2 (programmable) via AXI4-Lite; "
                      "the 146 comparator bits and 50 LUT outputs read back through DBG_BITS/DBG_LUTS; PMOD LED "
                      "pattern; per run: counters, latency (3 cycles), ID/INFO/SCRATCH/OP registers, manual LEDs, "
                      "button debounce, one BIST pass; fault run: every single fault injected through the FI "
                      "registers, BIST error count and first failing vector equal to the software model's prediction, "
                      "then a clean BIST pass after clearing"),
           "runs": runs}
    (KIT / "results/simulation_verification.json").write_text(json.dumps(out, indent=1))
    print("ALL PASS" if out["all_pass"] else "FAILURES", window_checks, "window checks,", n_fi, "fault cases")
    return 0 if out["all_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
