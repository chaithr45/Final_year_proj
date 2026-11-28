#!/usr/bin/env python3
"""Blend out-of-fold score sets by a weighted mean of log-odds (no fitting on labels) and score the blend.
Usage: python scripts/v2/blend.py --name b1 --runs runA runB --weights 1 1 [--gap 0]
Output: cache/oof/v2_blend_<name>/, results/v2/harness.json entry v2_blend_<name>."""
import argparse, json, sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness import REPO, load_meta, load_oof, evaluate, line  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--name", required=True)
ap.add_argument("--runs", nargs="+", required=True)
ap.add_argument("--weights", nargs="+", type=float)
ap.add_argument("--gap", type=int, default=0)
ap.add_argument("--no-save", action="store_true")
a = ap.parse_args()
w = np.array(a.weights or [1.0] * len(a.runs)); w = w / w.sum()
meta = load_meta()
sets = [load_oof(r, meta) for r in a.runs]
lg = lambda p: np.log(np.clip(p, 1e-6, 1 - 1e-6) / (1 - np.clip(p, 1e-6, 1 - 1e-6)))
bl = [1 / (1 + np.exp(-sum(wi * lg(s[i]) for wi, s in zip(w, sets)))) for i in range(len(meta))]
name = f"v2_blend_{a.name}"
if not a.no_save:
    out = REPO / "cache/oof" / name; out.mkdir(parents=True, exist_ok=True)
    for m, s in zip(meta, bl):
        np.save(out / f"{m['key']}.npy", s.astype(np.float32))
    (out / "config.json").write_text(json.dumps(vars(a), indent=1))
rep = evaluate(bl, meta, gap=a.gap)
rep["blend"] = {"runs": a.runs, "weights": w.tolist()}
res = REPO / "results/v2/harness.json"
allr = json.loads(res.read_text()); allr[name + (f"_gap{a.gap}" if a.gap else "")] = rep
res.write_text(json.dumps(allr, indent=1))
print(line(name, rep), flush=True)
