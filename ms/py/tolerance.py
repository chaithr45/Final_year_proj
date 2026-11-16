#!/usr/bin/env python3
"""Tolerance limits from the subset sweeps (MS_SPEC.md 1.2 steps 5-6, rule D-MS10).

For every parameter family of every swept modality: the levels from mildest to most severe, the seed-averaged
event-F1 and FP/24 h, the verdict per level against the clean run of the same file, and the tolerance limit.

Rule (D-MS10, deltas from ms/results/phase1/deltas.json, "subset"):
  tolerated  <=>  clean_F1 - mean_F1 <= delta_F1  and  mean_FP24 - clean_FP24 <= delta_FA
  limit       =   the most severe level of the unbroken run of tolerated levels that starts at the mildest level
                  ("none" if the mildest level already fails; "beyond grid" if every level is tolerated).
  A tolerated level after a failing one is reported as non-monotonic and does not extend the limit.

Mechanism columns (step 6): comparator bits of the frozen model that differ from the clean run, per window (sum
over the 146 bits of the per-bit flip rate), and the feature that moves most (mean |delta| in feature LSBs).

Usage: python ms/py/tolerance.py [grid ...]   (default: every ms/results/phase1/sweeps/<grid>.jsonl of
       eeg, ecg, emg, mov) -> ms/results/phase1/tolerance.json and ms/results/phase1/tolerance_table.md
"""
from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
P1 = REPO / "ms/results/phase1"
THR = json.loads((REPO / "export/n4_distill_s0/thresholds.json").read_text())["features"]
FEATS = [f["name"] for f in THR]

# family -> (unit, True if a larger number is more severe, label)
FAMILIES = {
    "lsb": (None, True, "LSB q"), "clip": (None, False, "clip level C"), "white": (None, True, "white noise"),
    "pink": ("Hz", True, "1/f corner (1 uV rms white)"), "gain+": ("", True, "gain error +"),
    "gain-": ("", True, "gain error -"), "offset": ("C", True, "DC offset"), "drift": (None, True, "drift (tau 64 s)"),
    "mains50": (None, True, "mains 50 Hz"), "mains250": (None, True, "mains 250 Hz (aliases to 6 Hz)"),
    "hp": ("Hz", True, "high-pass corner"), "lp": ("Hz", False, "low-pass corner"),
}
NAME = re.compile(r"^(eeg|ecg|emg|mov)_([a-z0-9]+)_([+-]?[0-9.]+)([a-zA-Z]*)")


def parse(name: str):
    m = NAME.match(name)
    if not m:
        raise ValueError(name)
    mod, fam, lev, unit = m.group(1), m.group(2), float(m.group(3)), m.group(4)
    if fam == "gain":
        fam = "gain+" if lev > 0 else "gain-"
        lev = abs(lev)
    return mod, fam, lev, unit


def load(path: Path) -> tuple[dict, list[dict]]:
    rows = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
    clean = [r for r in rows if r["name"] == "clean"]
    if len(clean) != 1:
        raise SystemExit(f"{path}: expected one clean row, found {len(clean)}")
    return clean[0], [r for r in rows if r["name"] != "clean"]


