#!/usr/bin/env python3
"""Fault list for the board's fault campaign and the testbench (after scripts/fault_analysis.py and
scripts/make_kv260_rtl.py).

hw/kv260/board/fault_list.json: every single fault (3,200 truth-table bits, 292 comparator and 100 LUT-output
stuck-at faults) with its effect on the 96 training patients' windows: observable (changes some score) and, per
operating point, whether it changes a decision or an alarm.
hw/kv260/sim/fi_cases.hex: the same faults with the BIST error count and first failing vector that the software
model predicts for the current BIST ROM (testbench +fi=... +nfi=...).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "hw/kv260/board"))
THRS = (9, 2, -7)


def main() -> int:
    from seizelut_model import SeizeLUTModel
    c = np.load(REPO / "cache/fault/fault_counts.npz")
    bv = np.load(REPO / "hw/kv260/board/seizelut_bist_vectors.npz")
    model = SeizeLUTModel(REPO / "hw/kv260/board/model")
    golden = {"score": bv["score"].astype(np.int64), "decision": bv["decision"], "alarm": bv["alarm"]}
    L, B = c["tt_hits"].shape[0], c["sab_score"].shape[0]
    faults = []
    for j in range(L):
        for a in range(64):
            f = {"kind": "tt", "idx": j, "addr": a, "observable": bool(c["tt_hits"][j, a] > 0),
                 "windows": int(c["tt_hits"][j, a])}
            for t in THRS:
                f[f"decision_{t}"] = bool(c[f"tt_dec_{t}"][j, a] > 0)
                f[f"alarm_{t}"] = bool(c[f"tt_alarm_{t}"][j, a] > 0)
            faults.append(f)
    for pre, n, kind in (("sab", B, "sab"), ("sal", L, "sal")):
        for i in range(n):
            for v in (0, 1):
                f = {"kind": f"{kind}{v}", "idx": i, "observable": bool(c[f"{pre}_score"][i, v] > 0),
                     "windows": int(c[f"{pre}_score"][i, v])}
                for t in THRS:
                    f[f"decision_{t}"] = bool(c[f"{pre}_dec_{t}"][i, v] > 0)
                    f[f"alarm_{t}"] = bool(c[f"{pre}_alarm_{t}"][i, v] > 0)
                faults.append(f)
    lines = []
    kind_code = {"tt": (1, 0), "sab0": (2, 0), "sab1": (2, 1), "sal0": (3, 0), "sal1": (3, 1)}
    for f in faults:
        k = f["kind"]
        ft = {"tt": [f["idx"]], "addr": f["addr"]} if k == "tt" else {{"sab0": "b0", "sab1": "b1", "sal0": "l0",
                                                                         "sal1": "l1"}[k]: [f["idx"]]}
        err, first = model.bist(bv["feats"], bv["art"], golden, ft)
        f["bist_err"], f["bist_first"] = err, first
        code, v = kind_code[k]
        word = (code | (v << 2) | (f["idx"] << 3) | (f.get("addr", 0) << 11) | ((err & 0xFFFF) << 17)
                | (((first if first >= 0 else 0xFFFF) & 0xFFFF) << 33))
        lines.append(f"{word:016x}")
    (REPO / "hw/kv260/board/fault_list.json").write_text(json.dumps(
        {"source": "scripts/fault_analysis.py on the 96 training patients; BIST prediction for the current ROM",
         "n": len(faults), "faults": faults}))
    (REPO / "hw/kv260/sim/fi_cases.hex").write_text("\n".join(lines) + "\n")
    det = np.array([f["bist_err"] > 0 for f in faults])
    for cls in ("observable", "decision_9", "decision_2", "decision_-7", "alarm_9"):
        m = np.array([f[cls] for f in faults])
        print(f"{cls}: {m.sum()} faults, predicted detected {(det & m).sum()} ({100 * (det & m).sum() / max(1, m.sum()):.2f} %)")
    print(len(faults), "faults")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
