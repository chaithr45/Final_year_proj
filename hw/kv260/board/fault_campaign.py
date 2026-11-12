#!/usr/bin/env python3
"""On-board fault-injection campaign (needs core version 2, kit v5).

Every single fault of the classifier is injected through the core's fault-injection registers, one at a time:
  tt     truth-table bit flipped: LUT j, entry a           (50 x 64 = 3,200 faults)
  sab0/1 comparator output i stuck at 0 / 1                (146 x 2 = 292)
  sal0/1 LUT output j stuck at 0 / 1                       (50 x 2 = 100)
After each injection the on-chip self-test (BIST) runs once, and its error count and first failing vector are read
back. The software model predicts both numbers for the same fault (seizelut_model.SeizeLUTModel.bist); the campaign
checks that the hardware agrees on every fault, and reports which faults the self-test detects. fault_list.json says,
for each fault, whether it changes any score, decision or alarm on the 9,000 hours of the 96 training patients
(computed in the project repository by scripts/fault_analysis.py), so the detected fraction of the faults that matter
is measured on the board.

Usage (board, as root, PYNQ venv):  python3 fault_campaign.py                (or: --backend emu without a board)
Output: results/kv260_faults_<time>_<backend>.json
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent


def run_bist(core, timeout_s: float = 1.0) -> tuple[int, int, int]:
    """One BIST pass; returns (errors, first error index or -1, ok count)."""
    core.write("CTRL", 0x4)
    time.sleep(0.001)
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        st = core.read("STATUS")
        if st & 0x4 and not st & 0x2:
            break
    else:
        raise TimeoutError("BIST did not finish")
    err, first, ok = core.read("BIST_ERR"), core.read("BIST_FIRSTERR"), core.read("BIST_OK")
    return err, (-1 if first == 0xFFFFFFFF else first), ok


def fault_list(cfg: dict) -> list[dict]:
    p = HERE / "fault_list.json"
    if p.exists():
        return json.loads(p.read_text())["faults"]
    nb, nl = cfg["n_bits"], cfg["n_last_luts"]          # without the relevance file: all faults, no classes
    out = [{"kind": "tt", "idx": j, "addr": a} for j in range(nl) for a in range(64)]
    out += [{"kind": f"sab{v}", "idx": i} for i in range(nb) for v in (0, 1)]
    out += [{"kind": f"sal{v}", "idx": j} for j in range(nl) for v in (0, 1)]
    return out


def as_fault(f: dict) -> dict:
    k = f["kind"]
    if k == "tt":
        return {"tt": [f["idx"]], "addr": f["addr"]}
    return {{"sab0": "b0", "sab1": "b1", "sal0": "l0", "sal1": "l1"}[k]: [f["idx"]]}


def campaign(core, model, max_faults: int = 0, log=print) -> dict:
    info = core.read("INFO")
    if (info & 0xFF) < 2:
        return {"skipped": "this bitstream has no fault-injection registers (core version < 2, kit v4 or older)"}
    bv = np.load(HERE / "seizelut_bist_vectors.npz")
    golden = {"score": bv["score"].astype(np.int64), "decision": bv["decision"], "alarm": bv["alarm"]}
    faults = fault_list(core.cfg)
    if max_faults:
        faults = faults[:: max(1, len(faults) // max_faults)][:max_faults]
    core.clear_faults()
    core.soft_reset()
    e0, _, ok0 = run_bist(core)
    if e0:
        return {"error": f"BIST fails without any fault ({e0} errors): wrong bitstream or vector file"}
    t0 = time.time()
    rows, mismatches = [], 0
    for n, f in enumerate(faults):
        reg = core.set_fault(f["kind"], f["idx"], f.get("addr", 0))
        err, first, _ = run_bist(core)
        core.write(reg, 0)
        exp_err, exp_first = model.bist(bv["feats"], bv["art"], golden, as_fault(f))
        same = (err == exp_err) and (first == exp_first)
        mismatches += not same
        rows.append({**f, "hw_err": err, "hw_first": first, "sw_err": exp_err, "sw_first": exp_first})
        if not same and mismatches <= 10:
            log(f"    MISMATCH {f}: hardware {err} errors (first {first}), software {exp_err} (first {exp_first})")
        if (n + 1) % 500 == 0:
            log(f"    {n + 1}/{len(faults)} faults injected, {time.time() - t0:.1f} s")
    secs = time.time() - t0
    core.clear_faults()
    e1, _, _ = run_bist(core)
    det = np.array([r["hw_err"] > 0 for r in rows])

    def frac(mask):
        m = np.array(mask, bool)
        return {"faults": int(m.sum()), "detected": int((det & m).sum()),
                "detected_pct": round(100.0 * (det & m).sum() / m.sum(), 2) if m.sum() else None}

    out = {"faults_injected": len(rows), "hw_sw_mismatches": mismatches, "seconds": round(secs, 2),
           "ms_per_fault": round(1000 * secs / max(1, len(rows)), 3), "bist_vectors": int(len(bv["feats"])),
           "bist_selected_vectors": int(bv["n_selected"]) if "n_selected" in bv else 0,
           "bist_after_clearing_errors": int(e1),
           "detected_all": frac([True] * len(rows))}
    for cls in ("observable", "decision_9", "decision_2", "decision_-7", "alarm_9", "alarm_2", "alarm_-7"):
        if rows and cls in faults[0]:
            out[f"detected_{cls}"] = frac([f[cls] for f in faults])
    by_kind = {}
    for k in ("tt", "sab0", "sab1", "sal0", "sal1"):
        m = [r["kind"] == k for r in rows]
        if any(m):
            by_kind[k] = frac(m)
    out["by_kind"] = by_kind
    out["undetected_relevant"] = [{k: r[k] for k in ("kind", "idx", "addr") if k in r}
                                  for r, f in zip(rows, faults) if r["hw_err"] == 0 and f.get("decision_9")][:50]
    out["pass"] = mismatches == 0 and e1 == 0
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--backend", default="pynq", choices=["pynq", "devmem", "emu"])
    ap.add_argument("--bit", default=str(HERE / "seizelut.bit"))
    ap.add_argument("--base", type=lambda s: int(s, 0))
    ap.add_argument("--max-faults", type=int, default=0, help="inject an evenly spaced subset (0: all)")
    args = ap.parse_args()
    from seizelut_kv260 import SeizeLUT
    from seizelut_model import SeizeLUTModel
    core = SeizeLUT(args.backend, bitfile=args.bit, base=args.base)
    model = SeizeLUTModel(HERE / "model")
    print("fault-injection campaign:", core.identify())
    res = campaign(core, model, args.max_faults)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    out = HERE / "results" / f"kv260_faults_{stamp}_{args.backend}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(res, indent=1))
    print(json.dumps({k: v for k, v in res.items() if k != "undetected_relevant"}, indent=1))
    print(("PASS" if res.get("pass") else "FAIL"), "->", out)
    return 0 if res.get("pass") else 1


if __name__ == "__main__":
    raise SystemExit(main())
