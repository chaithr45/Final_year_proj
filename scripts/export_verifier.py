#!/usr/bin/env python3
"""Hardware cost of the post-ictal verifier (stage 2 of the pre-registered cascade, D40). Training patients only.

The verifier is retrained exactly as scripts/paper_points_test.py trains it before reading any test data (DWN,
50 LUT6, 8 thresholds, the 24 inputs with the highest LightGBM gain, seed 0, all training-fold candidates of the
pre-registered stage-1 setting), exported as a package with integer comparators, turned into Verilog with the same
generator as the stage-1 classifier and synthesised with the same Yosys script.

Integer inputs: every verifier input is a mean over a power-of-two window (or a difference of such means, a score
mean, a fraction, a duration or a count), so 128 x input is integer away from recording edges; the comparators work
on round(128 x input) in 24 bits with thresholds floor(128 x t). The agreement of this integer verifier with the
trained floating-point one is reported over all training candidates.
Output: results/tables/verifier_hw.json, export/verifier_d96_s0/ (package + verifier_classifier.v)
"""
from __future__ import annotations

import importlib.util
import json
import re
import subprocess
from pathlib import Path

import numpy as np

from seizelut.data.split import official_train_subjects
from seizelut.hw.export import load_export, truth_table_hex
from seizelut.hw.verilog import generate

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("vc", REPO / "scripts/verify_cascade.py")
vc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vc)
SCALE = 128
OUT_DIR = REPO / "export/verifier_d96_s0"


