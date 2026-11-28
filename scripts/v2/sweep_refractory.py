#!/usr/bin/env python3
"""Paper-metric sensitivity at each FA/h budget versus the alarm refractory period (training CV only).
Usage: python scripts/v2/sweep_refractory.py <run> [<run> ...] --gaps 0 30 60 120 300
Writes results/v2/refractory.json (run -> gap -> budget -> best over k)."""
import argparse, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness import REPO, load_meta, load_oof, paper_curve, sens_at, BUDGETS_FAH  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("runs", nargs="+")
ap.add_argument("--gaps", nargs="+", type=int, default=[0, 30, 60, 120, 300])
ap.add_argument("--ks", nargs="+", type=int, default=[1, 4, 10])
a = ap.parse_args()
meta = load_meta()
out = REPO / "results/v2/refractory.json"
res = json.loads(out.read_text()) if out.exists() else {}
for run in a.runs:
    sc = load_oof(run, meta)
    for g in a.gaps:
        best = {}
        for k in a.ks:
            cur = paper_curve(sc, meta, k=k, gap=g)
            for b in BUDGETS_FAH:
                r = sens_at(cur, b)
                if r and (str(b) not in best or r[2] > best[str(b)]["sens"]):
                    best[str(b)] = {"k": k, "th": r[0], "fa_h": r[1], "sens": r[2], "on": r[3]}
        print(run, "gap", g, " ".join(f"{b}:{best[b]['sens']:.3f}" for b in best), flush=True)
        res = json.loads(out.read_text()) if out.exists() else {}  # re-read: other sweeps may write too
        res.setdefault(run, {})[str(g)] = best
        out.write_text(json.dumps(res, indent=1))
