#!/usr/bin/env python3
"""Combined spec point (MS_SPEC.md 1.2 step 7b): every impairment of every modality at its tolerance limit at once.

Built from ms/results/phase1/tolerance.json:
  * a family with a limit, or "beyond grid", enters at its limit (for "beyond grid" the worst level tested);
  * a family where no level passed enters clean, and is listed under "excluded" (its spec is tighter than the
    mildest level tested, so the combined point cannot include it);
  * gain error has one sign at a time: two combined jobs, +limit and -limit (each sign at its own limit);
  * the white-noise level is the white limit; the 1/f corner (measured at 1 uV rms white) is applied on top of it;
  * mains 50 Hz and 250 Hz enter together as harmonics 1 and 5 of one mains source; their amplitudes are the
    amplitudes at the ADC input (no further anti-alias attenuation), exactly as in the single-parameter sweeps;
  * offset and drift enter together; high-pass and low-pass together; LSB and clip level together.
Random impairments use seeds 0..4.

Usage: python ms/py/combined.py -> ms/results/phase1/combined_jobs.json, then
       python ms/py/sweep.py --models <seed-0 fold models> --grid combined, then
       python ms/py/combined.py --evaluate -> ms/results/phase1/combined_verdict.json
"""
from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
P1 = REPO / "ms/results/phase1"
DENS_BAND = 99.5          # Hz, as grids.dens
MOV_BAND = 12.5


def level(f: dict):
    if f["status"] == "none tolerated":
        return None
    return f["limit"]


def impair_for(mod: str, fams: dict, gain_sign: int) -> tuple[dict, list[str]]:
    kw, excluded = {}, []
    get = lambda k: fams.get(f"{mod}/{k}")

    def lv(k):
        f = get(k)
        if f is None:
            return None
        v = level(f)
        if v is None:
            excluded.append(f"{mod}/{k}")
        return v
    bio = mod != "mov"
    if (q := lv("lsb")) is not None:
        kw["lsb"] = float(q)
    if bio and (c := lv("clip")) is not None:
        kw["clip"] = float(c)
    if (w := lv("white")) is not None:
        kw["white_density"] = w / (DENS_BAND if bio else MOV_BAND) ** 0.5
    if bio and (fc := lv("pink")) is not None and "white_density" in kw:
        kw["pink_corner_hz"] = float(fc)
    g = lv("gain+" if gain_sign > 0 else "gain-")
    if g is not None:
        kw["gain_err"] = gain_sign * float(g)
    if bio:
        if (o := lv("offset")) is not None:
            kw["offset"] = float(o) * 8192.0
        if (d := lv("drift")) is not None:
            kw["drift_rms"], kw["drift_tau_s"] = float(d), 64.0
        m50, m250 = lv("mains50"), lv("mains250")
        if m50 is not None or m250 is not None:
            kw["mains_peak"] = (float(m50 or 0.0), 0.0, 0.0, 0.0, float(m250 or 0.0))
        if (h := lv("hp")) is not None:
            kw["hp_hz"] = float(h)
        if (l := lv("lp")) is not None:
            kw["lp_hz"] = float(l)
    return kw, excluded


def evaluate() -> int:
    """D-MS10 verdict of each combined job (seed mean) against the clean run of the same file."""
    import numpy as np
    rows = [json.loads(l) for l in (P1 / "sweeps/combined.jsonl").read_text().splitlines() if l.strip()]
    clean = next(r for r in rows if r["name"] == "clean")
    d = json.loads((P1 / "deltas.json").read_text())["subset"]
    res = {"clean": {k: clean[k] for k in ("f1", "fp_per_24h", "sensitivity")}, "deltas": d, "jobs": {}}
    for name in sorted({r["name"] for r in rows} - {"clean"}):
        rs = [r for r in rows if r["name"] == name]
        f1 = float(np.mean([r["f1"] for r in rs])); fa = float(np.mean([r["fp_per_24h"] for r in rs]))
        ok = (clean["f1"] - f1 <= d["delta_f1"]) and (fa - clean["fp_per_24h"] <= d["delta_fp24"])
        res["jobs"][name] = {"seeds": len(rs), "f1": f1, "fp_per_24h": fa, "d_f1": f1 - clean["f1"],
                             "d_fp24": fa - clean["fp_per_24h"], "tolerated": bool(ok)}
        print(f"{name}: F1 {f1:.4f} ({f1 - clean['f1']:+.4f}), FP/24h {fa:.3f} ({fa - clean['fp_per_24h']:+.3f}) "
              f"-> {'tolerated' if ok else 'NOT tolerated'}")
    (P1 / "combined_verdict.json").write_text(json.dumps(res, indent=1) + "\n")
    return 0


def main() -> int:
    import sys
    if "--evaluate" in sys.argv:
        return evaluate()
    tol = json.loads((P1 / "tolerance.json").read_text())
    jobs, excluded = [], set()
    for sign, tag in ((+1, "gain+"), (-1, "gain-")):
        imp = {}
        for mod, g in tol["grids"].items():
            kw, ex = impair_for(mod, g["families"], sign)
            excluded.update(ex)
            if kw:
                imp[mod] = kw
        jobs += [{"name": f"combined_{tag}", "seed": s, "impair": imp} for s in range(5)]
    out = {"what": "combined spec point, MS_SPEC.md step 7b", "excluded_none_tolerated": sorted(excluded),
           "jobs": jobs}
    (P1 / "combined_jobs.json").write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps({"excluded": sorted(excluded), "impair_gain+": jobs[0]["impair"]}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
