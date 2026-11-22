#!/usr/bin/env python3
"""Full-data confirmation of the tolerance limits (MS_SPEC.md D-MS5 (2), D-MS10; step 7).

Every training recording (2,072 runs, 8,714 h, sub-001..sub-096 only) is streamed from S3 once. Its integer
front-end inputs are captured, and the clean job plus every confirmation job run on them through exactly the code
path of the subset sweeps (subset_fe.run_segment_full: impairment -> unchanged golden front end), then through the
fold model that never saw the patient, at the frozen operating point (10 of 10, score >= 9, no gate). Scoring is
that of the pipeline (seizelut.eval: kth_of_last, run_events_at, prepare_ref/score_events, subject_metrics), on
whole recordings as in the CV runs, with seizure intervals and durations from cache/features/int/<run>.npz.

Checks: the clean job's features must equal cache/features/int/<run>.npz for every recording, and the clean
job's metrics must equal ms/results/phase1/cv_frozen_op.json (seed-0 models), else the run is invalid.

Jobs (--jobs): "limits" = from ms/results/phase1/tolerance.json, per parameter the limit level and the first
failing level (only the limit if every level passed; only the mildest level if none passed), with impairment
seeds --seeds. "stepdown" = the next milder level of every limit that failed on the full data (rule LOG L20, via
ms/py/full_spec.py); "combined" = the step 7b spec point from combined_jobs.json. Summaries of these two go to
confirm_<jobs>_<hash of the job names>.json, so later rounds never overwrite earlier ones.
Noise streams are keyed (seed, 100000 + recording index, channel index): independent of the subset.

Usage: python ms/py/confirm_full.py --models <fold checkpoint dir> [--workers 4] [--seeds 0] [--limit-runs N]
Per-recording counts: cache/ms/confirm/<tag>.jsonl (resumable). Summary: ms/results/phase1/confirm_<tag>.json
"""
from __future__ import annotations

import argparse
import contextlib
import json
import pickle
import sys
import time
from collections import defaultdict
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "ms/py"))
from seizelut.data.bids import discover_runs     # noqa: E402
from seizelut.data.edf import read_edf          # noqa: E402
from seizelut.data.remote import local_edf      # noqa: E402
from seizelut.data.split import load_folds      # noqa: E402
from seizelut.eval.fastscore import prepare_ref, score_events  # noqa: E402
from seizelut.eval.operating import kth_of_last, run_events_at, subject_metrics  # noqa: E402
from seizelut.features import golden            # noqa: E402

import grids                                    # noqa: E402
import subset_fe as FE                          # noqa: E402
from sweep import K, TH, compile_job            # noqa: E402

# Peak memory of one process() call grows with the recording: 1.79 GB at 5.5 h and 5.96 GB at 24.2 h (measured
# 17 Nov, LOG L22). Recordings are scheduled longest first and only while the estimated peaks fit --mem-gb (the bash
# cgroup of the cloud session is limited to 14.3 GB; four 24-h recordings at once were killed by the OOM killer).
MEM_BASE_GB, MEM_PER_H_GB = 0.6, 0.24
RAW = REPO / "data/raw/ds005873"
TMP = REPO / "cache/ms/tmp"
FEAT = REPO / "cache/features/int"
KEY_OFFSET = 100_000

_models: dict = {}
_folds: dict = {}


def _init(models_dir: str):
    global _models, _folds
    _folds = load_folds(REPO / "configs/folds_inner5.json")
    for p in sorted(Path(models_dir).glob("fold_*.pkl")):
        with open(p, "rb") as fh:
            _models[int(p.stem.split("_")[1])] = pickle.load(fh)
    assert sorted(_models) == [0, 1, 2, 3, 4], f"need fold_0..4.pkl in {models_dir}"


def jobs_by_name(names: list[str], seeds: list[int]) -> list[dict]:
    every = {}
    for g in ("eeg", "ecg", "emg"):
        for j in grids.bio(g, seeds):
            every[(j["name"], j["seed"])] = j
    for j in grids.mov(seeds):
        every[(j["name"], j["seed"])] = j
    jobs = []
    for n in names:
        js = [every[(n, s)] for s in seeds if (n, s) in every]
        if not js:      # deterministic impairments are defined for the first seed only
            js = [j for (nn, _), j in every.items() if nn == n][:1]
        jobs += js
    return jobs


