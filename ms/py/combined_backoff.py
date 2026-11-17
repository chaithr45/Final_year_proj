#!/usr/bin/env python3
"""Back-off of the combined spec point (MS_SPEC.md 1.2 step 7b; the rule's details pinned in LOG L21).

Step 7b: "If [the combined point] fails, the limits that move the features most (mechanism table, step 6) are backed
off one grid step at a time, most-moving first, until the combined point passes." Pinned as:

  * start: the combined point of ms/py/combined.py (spec_limits.json, else tolerance.json as a preview);
  * "moves the features most" = comparator bits of the frozen model that flip per window (the mechanism column of
    tolerance.json) in the single-impairment subset run of the family AT ITS CURRENT LEVEL, so a family that has been
    backed off is ranked again by the flips of its new level;
  * candidates: families in the point that are still on; the gain family of a sign only while that sign's job
    fails; ties broken by modality (eeg, ecg, emg, mov) and then family name;
  * one step: the top candidate moves one grid level milder (from the mildest level tested: off). The 1/f corner
    needs white noise, so it goes off with it;
  * after every step both jobs (gain +limit and -limit) run again and the D-MS10 test is applied to each; the point
    passes when both are tolerated. On the subset: 5 impairment seeds, subset deltas (as the preview). With
    --data full: seed 0 and the full deltas plus Wilcoxon (confirm_full.py --jobs combined), starting from the point
    that passed on the subset and continuing the same rule if it fails there.

Job names: step 0 keeps combined.py's names (combined[_preview]_gain+/-); step k >= 1 is combined[_preview]_b<k>_gain+/-.
Every step's point, verdicts and back-off go to ms/results/phase1/combined_backoff[_full].json; combined_jobs.json
holds the last step run. Resumable: finished jobs are skipped by sweep.py and confirm_full.py.

Usage: python ms/py/combined_backoff.py --models <seed-0 fold models> [--data subset|full] [--workers 4]
       python ms/py/combined_backoff.py --dry-run     # print the ranking of step 0 and exit
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
P1 = REPO / "ms/results/phase1"
sys.path.insert(0, str(REPO / "ms/py"))
import combined as CB                                 # noqa: E402

MOD_ORDER = ("eeg", "ecg", "emg", "mov")
SIGNS = ((+1, "gain+"), (-1, "gain-"))


def source() -> tuple[dict, bool]:
    p = P1 / "spec_limits.json"
    if p.exists():
        return json.loads(p.read_text()), False
    return json.loads((P1 / "tolerance.json").read_text()), True


def start_state(src: dict) -> dict:
    """family key -> index into its levels (mildest first); families with no tolerated level are left out."""
    st = {}
    for g in src["grids"].values():
        for k, f in g["families"].items():
            if f["status"] in ("limit", "beyond grid"):
                st[k] = next(i for i, x in enumerate(f["levels"]) if x["level"] == f["limit"])
    return st


def families_at(src: dict, st: dict) -> dict:
    """Copy of the source grids with each family's limit set to its current level (or status off)."""
    out = copy.deepcopy(src["grids"])
    for g in out.values():
        for k, f in g["families"].items():
            if k not in st:
                continue
            if st[k] < 0:
                f["status"], f["limit"] = "off", None
            else:
                f["status"], f["limit"] = "limit", f["levels"][st[k]]["level"]
    return out


def jobs_for(src: dict, st: dict, step: int, preview: bool, seeds) -> list[dict]:
    grids = families_at(src, st)
    pre = "preview_" if preview else ""
    jobs = []
    for sign, gtag in SIGNS:
        imp = {}
        for mod, g in grids.items():
            kw, _ = CB.impair_for(mod, g["families"], sign)
            if kw:
                imp[mod] = kw
        name = f"combined_{pre}{gtag}" if step == 0 else f"combined_{pre}b{step}_{gtag}"
        jobs += [{"name": name, "seed": s, "impair": json.loads(json.dumps(imp))} for s in seeds]
    return jobs


def ranking(src: dict, st: dict, failing: set[str]) -> list[tuple[float, str, str]]:
    """Candidates, most bit flips first: (flips, family key, level name)."""
    fams = {k: f for g in src["grids"].values() for k, f in g["families"].items()}
    out = []
    for k, i in st.items():
        if i < 0:
            continue
        fam = k.split("/", 1)[1]
        if fam in ("gain+", "gain-") and fam not in failing:
            continue
        lv = fams[k]["levels"][i]
        out.append((float(lv["bit_flips_per_window"]), k, lv["name"]))
    order = lambda t: (-t[0], MOD_ORDER.index(t[1].split("/")[0]), t[1])
    return sorted(out, key=order)


def back_off(st: dict, key: str) -> dict:
    st = dict(st)
    st[key] -= 1
    mod = key.split("/")[0]
    if key.endswith("/white") and st[key] < 0 and f"{mod}/pink" in st:
        st[f"{mod}/pink"] = -1                       # the 1/f corner is defined on top of the white noise
    return st


