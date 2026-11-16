#!/usr/bin/env python3
"""Phase 1 impairment sweeps (MS_SPEC.md 1.2 step 5): subset segments -> impairment -> unchanged golden front end
-> the fold model that never saw the patient (out-of-fold) -> frozen operating point -> SzCORE event counts.

Operating point = the frozen detector's (export/n4_distill_s0/head.json): no artefact gate, alarm when 10 of the
last 10 decisions have score >= 9. The 10-s alarm history includes the warm-up windows, as in the full pipeline;
only scored windows produce events.

Also measured per job, for the mechanism table: how often each of the frozen model's 146 comparator bits differs
from the clean run, and how far each of its 38 features moves (in feature LSBs), on the scored windows.

Usage:
  python ms/py/sweep.py --models <fold checkpoint dir> --grid <name> [--seeds 0 1 2 3 4] [--workers 4]
  python ms/py/sweep.py --models ... --grid clean --limit 20      # quick check on 20 segments
Output: ms/results/phase1/sweeps/<grid>.jsonl, one line per job (appended; finished jobs are skipped on restart).
"""
from __future__ import annotations

import argparse
import json
import pickle
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "ms/py"))
from seizelut.data.split import load_folds            # noqa: E402
from seizelut.eval.fastscore import prepare_ref, score_events  # noqa: E402
from seizelut.eval.operating import kth_of_last, run_events_at, subject_metrics  # noqa: E402

import impair as IMP                                   # noqa: E402
import subset_fe as FE                                 # noqa: E402

SUBSET = REPO / "ms/results/phase1/subset.json"
HEAD = json.loads((REPO / "export/n4_distill_s0/head.json").read_text())
THR = json.loads((REPO / "export/n4_distill_s0/thresholds.json").read_text())["features"]
TH, K = float(HEAD["decision_threshold"]), int(HEAD["k"])
assert HEAD["artefact_gate"] == "none" and HEAD["n"] == 10
BASE = {"eeg": 0.25, "ecg": 0.25, "emg": 0.25, "mov": 1.0}   # base units per input LSB (uV; motion in LSB)

_models: dict = {}
_folds: dict = {}


def _init(models_dir: str):
    global _models, _folds
    _folds = load_folds(REPO / "configs/folds_inner5.json")
    for p in sorted(Path(models_dir).glob("fold_*.pkl")):
        with open(p, "rb") as fh:
            _models[int(p.stem.split("_")[1])] = pickle.load(fh)
    assert sorted(_models) == [0, 1, 2, 3, 4], f"need fold_0..4.pkl in {models_dir}"


def frozen_bits(X: np.ndarray) -> np.ndarray:
    """The frozen model's 146 comparator bits (feature > threshold) of every window."""
    cols = [X[:, f["spec_index"]][:, None] > np.array(f["thresholds"])[None, :] for f in THR]
    return np.concatenate(cols, axis=1)


def compile_job(job: dict) -> dict:
    out = {}
    for mod, kw in job.get("impair", {}).items():
        out[mod] = IMP.compile_impairment(IMP.Impairment(**kw), FE.FS[mod], BASE[mod])
    return out


def eval_chunk(seg_list: list[dict], jobs: list[dict]) -> list[dict]:
    compiled = [compile_job(j) for j in jobs]
    res = []
    for seg in seg_list:
        arrs = FE.load_segment(seg["id"])
        m = _models[_folds[seg["subject"]]]
        model, cols = m["model"], m["cols"]
        k0 = seg["score_start_s"] - seg["start_s"]
        rel_sz = [(a - seg["score_start_s"], b - seg["score_start_s"]) for a, b in seg["seizures"]]
        dur = seg["end_s"] - seg["score_start_s"]
        ref = prepare_ref(rel_sz, dur)
        clean = None
        for j, (job, comp) in enumerate(zip(jobs, compiled)):
            r = FE.run_segment_full(seg, arrs, comp, seed=job.get("seed", 0))
            X = r["X"].astype(np.int16)
            s = model.score(X[:, cols])
            sk = kth_of_last(s, K)[k0:]
            tp, fp, nref = score_events(ref, run_events_at(sk, TH))
            out = {"job": j, "segment": seg["id"], "subject": seg["subject"], "tp": tp, "fp": fp, "nref": nref,
                   "hours": dur / 3600, "clipped": int(sum(r["clipped"].values()))}
            Xs = X[k0:]
            if job.get("name") == "clean" or not comp:
                clean = Xs
            if clean is not None:
                b0, b1 = frozen_bits(clean), frozen_bits(Xs)
                out["bit_flips"] = (b0 != b1).sum(0).astype(int).tolist()
                idx = [f["spec_index"] for f in THR]
                d = np.abs(Xs[:, idx].astype(np.int64) - clean[:, idx])
                out["feat_absdiff_sum"] = d.sum(0).astype(int).tolist()
                out["feat_changed"] = (d > 0).sum(0).astype(int).tolist()
                out["windows"] = int(len(Xs))
            res.append(out)
    return res