def stepdown_jobs(seeds: list[int]) -> list[dict]:
    """Next milder levels needed by the step-down rule (LOG L20), from tolerance.json and the confirmations so far."""
    import full_spec
    tol = json.loads((REPO / "ms/results/phase1/tolerance.json").read_text())
    return jobs_by_name(full_spec.pending_names(full_spec.build(tol, full_spec.load_full_results())), seeds)


def limit_jobs(seeds: list[int]) -> list[dict]:
    tol = json.loads((REPO / "ms/results/phase1/tolerance.json").read_text())
    names = []
    for grid in tol["grids"].values():
        for f in grid["families"].values():
            lv = f["levels"]
            if f["status"] == "none tolerated":
                names.append(lv[0]["name"])
            else:
                names.append(next(x["name"] for x in lv if x["level"] == f["limit"]))
                if f["status"] == "limit":
                    names.append(next(x["name"] for x in lv if not x["tolerated"]))
    return jobs_by_name(names, seeds)


def run_hours(runs: list[str]) -> dict:
    """Recording length in hours from the feature cache (cached in cache/ms/confirm/run_hours.json)."""
    p = REPO / "cache/ms/confirm/run_hours.json"
    h = json.loads(p.read_text()) if p.exists() else {}
    for k in runs:
        if k not in h:
            with np.load(FEAT / f"{k}.npz") as d:
                h[k] = float(d["duration_s"]) / 3600
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(h))
    return h


def mem_est(hours: float) -> float:
    return MEM_BASE_GB + MEM_PER_H_GB * hours


def process(idx: int, run_key: str, jobs: list[dict]) -> dict:
    t0 = time.time()
    subj = run_key.split("_")[0]
    assert int(subj.split("-")[1]) <= 96, "training patients only"
    run = [r for r in discover_runs(RAW, [subj]) if r.key == run_key][0]
    inputs: dict = {}
    with contextlib.ExitStack() as st:
        sig = {m: read_edf(st.enter_context(local_edf(run, m, str(TMP)))) for m in run.modalities}
        n_sec = int(sig["eeg"].duration_s)
        golden.extract(sig, n_sec, "int", inputs=inputs)
    arrs = {"_keys": np.array([k.replace("/", "|", 1) for k in inputs])}
    for k, v in inputs.items():
        arrs[k.replace("/", "|", 1)] = v
    seg = {"id": KEY_OFFSET + idx, "start_s": 0, "end_s": n_sec}
    d = np.load(FEAT / f"{run_key}.npz")
    seizures, duration_s = [tuple(s) for s in d["seizures"]], float(d["duration_s"])
    ref = prepare_ref(seizures, duration_s)
    m = _models[_folds[subj]]
    out = {"run": run_key, "subject": subj, "hours": duration_s / 3600, "jobs": []}
    for j, job in enumerate(jobs):
        comp = compile_job(job)
        r = FE.run_segment_full(seg, arrs, comp, seed=job.get("seed", 0))
        X = r["X"].astype(np.int16)
        if j == 0:
            out["clean_equal_cache"] = bool(np.array_equal(X, d["X"]))
        sk = kth_of_last(m["model"].score(X[:, m["cols"]]), K)
        tp, fp, nref = score_events(ref, run_events_at(sk, TH))
        out["jobs"].append([int(tp), int(fp), int(nref), int(sum(r["clipped"].values()))])
    out["seconds"] = round(time.time() - t0, 1)
    return out


def summarise(rows: list[dict], jobs: list[dict]) -> dict:
    from scipy.stats import wilcoxon
    per_job = []
    for j, job in enumerate(jobs):
        counts = defaultdict(lambda: [0, 0, 0, 0.0])
        for r in rows:
            c = counts[r["subject"]]
            tp, fp, nref, _ = r["jobs"][j]
            c[0] += tp; c[1] += fp; c[2] += nref; c[3] += r["hours"]
        f1 = {}
        for s, (tp, fp, nref, h) in counts.items():
            if nref:
                se, pr = tp / nref, (tp / (tp + fp) if tp + fp else 0.0)
                f1[s] = 2 * se * pr / (se + pr) if se + pr else 0.0
        per_job.append({**job, **subject_metrics(dict(counts)), "per_subject": dict(counts), "per_subject_f1": f1,
                        "clipped_samples": int(sum(r["jobs"][j][3] for r in rows))})
    clean = per_job[0]
    for pj in per_job[1:]:
        subs = sorted(clean["per_subject_f1"])
        diff = np.array([pj["per_subject_f1"][s] - clean["per_subject_f1"][s] for s in subs])
        if np.all(diff == 0):
            pj["wilcoxon_p"] = 1.0
        else:
            pj["wilcoxon_p"] = float(wilcoxon(diff).pvalue)
        pj["d_f1"] = pj["f1"] - clean["f1"]
        pj["d_fp24"] = pj["fp_per_24h"] - clean["fp_per_24h"]
    return {"clean": clean, "jobs": per_job[1:]}


