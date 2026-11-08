#!/usr/bin/env python3
"""Breakdown of a finished inner-CV run: sensitivity by seizure type, and missing-modality robustness
(N6, Section 6.3; Table 4 and 5 of Section 9.2 on the inner folds).

* By type: every annotated seizure (class from results/audit/seizures.csv: FBTC, FIA, FA,
  focal with unknown awareness, unknown onset) counts as detected when an alarm of the run's own
  best-F1 operating point overlaps [onset - 30 s, end + 60 s] (the SzCORE tolerances, applied per
  seizure without merging). Per class: seizures, detected, sensitivity.
* Missing modality (--missing; needs the run's fold models in checkpoints/<run>/): every validation
  patient is re-scored with ECG, EMG, motion, or all three removed (features and present bits set
  to 0, exactly as when the sensor is absent) and evaluated at the same operating point (gate, k
  and threshold unchanged, as on a deployed device). Per-patient event-F1 against the intact model,
  paired Wilcoxon test.

Inner folds only (training patients); never touches the test patients.
Usage:  python scripts/m5_breakdown.py --run results/runs/<id> [--missing]
Output: results/runs/<id>/breakdown.json and breakdown.md
"""
from __future__ import annotations

import argparse
import csv
import json
import pickle
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import yaml

from seizelut.data.featureset import FeatureStore
from seizelut.data.split import load_folds
from seizelut.eval.operating import gate_mask, kth_of_last, run_events_at, sweep
from seizelut.eval.stats import paired_wilcoxon
from seizelut.features import spec as S

REPO = Path(__file__).resolve().parents[1]
CLASSES = ["FBTC", "FIA", "FA", "focal_unknown_awareness", "unknown_onset"]
MISSING = {"no_ecg": ("ecg",), "no_emg": ("emg",), "no_mov": ("mov",), "eeg_only": ("ecg", "emg", "mov")}
PREFIX = {"ecg": ("ecg_", "present_ecg"), "emg": ("emg_", "present_emg"),
          "mov": ("mov_", "present_mov_acc", "present_mov_gyr")}


def seizure_classes(path=REPO / "results/audit/seizures.csv"):
    out = defaultdict(list)
    for r in csv.DictReader(open(path)):
        out[(r["subject"], r["run"])].append((float(r["onset_s"]), r["class"]))
    return out


def class_of(classes, subject, run, onset):
    for o, c in classes.get((subject, run), []):
        if abs(o - onset) <= 1.0:
            return c
    return "unmatched"


def detected_seizures(score, artefact, seizures, op):
    gated = np.where(gate_mask(artefact, op["gate"]), -np.inf, score)
    hyp = run_events_at(kth_of_last(gated, op["k"]), op["threshold"])
    return [any(h0 < b + 60.0 and h1 > a - 30.0 for h0, h1 in hyp) for a, b in seizures]


