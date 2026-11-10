#!/usr/bin/env python3
"""RTL of the two LUT-native baselines (TreeLUT, logic-gate network) from their frozen final models, checked
bit-exact against the software models by simulation (Icarus Verilog), for the synthesised cost comparison.

The models are the M6 final models (seed 0); their decision thresholds and k are the best-F1 operating points
chosen on the training folds. The check uses golden features of three of the exported test recordings (the same
recordings the DWN's Verilog was checked on); no model is changed or selected here.

Writes hw/kv260/rtl/baselines/{treelut,lgn}_classifier.v and results/tables/baseline_rtl_check.json.
Usage: python scripts/make_baseline_rtl.py
"""
from __future__ import annotations

import json
import pickle
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

from seizelut.hw.baseline_rtl import generate_lgn, generate_treelut, pack_hex
from seizelut.hw.kv260 import alarm_from_reset

REPO = Path(__file__).resolve().parents[1]
MODELS = {"treelut": "20261108-204448_treelut_w5_final_s0", "lgn": "20261108-215255_lgn_mi40_final_s0"}
RECS = ("sub-100_run-03", "sub-099_run-02", "sub-097_run-10")
SIM = "verilator" if __import__("shutil").which("verilator") else "iverilog"   # Icarus is very slow on TreeLUT


def testbench(module, sw, tw, n, vec):
    lw = 1 + 1 + sw + tw
    return "\n".join([
        "`timescale 1ns/1ps", "module tb;", "reg clk=0, rst=1, valid_in=0;", f"reg [{tw - 1}:0] features=0;",
        f"wire signed [{sw - 1}:0] score;", "wire decision, alarm, out_valid;",
        f"reg [{lw - 1}:0] mem[0:{n - 1}]; reg [{lw - 1}:0] e; integer i, no, err;",
        f"{module} dut(.clk(clk), .rst(rst), .valid_in(valid_in), .features(features), .score(score),"
        " .decision(decision), .alarm(alarm), .out_valid(out_valid));",
        "always #5 clk = ~clk;",
        f"always @(posedge clk) if (!rst && out_valid) begin e = mem[no];"
        f" if (score !== e[{tw + sw - 1}:{tw}] || decision !== e[{lw - 2}] || alarm !== e[{lw - 1}]) begin"
        f" err = err + 1; if (err < 5) $display(\"MISMATCH %0d score %0d exp %0d\", no, score, $signed(e[{tw + sw - 1}:{tw}]));"
        " end no = no + 1; end",
        f"initial begin $readmemh(\"{vec}\", mem); no = 0; err = 0; repeat (3) @(posedge clk); rst = 0;",
        f"for (i = 0; i < {n}; i = i + 1) begin @(negedge clk); features = mem[i][{tw - 1}:0]; valid_in = 1; end",
        "@(negedge clk); valid_in = 0; repeat (8) @(posedge clk);",
        f"if (err == 0 && no == {n}) $display(\"PASS %0d\", no); else $display(\"FAIL %0d errors %0d outputs\", err, no);",
        "$finish; end", "endmodule", ""])


def main() -> int:
    vd = REPO / "export/n4_distill_s0/vectors"
    man = json.loads((vd / "manifest.json").read_text())
    names = man["feature_names"]
    out_dir = REPO / "hw/kv260/rtl/baselines"
    out_dir.mkdir(parents=True, exist_ok=True)
    report = {}
    for name, run in MODELS.items():
        o = pickle.load(open(REPO / "checkpoints" / run / "seed_0.pkl", "rb"))
        m, cols = o["model"], list(o["cols"])
        fn = [names[c] for c in cols]
        op = json.loads((REPO / "results/runs" / run / "final_metrics.json").read_text())["seeds"]["0"]["best_f1"][
            "operating_point"]
        gen = generate_treelut if name == "treelut" else generate_lgn
        rtl = out_dir / f"{name}_classifier.v"
        info = gen(m, fn, op["threshold"], op["k"], rtl)
        checks = {}
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            for rec in RECS:
                X = np.fromfile(vd / rec / "features.i16", dtype=np.int16).reshape(-1, len(names)).astype(np.int64)[:, cols]
                sc = m.score_int(X) if name == "treelut" else np.asarray(m.score(X)).astype(np.int64)
                dec = (sc >= info["threshold_int"]).astype(np.uint8)
                al = alarm_from_reset(dec, op["k"])
                vec = td / f"{rec}.hex"
                vec.write_text("\n".join(pack_hex(X, info["widths"], [(al, 1), (dec, 1), (sc, info["score_bits"])])) + "\n")
                (td / "tb.v").write_text(testbench(info["module"], info["score_bits"], info["feature_bus_bits"], len(X),
                                                   vec.name))
                if SIM == "verilator":
                    subprocess.run(["verilator", "--binary", "--timing", "-Wno-fatal", "-Wno-WIDTH", "-Wno-UNUSED",
                                    "--top-module", "tb", "-O3", "-j", "4", "--Mdir", str(td / "obj"), str(td / "tb.v"),
                                    str(rtl)], check=True, capture_output=True)
                    r = subprocess.run([str(td / "obj" / "Vtb")], capture_output=True, text=True, cwd=td)
                else:
                    subprocess.run(["iverilog", "-g2005", "-o", str(td / "s.vvp"), str(td / "tb.v"), str(rtl)], check=True)
                    r = subprocess.run(["vvp", "-n", str(td / "s.vvp")], capture_output=True, text=True, cwd=td)
                ok = f"PASS {len(X)}" in r.stdout
                checks[rec] = {"windows": int(len(X)), "pass": ok, "decisions": int(dec.sum()), "alarms": int(al.sum()),
                               "output": [l for l in r.stdout.splitlines() if l.startswith(("PASS", "FAIL", "MISMATCH"))]}
                print(name, rec, len(X), "PASS" if ok else "FAIL", flush=True)
        report[name] = {"run": run, "operating_point": op, "simulator": SIM, **{k: v for k, v in info.items() if k != "widths"},
                        "checks": checks, "all_pass": all(c["pass"] for c in checks.values())}
    (REPO / "results/tables/baseline_rtl_check.json").write_text(json.dumps(report, indent=1, default=int))
    ok = all(r["all_pass"] for r in report.values())
    print("ALL PASS" if ok else "SOME FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
