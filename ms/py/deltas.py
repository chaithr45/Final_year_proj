#!/usr/bin/env python3
"""The two thresholds of "tolerated" (MS_SPEC.md D-MS10): the run-to-run spread of the clean result across 5
training seeds of the frozen recipe, measured on the same data each test uses.

  * full:   all 96 training patients, out-of-fold (ms/py/cv_frozen_op.py -> ms/results/phase1/cv_frozen_op.json);
            used for the full-data confirmations (D-MS5 (2)).
  * subset: the sweep subset (ms/results/phase1/subset.json), clean job of each seed's fold models
            (python ms/py/sweep.py --models <cv_s<s> checkpoints> --grid clean --out
             ms/results/phase1/sweeps/clean_models_s<s>.jsonl); used for the subset tolerance curves.

delta = max(sample standard deviation over the 5 seeds, floor); floors 0.005 (F1) and 0.1 (FP/24 h).

Usage: python ms/py/deltas.py -> ms/results/phase1/deltas.json
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
P1 = REPO / "ms/results/phase1"
FLOOR_F1, FLOOR_FA = 0.005, 0.1


def spread(rows: list[dict]) -> dict:
    f1 = np.array([r["f1"] for r in rows])
    fa = np.array([r["fp_per_24h"] for r in rows])
    se = np.array([r["sensitivity"] for r in rows])
    return {"n_seeds": len(rows), "seeds": [r["seed"] for r in rows],
            "f1": f1.round(6).tolist(), "fp_per_24h": fa.round(6).tolist(), "sensitivity": se.round(6).tolist(),
            "f1_mean": float(f1.mean()), "f1_std": float(f1.std(ddof=1)),
            "fp24_mean": float(fa.mean()), "fp24_std": float(fa.std(ddof=1)),
            "delta_f1": float(max(f1.std(ddof=1), FLOOR_F1)), "delta_fp24": float(max(fa.std(ddof=1), FLOOR_FA))}


def main() -> int:
    out = {"definition": "delta = max(sample std over training seeds of the clean result, floor); floors "
                         f"{FLOOR_F1} (F1), {FLOOR_FA} (FP/24h); MS_SPEC.md D-MS10"}
    full = json.loads((P1 / "cv_frozen_op.json").read_text())
    rows = sorted((v for k, v in full.items() if k != "summary"), key=lambda r: r["seed"])
    out["full"] = spread(rows)
    sub = []
    for p in sorted((P1 / "sweeps").glob("clean_models_s*.jsonl")):
        r = [json.loads(l) for l in p.read_text().splitlines() if l.strip()]
        r = [x for x in r if x["name"] == "clean"]
        assert len(r) == 1, p
        sub.append({**r[0], "seed": int(p.stem.split("_s")[-1])})
    if sub:
        out["subset"] = spread(sorted(sub, key=lambda r: r["seed"]))
    (P1 / "deltas.json").write_text(json.dumps(out, indent=1) + "\n")
    for k in ("full", "subset"):
        if k in out:
            s = out[k]
            print(f"{k:6s}: {s['n_seeds']} seeds  F1 {s['f1_mean']:.4f} +- {s['f1_std']:.4f} -> delta_F1 "
                  f"{s['delta_f1']:.4f} | FP/24h {s['fp24_mean']:.3f} +- {s['fp24_std']:.3f} -> delta_FA "
                  f"{s['delta_fp24']:.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
