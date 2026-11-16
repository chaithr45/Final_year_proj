#!/usr/bin/env python3
"""Phase 1 sweep subset (MS_SPEC.md D-MS5), fixed BEFORE any sweep. Training patients sub-001..sub-096 only.

* Seizure segments: every training seizure (merged intervals, as the pipeline reads them) from 20 min before onset
  to 10 min after offset, clipped to its recording; overlapping or touching segments of one recording are merged.
* Background segments: per patient about 4 h, drawn at random (seed 20261116): one-hour blocks inside recordings
  of >= 1 h, or whole recordings of >= 10 min for patients whose files are split into shorter recordings; every
  block at least 30 min from any seizure and not overlapping a seizure segment or another block.
* Warm-up: each segment is processed from 10 min before its scored part (or from the recording start, which is
  what the full pipeline does too); warm-up windows are not scored.

Output: ms/results/phase1/subset.json (segment list + summary). Reads only training metadata
(data/raw/ds005873, fetched by ms/py/fetch_train_metadata.py) and results/audit/runs.csv (durations).
Usage: python ms/py/make_subset.py
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from seizelut.data.bids import discover_runs           # noqa: E402
from seizelut.data.split import official_train_subjects  # noqa: E402

SEED = 20261116
PRE_S, POST_S, WARM_S = 20 * 60, 10 * 60, 10 * 60
BG_BLOCKS, BG_LEN_S, BG_GUARD_S = 4, 3600, 30 * 60
MIN_WHOLE_S = 10 * 60
OUT = REPO / "ms/results/phase1/subset.json"


def merge(iv):
    out = []
    for a, b in sorted(iv):
        if out and a <= out[-1][1]:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return out


def main() -> int:
    subjects = official_train_subjects()
    assert len(subjects) == 96 and subjects[-1] == "sub-096"
    dur = {(r["subject"], r["run"]): int(float(r["duration_eeg_s"]))
           for r in csv.DictReader(open(REPO / "results/audit/runs.csv")) if r["subject"] in set(subjects)}
    runs = discover_runs(REPO / "data/raw/ds005873", subjects)
    assert {r.subject for r in runs} <= set(subjects)
    rng = np.random.default_rng(SEED)
    segs, n_sz = [], 0
    for subj in subjects:
        sruns = [r for r in runs if r.subject == subj]
        busy = {}                                   # run -> intervals that background must avoid
        for r in sruns:
            d = dur[(subj, r.run)]
            sz = [(float(a), float(b)) for a, b in r.read_annotations().seizure_intervals()]
            n_sz += len(sz)
            busy[r.key] = [(a - BG_GUARD_S, b + BG_GUARD_S) for a, b in sz]
            for a, b in merge([[max(0, int(np.floor(a)) - PRE_S), min(d, int(np.ceil(b)) + POST_S)] for a, b in sz]):
                inside = [[x, y] for x, y in sz if x < b and y > a]
                segs.append({"subject": subj, "run": r.key, "kind": "seizure", "start_s": max(0, a - WARM_S),
                             "score_start_s": a, "end_s": b, "seizures": inside, "run_duration_s": d})
                busy[r.key].append((a, b))
        # background, 4 h per patient: a random 1-h block inside a recording of >= 1 h, or (recordings split into
        # files shorter than 1 h) a whole recording of >= 10 min. A whole recording starts cold at its first sample,
        # exactly as the full pipeline does, so it needs no extra warm-up.
        cand = []
        for r in sruns:
            d = dur[(subj, r.run)]
            if d >= BG_LEN_S or d >= MIN_WHOLE_S:
                cand.append((r.key, d))
        picked, total, tries = [], 0, 0
        while total < BG_BLOCKS * BG_LEN_S and cand and tries < 4000:
            tries += 1
            key, d = cand[rng.integers(len(cand))]
            if d >= BG_LEN_S:
                s = int(rng.integers(0, d - BG_LEN_S + 1))
                e = s + BG_LEN_S
            else:
                s, e = 0, d
            if any(s < y and e > x for x, y in busy[key]):
                continue
            busy[key].append((s, e))
            picked.append((key, s, e, d))
            total += e - s
        for key, s, e, d in picked:
            segs.append({"subject": subj, "run": key, "kind": "background", "start_s": max(0, s - WARM_S),
                         "score_start_s": s, "end_s": e, "seizures": [], "run_duration_s": d})
    segs.sort(key=lambda g: (g["subject"], g["run"], g["start_s"]))
    for i, g in enumerate(segs):
        g["id"] = i
    scored = sum(g["end_s"] - g["score_start_s"] for g in segs)
    processed = sum(g["end_s"] - g["start_s"] for g in segs)
    in_sz = sum(len(g["seizures"]) for g in segs)
    summary = {"seed": SEED, "patients": len({g["subject"] for g in segs}), "segments": len(segs),
               "seizure_segments": sum(g["kind"] == "seizure" for g in segs),
               "background_segments": sum(g["kind"] == "background" for g in segs),
               "seizures_total_in_training": n_sz, "seizures_in_segments": in_sz,
               "background_hours": round(sum(g["end_s"] - g["score_start_s"] for g in segs if g["kind"] == "background") / 3600, 1),
               "scored_hours": round(scored / 3600, 1), "processed_hours": round(processed / 3600, 1),
               "rules": {"pre_s": PRE_S, "post_s": POST_S, "warmup_s": WARM_S, "bg_hours": BG_BLOCKS, "min_whole_s": MIN_WHOLE_S,
                         "bg_len_s": BG_LEN_S, "bg_guard_s": BG_GUARD_S}}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"summary": summary, "segments": segs}, indent=1))
    print(json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