def verdict_subset(names: list[str]) -> dict:
    rows = [json.loads(l) for l in (P1 / "sweeps/combined.jsonl").read_text().splitlines() if l.strip()]
    clean = next(r for r in rows if r["name"] == "clean")
    d = json.loads((P1 / "deltas.json").read_text())["subset"]
    out = {}
    for n in names:
        rs = [r for r in rows if r["name"] == n]
        f1 = float(np.mean([r["f1"] for r in rs])); fa = float(np.mean([r["fp_per_24h"] for r in rs]))
        out[n] = {"seeds": len(rs), "f1": f1, "fp_per_24h": fa, "d_f1": f1 - clean["f1"],
                  "d_fp24": fa - clean["fp_per_24h"],
                  "tolerated": bool(clean["f1"] - f1 <= d["delta_f1"] and fa - clean["fp_per_24h"] <= d["delta_fp24"])}
    return out


def verdict_full(names: list[str]) -> dict:
    tag = "combined_" + hashlib.sha1(json.dumps(sorted(names)).encode()).hexdigest()[:8]
    js = {j["name"]: j for j in json.loads((P1 / f"confirm_{tag}.json").read_text())["jobs"] if j["seed"] == 0}
    return {n: {k: js[n][k] for k in ("f1", "fp_per_24h", "d_f1", "d_fp24", "wilcoxon_p", "tolerated", "marginal")}
            | {"file": f"confirm_{tag}.json"} for n in names}


def run(cmd: list[str]) -> None:
    print("$", " ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=REPO, check=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--models")
    ap.add_argument("--data", choices=("subset", "full"), default="subset")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--max-steps", type=int, default=60)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    src, preview = source()
    st = start_state(src)
    if args.dry_run:
        for f, k, n in ranking(src, st, {"gain+", "gain-"}):
            print(f"{f:8.3f}  {k:16s} {n}")
        return 0
    if args.data == "full" and preview:
        raise SystemExit("--data full needs spec_limits.json (the confirmed limits), not the preview")
    py = sys.executable
    full = args.data == "full"
    seeds = [0] if full else [0, 1, 2, 3, 4]
    steps, start = [], 0
    if full:                                    # continue from the point that passed on the subset
        sub = json.loads((P1 / "combined_backoff.json").read_text())
        if sub.get("status") != "passed" or sub.get("preview"):
            raise SystemExit("the subset back-off (non-preview) has not passed yet")
        st, start = {k: int(v) for k, v in sub["final_state"].items()}, sub["final_step"]
    out_p = P1 / ("combined_backoff_full.json" if full else "combined_backoff.json")
    status = "nothing left to back off"
    for step in range(start, start + args.max_steps):
        jobs = jobs_for(src, st, step, preview, seeds)
        names = sorted({j["name"] for j in jobs})
        (P1 / "combined_jobs.json").write_text(json.dumps(
            {"what": f"combined spec point, MS_SPEC.md step 7b, back-off step {step} (LOG L21)"
                     + (" (preview from the subset limits)" if preview else ""),
             "source": "tolerance.json" if preview else "spec_limits.json", "step": step, "jobs": jobs}, indent=1) + "\n")
        if full:
            run([py, "ms/py/confirm_full.py", "--models", args.models, "--jobs", "combined", "--seeds", "0",
                 "--workers", str(args.workers)])
            v = verdict_full(names)
        else:
            run([py, "ms/py/sweep.py", "--models", args.models, "--grid", "combined", "--seeds", "0", "1", "2", "3",
                 "4", "--workers", str(args.workers), "--batch", "12"])
            v = verdict_subset(names)
        failing = {n.rsplit("_", 1)[1] for n, x in v.items() if not x["tolerated"]}
        lv = {k: (src_level(src, k, i)) for k, i in st.items()}
        rec = {"step": step, "levels": lv, "verdicts": v}
        for n, x in v.items():
            print(f"step {step} {n}: F1 {x['f1']:.4f} ({x['d_f1']:+.4f}) FP/24h {x['fp_per_24h']:.3f} "
                  f"({x['d_fp24']:+.3f}) -> {'tolerated' if x['tolerated'] else 'NOT tolerated'}", flush=True)
        if not failing:
            steps.append(rec)
            status = "passed"
            break
        rk = ranking(src, st, failing)
        if not rk:
            steps.append(rec)
            break
        flips, key, lname = rk[0]
        new = back_off(st, key)
        rec["back_off"] = {"family": key, "from": lname, "flips_per_window": flips,
                           "to": src_level(src, key, new[key]), "ranking_top5": rk[:5]}
        print(f"step {step}: back off {key} from {lname} ({flips:.2f} flips/window) to {rec['back_off']['to']}",
              flush=True)
        steps.append(rec)
        st = new
        out_p.write_text(json.dumps({"rule": "MS_SPEC step 7b, LOG L21", "data": args.data, "preview": preview,
                                     "status": "running", "steps": steps}, indent=1) + "\n")
    else:
        status = f"stopped after --max-steps {args.max_steps}"
    out_p.write_text(json.dumps({"rule": "MS_SPEC step 7b, LOG L21", "data": args.data, "preview": preview,
                                 "status": status, "final_step": steps[-1]["step"], "final_state": st,
                                 "steps": steps}, indent=1) + "\n")
    print(f"back-off {args.data}: {status} at step {steps[-1]['step']}")
    return 0 if status == "passed" else 2


def src_level(src: dict, key: str, i: int):
    if i < 0:
        return "off"
    mod = key.split("/")[0]
    return src["grids"][mod]["families"][key]["levels"][i]["name"]


if __name__ == "__main__":
    raise SystemExit(main())
