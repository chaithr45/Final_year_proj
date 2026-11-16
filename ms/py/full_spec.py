#!/usr/bin/env python3
"""Full-data tolerance limits (MS_SPEC.md step 7, D-MS5 (2), D-MS10; step-down rule LOG L20).

Combines the subset limits (ms/results/phase1/tolerance.json) with every full-data confirmation
(ms/results/phase1/confirm_<tag>.json, quick runs with "_runs" in the tag ignored) into the limits the spec uses:

  * subset "none tolerated": stays "none tolerated" (spec tighter than the mildest level tested);
  * otherwise, from the subset limit towards milder levels: the first level that is tolerated on the full data
    (full deltas + Wilcoxon p >= 0.05) is the spec limit. A level that fails moves the search one grid step milder;
    a level not yet run on the full data makes the family "pending" and is listed for `confirm_full.py --jobs
    stepdown`. If every level down to the mildest fails, the family becomes "none tolerated".
  * "beyond grid" on the subset and tolerated on the full data at the worst level stays "beyond grid" (a bound).
  * If the full data also tolerates the subset's first failing level, the spec stays at the subset limit (the
    subset curve failed there) and a note says so.

Output: ms/results/phase1/spec_limits.json, the same layout as tolerance.json (grids -> families with status,
limit, levels), plus per family: subset_status, subset_limit, full (verdicts by level name), pending, note. Both
ms/py/combined.py and ms/py/spec_table.py read it when it exists.

Usage: python ms/py/full_spec.py
"""
from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
P1 = REPO / "ms/results/phase1"


def load_full_results(p1: Path = P1) -> dict:
    """Level name -> full-data verdict (seed 0, LOG L18). Identical names in two files must agree."""
    out: dict = {}
    for p in sorted(p1.glob("confirm_*.json")):
        if "_runs" in p.stem:
            continue
        for j in json.loads(p.read_text()).get("jobs", []):
            if j.get("seed", 0) != 0 or "tolerated" not in j:
                continue
            v = {k: j[k] for k in ("tolerated", "d_f1", "d_fp24", "wilcoxon_p", "marginal")} | {"file": p.name}
            if j["name"] in out and out[j["name"]]["tolerated"] != v["tolerated"]:
                raise SystemExit(f"{j['name']}: different full-data verdicts in {out[j['name']]['file']} and {p.name}")
            out.setdefault(j["name"], v)
    return out


def resolve(f: dict, full: dict) -> dict:
    lv = f["levels"]
    names = [x["name"] for x in lv]
    r = {**f, "subset_status": f["status"], "subset_limit": f["limit"], "pending": None, "note": None,
         "full": {n: full[n] for n in names if n in full}}
    if f["status"] == "none tolerated":
        r.update(status="none tolerated", limit=None)
        return r
    idx = next(i for i, x in enumerate(lv) if x["level"] == f["limit"])
    for i in range(idx, -1, -1):
        v = full.get(names[i])
        if v is None:
            r.update(status="pending", limit=None, pending=names[i])
            return r
        if v["tolerated"]:
            beyond = f["status"] == "beyond grid" and i == idx
            r.update(status="beyond grid" if beyond else "limit", limit=lv[i]["level"], limit_unit=lv[i]["unit"])
            if i == idx and f["status"] == "limit" and full.get(names[idx + 1], {}).get("tolerated"):
                r["note"] = "full data also tolerates the subset's first failing level; spec kept at the subset limit"
            if i < idx:
                r["note"] = f"stepped down {idx - i} grid step(s) from the subset limit {f['limit']:g}"
            return r
    r.update(status="none tolerated", limit=None, note="every level up to the subset limit fails on the full data")
    return r


def build(tol: dict, full: dict) -> dict:
    out = {"source": "ms/results/phase1/tolerance.json + confirm_*.json", "rule": "LOG L20, MS_SPEC step 7",
           "grids": {}}
    for g, grid in tol["grids"].items():
        out["grids"][g] = {"families": {k: resolve(f, full) for k, f in grid["families"].items()}}
    return out


def pending_names(spec: dict) -> list[str]:
    return [f["pending"] for g in spec["grids"].values() for f in g["families"].values() if f["pending"]]


def main() -> int:
    tol = json.loads((P1 / "tolerance.json").read_text())
    spec = build(tol, load_full_results())
    (P1 / "spec_limits.json").write_text(json.dumps(spec, indent=1) + "\n")
    for g in spec["grids"].values():
        for k, f in g["families"].items():
            lim = "-" if f["limit"] is None else f"{f['limit']:g}"
            sub = "-" if f["subset_limit"] is None else f"{f['subset_limit']:g}"
            print(f"{k:16s} subset {f['subset_status']:15s} {sub:>6s} -> full {f['status']:15s} {lim:>6s}"
                  f"{'  needs ' + f['pending'] if f['pending'] else ''}{'  (' + f['note'] + ')' if f['note'] else ''}")
    p = pending_names(spec)
    print(f"{len(p)} famil{'y' if len(p) == 1 else 'ies'} pending" + (": run confirm_full.py --jobs stepdown" if p else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