def main() -> int:
    pre = json.loads((REPO / "results/tables/paper_points_prereg.json").read_text())
    c = pre["cascade"]
    recs = vc.collect(pre["cv_run"], c["k1"], [c["th1"]], c["variant"], official_train_subjects())
    Xtr = np.concatenate([r["ev"][c["th1"]][2] for r in recs])
    ytr = np.concatenate([r["ev"][c["th1"]][3] for r in recs])
    print(len(Xtr), "training candidates", int(ytr.sum()), "positive", flush=True)
    pv, (m, cols, med) = vc.fit_score(c["verifier"], Xtr, ytr, Xtr, seed=0)
    names = vc.names(c["variant"])
    Xin = np.where(np.isnan(Xtr[:, cols]), med, Xtr[:, cols]).astype(np.float64)
    # integer package: thresholds floor(SCALE * t) on round(SCALE * x)
    therm, inner = m.therm, m
    th = therm.thresholds
    nb = therm.num_bits
    used = np.unique(inner.exported["layers"][0]["mapping"])
    key_index, ipairs = {}, []
    remap = np.full(th.size, -1, dtype=np.int64)
    for b in used:
        f, i = divmod(int(b), nb)
        key = (f, int(np.floor(SCALE * float(th[f, i]))))
        if key not in key_index:
            key_index[key] = len(ipairs)
            ipairs.append(key)
        remap[b] = key_index[key]
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    fnames = [f"v{k}_{names[cols[k]]}" for k in range(len(cols))]
    fu = sorted({f for f, _ in ipairs})
    (OUT_DIR / "thresholds.json").write_text(json.dumps({
        "features": [{"name": fnames[f], "column": int(f), "width_bits": 24,
                      "thresholds": sorted({t for ff, t in ipairs if ff == f})} for f in fu],
        "input_bits": [{"bit": i, "feature": fnames[f], "threshold": int(t)} for i, (f, t) in enumerate(ipairs)],
        "rule": f"bit = (round({SCALE} x input) > threshold), signed 24-bit compare"}, indent=1))
    layers = inner.exported["layers"]
    maps = [remap[layers[0]["mapping"].astype(np.int64)].tolist()] + [l["mapping"].astype(int).tolist() for l in layers[1:]]
    (OUT_DIR / "mapping.json").write_text(json.dumps({"layers": [{"n_luts": len(mm), "n_inputs": len(mm[0]),
                                                                   "inputs": mm} for mm in maps]}))
    (OUT_DIR / "luts.json").write_text(json.dumps({"layers": [[truth_table_hex(t) for t in l["tables"]] for l in layers]}))
    last = layers[-1]["tables"].shape[0]
    half = (last + 1) // 2
    th2 = float(c["th2"][0])
    (OUT_DIR / "head.json").write_text(json.dumps({"groups": {"background": [0, half], "seizure": [half, last]},
                                                   "decision_threshold": int(np.ceil(th2)), "artefact_gate": "none",
                                                   "k": 1, "n": 2}, indent=1))
    (OUT_DIR / "manifest.json").write_text(json.dumps({"model_type": "dwn verifier", "variant": c["variant"],
                                                       "th2": th2, "inputs": fnames, "scale": SCALE}, indent=1))
    pkg = load_export(OUT_DIR)
    # agreement: integer comparators on round(SCALE x) against the float model's own score
    Xi = np.round(SCALE * Xin).astype(np.int64)
    col = {f["name"]: i for i, f in enumerate(pkg["thresholds"]["features"])}
    fcol = [int(f["column"]) for f in pkg["thresholds"]["features"]]
    bit_col = np.array([col[b["feature"]] for b in pkg["thresholds"]["input_bits"]])
    bit_thr = np.array([b["threshold"] for b in pkg["thresholds"]["input_bits"]])
    h = (Xi[:, fcol][:, bit_col] > bit_thr).astype(np.int64)
    for layer, tabs in zip(pkg["mapping"]["layers"], pkg["luts"]["layers"]):
        mp = np.array(layer["inputs"])
        tt = np.array([[(int(t, 16) >> a) & 1 for a in range(1 << mp.shape[1])] for t in tabs])
        addr = np.zeros((len(h), mp.shape[0]), np.int64)
        for lb in range(mp.shape[1]):
            addr |= h[:, mp[:, lb]] << lb
        h = tt[np.arange(mp.shape[0])[None, :], addr]
    s_int = h[:, half:].sum(1) - h[:, :half].sum(1)
    s_flt = np.asarray(pv)
    same = float((s_int == s_flt).mean())
    acc_same = float(((s_int >= th2) == (s_flt >= th2)).mean())
    v = OUT_DIR / "verifier_classifier.v"
    info = generate(pkg, v, module="verifier_classifier")
    # Yosys, the same script as the three stage-1 classifiers
    ys = f"read_verilog {v.name}; synth_xilinx -family xcup -top verifier_classifier -flatten -abc9; tee -o yosys_stat.txt stat"
    subprocess.run(["yowasp-yosys", "-q", "-p", ys], capture_output=True, text=True, timeout=3000, cwd=OUT_DIR)
    txt = (OUT_DIR / "yosys_stat.txt").read_text()
    cells = {k: int(n) for n, k in re.findall(r"^\s+(\d+)\s+(\S+)$", txt, re.M) if not k.startswith("$")}
    luts = sum(n for k, n in cells.items() if k.startswith("LUT"))   # as for the stage-1 models (INV not counted)
    ffs = sum(n for k, n in cells.items() if k.startswith("FD"))
    res = {"what": "post-ictal verifier (stage 2, pre-registered D40 cascade) as a LUT-native classifier",
           "training_candidates": int(len(Xtr)), "inputs": fnames, "comparators": len(ipairs),
           "luts": luts, "ffs": ffs, "dsp": cells.get("DSP48E2", 0), "cells": cells,
           "score_agreement_int_vs_float": round(same, 5), "decision_agreement_at_th2": round(acc_same, 5),
           "th2": th2, "scale": SCALE, "input_width_bits": 24,
           "tool": "Yosys (yowasp-yosys), read_verilog; synth_xilinx -family xcup -flatten -abc9; stat",
           "note": "classifier only; the 24 window statistics are sums and differences of the integer feature stream "
                   "over power-of-two windows, computed by the processor"}
    if not cells:
        res["yosys_tail"] = txt[-2000:]
    (REPO / "results/tables/verifier_hw.json").write_text(json.dumps(res, indent=1))
    print(json.dumps({k: res[k] for k in ("luts", "ffs", "comparators", "score_agreement_int_vs_float",
                                           "decision_agreement_at_th2")}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
