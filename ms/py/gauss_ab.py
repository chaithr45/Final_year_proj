#!/usr/bin/env python3
"""Generator A/B (MS_SPEC.md D-MS7, LOG L12 and L17): does the 64-uniform-sum noise generator of the fabric give the
detector the same result as an exact Gaussian of the same rms?

Input: ms/results/phase1/sweeps/gauss_ab.jsonl (written by `sweep.py --grid gauss_ab --seeds 0 1 2 3 4`): the clean
run plus, at one EEG white-noise level (rule in grids.gauss_ab_level), 5 seeds with each generator.

Criterion, fixed 16 Nov before any EEG sweep result (LOG L17), with the subset deltas of D-MS10:
  same  <=>  |mean F1(64-sum) - mean F1(exact)| <= delta_F1  and  |mean FP24(64-sum) - mean FP24(exact)| <= delta_FA
Also reported (information, not part of the criterion): the D-MS10 verdict at that level with each generator.
If "same" fails, D-MS7's fall-back applies (inverse-CDF table) and the EEG noise curve is re-run.

Usage: python ms/py/gauss_ab.py  -> ms/results/phase1/gauss_ab.json
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
P1 = REPO / "ms/results/phase1"


def compare(clean: dict, rows: list[dict], d_f1: float, d_fa: float) -> dict:
    gen = {"sum64": [r for r in rows if not r["name"].endswith("_refgauss")],
           "exact": [r for r in rows if r["name"].endswith("_refgauss")]}
    out = {}
    for k, rs in gen.items():
        if not rs:
            raise SystemExit(f"no rows for generator {k}")
        f1 = np.array([r["f1"] for r in rs]); fa = np.array([r["fp_per_24h"] for r in rs])
        out[k] = {"names": sorted({r["name"] for r in rs}), "seeds": sorted(r["seed"] for r in rs),
                  "f1": f1.tolist(), "fp_per_24h": fa.tolist(),
                  "f1_mean": float(f1.mean()), "fp24_mean": float(fa.mean()),
                  "d_f1": float(f1.mean() - clean["f1"]), "d_fp24": float(fa.mean() - clean["fp_per_24h"])}
        out[k]["tolerated"] = bool(-out[k]["d_f1"] <= d_f1 and out[k]["d_fp24"] <= d_fa)
    diff_f1 = out["sum64"]["f1_mean"] - out["exact"]["f1_mean"]
    diff_fa = out["sum64"]["fp24_mean"] - out["exact"]["fp24_mean"]
    return {"generators": out, "diff_f1": diff_f1, "diff_fp24": diff_fa,
            "same": bool(abs(diff_f1) <= d_f1 and abs(diff_fa) <= d_fa),
            "same_verdict": out["sum64"]["tolerated"] == out["exact"]["tolerated"]}


def main() -> int:
    rows = [json.loads(l) for l in (P1 / "sweeps/gauss_ab.jsonl").read_text().splitlines() if l.strip()]
    clean = [r for r in rows if r["name"] == "clean"]
    if len(clean) != 1:
        raise SystemExit(f"expected one clean row, found {len(clean)}")
    d = json.loads((P1 / "deltas.json").read_text())["subset"]
    res = compare(clean[0], [r for r in rows if r["name"] != "clean"], d["delta_f1"], d["delta_fp24"])
    res = {"criterion": "same <=> |dF1 between generators| <= delta_F1 and |dFP24| <= delta_FA (subset deltas, LOG L17)",
           "delta_f1": d["delta_f1"], "delta_fp24": d["delta_fp24"],
           "clean": {k: clean[0][k] for k in ("f1", "fp_per_24h")}, **res}
    (P1 / "gauss_ab.json").write_text(json.dumps(res, indent=1) + "\n")
    g = res["generators"]
    for k in ("sum64", "exact"):
        print(f"{k:6s} {g[k]['names'][0]}: F1 {g[k]['f1_mean']:.4f} FP/24h {g[k]['fp24_mean']:.3f} "
              f"tolerated {g[k]['tolerated']}")
    print(f"difference F1 {res['diff_f1']:+.4f} (limit {d['delta_f1']:.4f}), FP/24h {res['diff_fp24']:+.3f} "
          f"(limit {d['delta_fp24']:.3f}) -> {'SAME' if res['same'] else 'DIFFERENT'}; "
          f"verdicts {'agree' if res['same_verdict'] else 'differ'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