def verdicts(jobs: list[dict], d_full: dict, subset_levels: dict) -> None:
    """D-MS10 on the full training set: tolerated <=> F1 drop <= delta_F1, FP/24h rise <= delta_FA (full deltas) and
    Wilcoxon p >= 0.05. "marginal" (MS_SPEC step 7, LOG L18; a report, not a test): a random-family job whose margin
    to either threshold is smaller than that level's impairment-seed sd on the subset."""
    df1, dfa = d_full["delta_f1"], d_full["delta_fp24"]
    for j in jobs:
        j["tolerated"] = bool(-j["d_f1"] <= df1 and j["d_fp24"] <= dfa and j["wilcoxon_p"] >= 0.05)
        lv = subset_levels.get(j["name"])
        sd1, sda = (lv.get("f1_sd"), lv.get("fp24_sd")) if lv else (None, None)
        j["subset_seed_sd"] = {"f1": sd1, "fp24": sda}
        j["marginal"] = bool(sd1 is not None and sda is not None and
                             (abs(-j["d_f1"] - df1) < sd1 or abs(j["d_fp24"] - dfa) < sda))


def subset_level_table() -> dict:
    p = REPO / "ms/results/phase1/tolerance.json"
    if not p.exists():
        return {}
    tol = json.loads(p.read_text())
    return {x["name"]: x for g in tol["grids"].values() for f in g["families"].values() for x in f["levels"]}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--models", required=True)
    ap.add_argument("--jobs", default="limits",
                    help="'limits' (from tolerance.json), 'stepdown' (next milder levels of limits that failed, LOG L20), "
                         "'combined' (combined_jobs.json, step 7b) or 'clean'")
    ap.add_argument("--seeds", type=int, nargs="*", default=[0])
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--limit-runs", type=int, default=None, help="first N recordings only (quick checks)")
    ap.add_argument("--tag", default=None)
    ap.add_argument("--mem-gb", type=float, default=11.0, help="budget for the summed peak-memory estimates")
    ap.add_argument("--reserve-gb", type=float, default=1.8,
                    help="memory kept back for each other free worker when picking a recording, so a long recording "
                         "runs next to short ones instead of next to another long one with two cores idle (LOG L22)")
    args = ap.parse_args()
    extra = {"limits": lambda: limit_jobs(args.seeds), "clean": list,
             "stepdown": lambda: stepdown_jobs(args.seeds),
             "combined": lambda: [j for j in grids.get("combined", []) if j["seed"] in args.seeds]}[args.jobs]()
    if args.jobs in ("stepdown", "combined") and not extra:
        print(f"no {args.jobs} jobs to run"); return 0
    jobs = [{"name": "clean", "seed": 0}] + extra
    name = args.jobs
    if args.jobs in ("stepdown", "combined"):   # one summary file per distinct job set (resumable, never overwritten)
        import hashlib
        name += "_" + hashlib.sha1(json.dumps(sorted(j["name"] for j in extra)).encode()).hexdigest()[:8]
    tag = args.tag or name + (f"_runs{args.limit_runs}" if args.limit_runs else "")
    subjects = sorted(load_folds(REPO / "configs/folds_inner5.json"))
    runs = sorted(r.key for r in discover_runs(RAW, subjects))
    assert len(subjects) == 96 and all(int(s.split("-")[1]) <= 96 for s in subjects)
    if args.limit_runs:
        runs = runs[: args.limit_runs]
    log = REPO / f"cache/ms/confirm/{tag}.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    TMP.mkdir(parents=True, exist_ok=True)
    sig = [json.dumps(j, sort_keys=True) for j in jobs]
    done = {}
    if log.exists():
        for l in log.read_text().splitlines():
            r = json.loads(l)
            if r.get("job_sigs") == sig:
                done[r["run"]] = r
    todo = [(i, k) for i, k in enumerate(runs) if k not in done]
    print(f"{len(jobs)} jobs (incl. clean), {len(runs)} recordings, {len(todo)} to do, {args.workers} workers, "
          f"memory budget {args.mem_gb:g} GB, reserve {args.reserve_gb:g} GB per other free worker", flush=True)
    hours = run_hours([k for _, k in todo])
    pending = sorted(todo, key=lambda t: (-hours[t[1]], t[1]))       # longest first
    running, used, n = {}, 0.0, 0
    with ProcessPoolExecutor(args.workers, initializer=_init, initargs=(args.models,)) as pool, \
            open(log, "a") as fh:
        while pending or running:
            while pending and len(running) < args.workers:
                free = args.workers - len(running) - 1          # other free workers after this pick
                pick = next((t for t in pending
                             if used + mem_est(hours[t[1]]) + free * args.reserve_gb <= args.mem_gb), None)
                if pick is None:
                    pick = next((t for t in pending if used + mem_est(hours[t[1]]) <= args.mem_gb), None)
                if pick is None:
                    if running:
                        break
                    pick = pending[0]                 # nothing running: the longest one runs alone
                pending.remove(pick)
                running[pool.submit(process, pick[0], pick[1], jobs)] = pick
                used += mem_est(hours[pick[1]])
            fin, _ = wait(running, return_when=FIRST_COMPLETED)
            for f in fin:
                _, k = running.pop(f)
                used -= mem_est(hours[k])
                r = f.result()
                r["job_sigs"] = sig
                fh.write(json.dumps(r) + "\n"); fh.flush()
                done[r["run"]] = r
                n += 1
                if n % 20 == 0 or n == len(todo):
                    print(f"  {n}/{len(todo)} {r['run']} {r['hours']:.1f} h {r['seconds']} s clean_equal_cache "
                          f"{r['clean_equal_cache']}", flush=True)
    rows = [done[k] for k in runs]
    bad = [r["run"] for r in rows if not r["clean_equal_cache"]]
    summ = summarise(rows, jobs)
    summ["deltas_full"] = json.loads((REPO / "ms/results/phase1/deltas.json").read_text())["full"]
    verdicts(summ["jobs"], summ["deltas_full"], subset_level_table())
    summ["recordings"] = len(rows)
    summ["clean_feature_mismatches"] = bad
    c = summ["clean"]
    if not args.limit_runs:        # the clean job must reproduce the seed-0 CV result exactly (same models, data)
        cv = json.loads((REPO / "ms/results/phase1/cv_frozen_op.json").read_text())
        ref = [v for k, v in cv.items() if k != "summary" and v["seed"] == 0 and Path(args.models).name in k]
        def same(a, b):     # event counts exactly; hours up to float summation order
            return a.keys() == b.keys() and all(a[s][:3] == b[s][:3] and abs(a[s][3] - b[s][3]) < 1e-9 for s in a)
        summ["clean_vs_cv"] = ({"run": Path(args.models).name, "equal": bool(same(ref[0]["per_subject"],
                                                                                   c["per_subject"]))}
                               if ref else "no matching seed-0 run in cv_frozen_op.json")
        bad = bad + ([] if isinstance(summ["clean_vs_cv"], dict) and summ["clean_vs_cv"]["equal"] else ["clean_vs_cv"])
    p = REPO / f"ms/results/phase1/confirm_{tag}.json"
    p.write_text(json.dumps(summ, indent=1) + "\n")
    print(f"clean: F1 {c['f1']:.4f} sens {c['sensitivity']:.4f} FP/24h {c['fp_per_24h']:.3f}; "
          f"problems: {bad or 'none'}; clean vs CV: {summ.get('clean_vs_cv')}")
    for j in summ["jobs"]:
        print(f"  {j['name']:<30s} seed {j['seed']}: F1 {j['f1']:.4f} ({j['d_f1']:+.4f}) FP/24h {j['fp_per_24h']:.3f} "
              f"({j['d_fp24']:+.3f}) Wilcoxon p {j['wilcoxon_p']:.3g} -> "
              f"{'tolerated' if j['tolerated'] else 'NOT tolerated'}{' (marginal)' if j['marginal'] else ''}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