def analyse(clean: dict, rows: list[dict], d_f1: float, d_fa: float) -> dict:
    by = defaultdict(list)
    for r in rows:
        by[r["name"]].append(r)
    fams: dict = defaultdict(list)
    for name, rs in by.items():
        mod, fam, lev, unit = parse(name)
        f1 = np.array([r["f1"] for r in rs]); fa = np.array([r["fp_per_24h"] for r in rs])
        se = np.array([r["sensitivity"] for r in rs])
        lvl = {"name": name, "level": lev, "unit": unit, "seeds": sorted(r["seed"] for r in rs),
               "f1": float(f1.mean()), "f1_sd": float(f1.std(ddof=1)) if len(rs) > 1 else None,
               "fp_per_24h": float(fa.mean()), "fp24_sd": float(fa.std(ddof=1)) if len(rs) > 1 else None,
               "sensitivity": float(se.mean()),
               "d_f1": float(f1.mean() - clean["f1"]), "d_fp24": float(fa.mean() - clean["fp_per_24h"]),
               "clipped_samples": int(np.mean([r["clipped_samples"] for r in rs]))}
        lvl["tolerated"] = bool(-lvl["d_f1"] <= d_f1 and lvl["d_fp24"] <= d_fa)
        if all("bit_flip_rate" in r for r in rs):
            flips = np.mean([r["bit_flip_rate"] for r in rs], 0)
            moves = np.mean([r["feat_mean_absdiff"] for r in rs], 0)
            lvl["bit_flips_per_window"] = float(flips.sum())
            top = np.argsort(moves)[::-1][:3]
            lvl["top_features"] = [(FEATS[i], round(float(moves[i]), 3)) for i in top]
        fams[(mod, fam)].append(lvl)
    out = {}
    for (mod, fam), lv in sorted(fams.items()):
        sev = FAMILIES[fam][1]
        lv.sort(key=lambda x: x["level"], reverse=not sev)
        limit, broken, nonmono = None, False, []
        for x in lv:
            if x["tolerated"] and not broken:
                limit = x
            elif not x["tolerated"]:
                broken = True
            else:
                nonmono.append(x["name"])
        status = ("none tolerated" if limit is None and lv else
                  "beyond grid" if not broken else "limit")
        out[f"{mod}/{fam}"] = {"modality": mod, "family": fam, "label": FAMILIES[fam][2], "status": status,
                               "limit": None if limit is None else limit["level"],
                               "limit_unit": None if limit is None else limit["unit"],
                               "first_failing": next((x["level"] for x in lv if not x["tolerated"]), None),
                               "non_monotonic": nonmono, "levels": lv}
    return out


def fmt(v):
    return "-" if v is None else (f"{v:g}")


def main() -> int:
    grids = sys.argv[1:] or [g for g in ("eeg", "ecg", "emg", "mov") if (P1 / f"sweeps/{g}.jsonl").exists()]
    dl = json.loads((P1 / "deltas.json").read_text())
    if "subset" not in dl:
        raise SystemExit("deltas.json has no subset spread yet (D-MS10 deltas must exist before any verdict)")
    d_f1, d_fa = dl["subset"]["delta_f1"], dl["subset"]["delta_fp24"]
    res = {"deltas": {"delta_f1": d_f1, "delta_fp24": d_fa, "source": "ms/results/phase1/deltas.json (subset)"},
           "grids": {}}
    md = [f"# Phase 1 tolerance limits (subset, out-of-fold, frozen operating point)\n",
          f"Tolerated: F1 drop <= {d_f1:.4f} and FP/24h rise <= {d_fa:.3f} vs the clean run (D-MS10). "
          "Generated by `python ms/py/tolerance.py`.\n"]
    for g in grids:
        clean, rows = load(P1 / f"sweeps/{g}.jsonl")
        a = analyse(clean, rows, d_f1, d_fa)
        res["grids"][g] = {"clean": {k: clean[k] for k in ("f1", "sensitivity", "precision", "fp_per_24h")},
                           "families": a}
        md += [f"\n## {g}: clean F1 {clean['f1']:.4f}, FP/24h {clean['fp_per_24h']:.3f}\n",
               "| parameter | limit | first failing | at limit: dF1 / dFP24 / bit flips per window | status |",
               "|---|---|---|---|---|"]
        for k, f in a.items():
            lim = next((x for x in f["levels"] if x["level"] == f["limit"]), None)
            at = "-" if lim is None else (f"{lim['d_f1']:+.4f} / {lim['d_fp24']:+.3f} / "
                                          f"{fmt(round(lim.get('bit_flips_per_window', float('nan')), 3))}")
            unit = f["limit_unit"] or ""
            st = f["status"] + (f" (non-monotonic: {', '.join(f['non_monotonic'])})" if f["non_monotonic"] else "")
            md.append(f"| {f['label']} | {fmt(f['limit'])} {unit} | {fmt(f['first_failing'])} | {at} | {st} |")
    (P1 / "tolerance.json").write_text(json.dumps(res, indent=1) + "\n")
    (P1 / "tolerance_table.md").write_text("\n".join(md) + "\n")
    print("\n".join(md))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