def f1_per_subject(counts):
    out = {}
    for s, (tp, fp, nref, _) in counts.items():
        se = tp / nref if nref else np.nan
        pr = tp / (tp + fp) if tp + fp else 0.0
        out[s] = 2 * se * pr / (se + pr) if nref and se + pr > 0 else (0.0 if nref else np.nan)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", required=True)
    ap.add_argument("--missing", action="store_true")
    ap.add_argument("--features-root", default=None)
    ap.add_argument("--out", default=None, help="repository-like root holding cache/oof and checkpoints (tests)")
    ap.add_argument("--folds-file", default=None, help="default: configs/<the run's folds file>")
    args = ap.parse_args()
    run = Path(args.run)
    root = Path(args.out) if args.out else REPO
    cfg = yaml.safe_load((run / "config.yaml").read_text())
    metrics = json.loads((run / "metrics.json").read_text())
    op = metrics["operating_points"]["best_f1"]
    folds = load_folds(args.folds_file or REPO / "configs" / cfg.get("folds_file", "folds_inner5.json"))
    folds = {s: f for s, f in folds.items() if f in metrics["folds"]}
    store = FeatureStore(cfg.get("feature_mode", "int"), root=Path(args.features_root) if args.features_root else None)
    store.stack = int(cfg.get("stack", 1))
    classes = seizure_classes()
    oof_dir = root / "cache" / "oof" / run.name
    nF = len(S.FEATURES)

    by_class = defaultdict(lambda: [0, 0])
    cond_runs = defaultdict(list)
    for k in sorted(set(folds.values())):
        va = sorted(s for s, f in folds.items() if f == k)
        fm = None
        if args.missing:
            with open(root / "checkpoints" / run.name / f"fold_{k}.pkl", "rb") as fh:
                fm = pickle.load(fh)
        for r in store.iter_runs(va):
            s = np.load(oof_dir / f"{r.subject}_{r.run}.npy")
            for det, (a, b) in zip(detected_seizures(s, r.artefact, r.seizures, op), r.seizures):
                c = class_of(classes, r.subject, r.run, a)
                by_class[c][0] += 1
                by_class[c][1] += int(det)
            base = {"subject": r.subject, "artefact": r.artefact, "seizures": r.seizures, "duration_s": r.duration_s}
            cond_runs["intact"].append({**base, "score": s})
            if fm is not None:
                for name, mods in MISSING.items():
                    X = r.X.copy()
                    drop = [i for i in range(X.shape[1])
                            if S.FEATURES[i % nF].startswith(tuple(p for m in mods for p in PREFIX[m]))]
                    X[:, drop] = 0
                    cond_runs[name].append({**base, "score": fm["model"].score(X[:, fm["cols"]]).astype(np.float32)})
            r.X = None

    out = {"run": run.name, "operating_point": {kk: op[kk] for kk in ("gate", "k", "threshold")},
           "by_class": {c: {"seizures": n, "detected": d, "sensitivity": d / n if n else None}
                        for c, (n, d) in sorted(by_class.items(), key=lambda t: -t[1][0])}}
    md = [f"# {run.name}: breakdown (inner folds, best-F1 operating point: gate {op['gate']}, k {op['k']})\n",
          "## Sensitivity by seizure type (alarm within [onset - 30 s, end + 60 s])\n",
          "| Class | Seizures | Detected | Sensitivity |", "|---|---|---|---|"]
    md += [f"| {c} | {v['seizures']} | {v['detected']} | {v['sensitivity']:.3f} |" for c, v in out["by_class"].items()]
    if args.missing:
        res = {}
        intact = None
        for name, runs in cond_runs.items():
            row = sweep(runs, ks=[op["k"]], gates=[op["gate"]], thresholds=[op["threshold"]])[0]
            f1s = f1_per_subject(row["per_subject"])
            if name == "intact":
                intact = f1s
            subs = sorted(f1s)
            test = paired_wilcoxon([f1s[s] for s in subs], [intact[s] for s in subs]) if name != "intact" else None
            res[name] = {kk: row[kk] for kk in ("f1", "sensitivity", "precision", "fp_per_24h")} | {"vs_intact": test}
        out["missing_modality"] = res
        md += ["\n## Missing modalities at test time (same operating point)\n",
               "| Condition | Event-F1 | Sens | Prec | FP/24h | median dF1 vs intact | p |", "|---|---|---|---|---|---|---|"]
        for name, v in res.items():
            t = v["vs_intact"]
            md.append(f"| {name} | {v['f1']:.3f} | {v['sensitivity']:.3f} | {v['precision']:.3f} | {v['fp_per_24h']:.1f} | "
                      + (f"{t['median_diff']:+.3f} | {t['p']:.3g} |" if t else "- | - |"))
    (run / "breakdown.json").write_text(json.dumps(out, indent=1, default=float) + "\n")
    (run / "breakdown.md").write_text("\n".join(md) + "\n")
    print("\n".join(md))
    return 0


if __name__ == "__main__":
    sys.exit(main())
