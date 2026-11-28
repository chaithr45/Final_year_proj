#!/usr/bin/env python3
"""WP4: detection by seizure class (and vigilance, duration) at a paper-metric operating point, training CV only.
A seizure counts as detected when at least one raw alarm-on second overlaps it (the paper's any-overlap rule).
Usage: python scripts/v2/by_type.py <run> --budget 5 [--k 10 --th 0.05] [--oof <dir>]
Detection uses raw alarm seconds, so it is the same with or without a refractory period.  (default: harness.json paper_best point)
Output: results/v2/by_type.json (run -> budget -> table)."""
import argparse, csv, json, sys
from collections import defaultdict
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness import REPO, load_meta, load_oof, kth_of_last  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("run"); ap.add_argument("--budget", default="5.0")
ap.add_argument("--k", type=int); ap.add_argument("--th", type=float)
ap.add_argument("--oof", help="OOF directory name if it differs from the harness.json key")
a = ap.parse_args()
b = str(float(a.budget))
if a.k is None:
    hb = json.loads((REPO / "results/v2/harness.json").read_text())[a.run]["paper_best"][b]
    a.k, a.th = hb["k"], hb["th"]
info = {}
for r in csv.DictReader(open(REPO / "results/audit/seizures.csv")):
    info[(f"{r['subject']}_{r['run']}", round(float(r["onset_s"])))] = r
meta = load_meta(); sc = load_oof(a.oof or a.run, meta)
groups = defaultdict(lambda: [0, 0])
for m, s in zip(meta, sc):
    if not len(m["seizures"]):
        continue
    al = kth_of_last(s, a.k) >= a.th
    for on, en in m["seizures"]:
        r = info.get((m["key"], round(on)))
        lo, hi = int(on), max(int(on) + 1, int(np.ceil(en)))
        det = bool(al[lo:hi].any())
        dur = en - on
        keys = ["all", "class:" + (r["class"] if r else "unmatched"),
                "vigilance:" + (r["vigilance"] if r else "n/a"),
                "duration:" + ("<20s" if dur < 20 else "20-60s" if dur < 60 else ">=60s")]
        for kk in keys:
            groups[kk][0] += 1; groups[kk][1] += det
tab = {kk: {"n": n, "detected": d, "sens": d / n} for kk, (n, d) in sorted(groups.items())}
out = REPO / "results/v2/by_type.json"
res = json.loads(out.read_text()) if out.exists() else {}
res.setdefault(a.run, {})[b] = {"k": a.k, "th": a.th, "table": tab}
out.write_text(json.dumps(res, indent=1))
for kk, v in tab.items():
    print(f"{kk:32s} {v['detected']:4d}/{v['n']:4d}  {v['sens']:.3f}")