def aggregate(job: dict, rows: list[dict]) -> dict:
    counts: dict = {}
    for r in rows:
        c = counts.setdefault(r["subject"], [0, 0, 0, 0.0])
        c[0] += r["tp"]; c[1] += r["fp"]; c[2] += r["nref"]; c[3] += r["hours"]
    m = subject_metrics(counts)
    per_f1 = {}
    for s, (tp, fp, nref, h) in counts.items():
        if nref:
            se, pr = tp / nref, (tp / (tp + fp) if tp + fp else 0.0)
            per_f1[s] = 2 * se * pr / (se + pr) if se + pr else 0.0
    out = {**job, **m, "per_subject": counts, "per_subject_f1": per_f1,
           "clipped_samples": int(sum(r["clipped"] for r in rows))}
    if all("bit_flips" in r for r in rows):
        out["windows"] = int(sum(r["windows"] for r in rows))
        out["bit_flip_rate"] = (np.sum([r["bit_flips"] for r in rows], 0) / out["windows"]).tolist()
        out["feat_mean_absdiff"] = (np.sum([r["feat_absdiff_sum"] for r in rows], 0) / out["windows"]).tolist()
        out["feat_changed_rate"] = (np.sum([r["feat_changed"] for r in rows], 0) / out["windows"]).tolist()
    return out


def main() -> int:
    import grids
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--models", required=True, help="directory with fold_0.pkl .. fold_4.pkl")
    ap.add_argument("--grid", required=True)
    ap.add_argument("--seeds", type=int, nargs="*", default=[0])
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--limit", type=int, default=None, help="first N segments only (quick checks)")
    ap.add_argument("--batch", type=int, default=6, help="jobs evaluated per pass over the segments")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    segs = json.loads(SUBSET.read_text())["segments"]
    if args.limit:
        segs = segs[: args.limit]
    jobs = [{"name": "clean", "seed": 0}] + grids.get(args.grid, args.seeds)
    out = Path(args.out or REPO / f"ms/results/phase1/sweeps/{args.grid}{'_limit' + str(args.limit) if args.limit else ''}.jsonl")
    out.parent.mkdir(parents=True, exist_ok=True)
    done = set()
    if out.exists():
        done = {json.dumps({k: v for k, v in json.loads(l).items() if k in ("name", "seed", "impair")}, sort_keys=True)
                for l in out.read_text().splitlines() if l.strip()}
    sig = lambda j: json.dumps({k: v for k, v in j.items() if k in ("name", "seed", "impair")}, sort_keys=True)
    todo = [j for j in jobs[1:] if sig(j) not in done]
    batches = [todo[i: i + args.batch] for i in range(0, len(todo), args.batch)]
    if not batches and sig(jobs[0]) not in done:
        batches = [[]]
    print(f"{len(todo)} impaired jobs to run ({len(jobs) - 1 - len(todo)} done), {len(segs)} segments, "
          f"{args.workers} workers", flush=True)
    chunks = [c for c in (segs[i::args.workers * 4] for i in range(args.workers * 4)) if c]
    with ProcessPoolExecutor(args.workers, initializer=_init, initargs=(args.models,)) as pool:
        for b in batches:
            batch = [jobs[0]] + b          # the clean job runs with every batch: the bit flips are measured against it
            t0 = time.time()
            rows = [r for part in pool.map(eval_chunk, chunks, [batch] * len(chunks)) for r in part]
            with open(out, "a") as fh:
                for j, job in enumerate(batch):
                    if sig(job) in done:
                        continue
                    agg = aggregate(job, [r for r in rows if r["job"] == j])
                    agg["batch_seconds"] = round(time.time() - t0, 1)
                    fh.write(json.dumps(agg) + "\n")
                    done.add(sig(job))
                    print(f"  {job['name']:<30s} seed {job.get('seed', 0)}: F1 {agg['f1']:.3f} sens "
                          f"{agg['sensitivity']:.3f} FP/24h {agg['fp_per_24h']:.2f} clipped {agg['clipped_samples']} "
                          f"({agg['batch_seconds']:.0f} s batch)", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
