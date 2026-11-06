#!/usr/bin/env python3
"""Score per-second predictions with both metric families (kept apart, never compared).

(a) SeizeIT2-paper metrics: threshold, RMS gate, official post-processing (merge < 2 s,
    drop < 8 s), any-overlap without tolerance, FA/h, mean over recordings.
    Reported "as published" (cross-channel gate, multi-counted TPs) and "corrected".
(b) SzCORE: the baseline's post-processed alarms at threshold 0.5 scored with timescoring
    (30 s / 60 s tolerance, 90 s merge, 5 min split), FP per 24 h, mean over subjects.

Usage:  python scripts/baselines/evaluate_predictions.py --run results/runs/<id> [--final-test]
Output: results/runs/<id>/metrics.json and metrics.md
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

from seizelut.eval import seizeit2 as s2
from seizelut.eval.events import mask_to_events
from seizelut.eval.runlog import log_test_access, require_test_access, touches_test
from seizelut.eval.szcore import aggregate, score_recording

REPO = Path(__file__).resolve().parents[2]
PUBLISHED = {"svm": {"sens": 71.1, "fa_h": 11.0, "auroc": 0.6995, "aupr": 0.0810},
             "chrononet": {"sens": 84.2, "fa_h": 100.5, "auroc": 0.7921, "aupr": 0.1042}}


def load(pred_dir: Path):
    recs = []
    for f in sorted(pred_dir.glob("*.npz")):
        d = np.load(f)
        sub, run = f.stem.split("_")[:2]
        recs.append({"subject": sub, "recording": f"{sub}_{run}", "y_pred": d["y_pred"].astype(float),
                     "y_true": d["y_true"].astype(int), "rms1": d["rms1"], "rms2": d["rms2"],
                     "duration_s": float(d["duration_s"])})
    return recs


def seizeit2_family(recs, as_published: bool) -> dict:
    gated = [(s2.rms_gate(r["y_pred"], r["rms1"], r["rms2"], as_published=as_published), r["y_true"]) for r in recs]
    res = s2.evaluate_recordings([(p, t[:len(p)]) for p, t in gated], fixed=not as_published)
    res.update(s2.epoch_auc(np.concatenate([p for p, _ in gated]), np.concatenate([t[:len(p)] for p, t in gated])))
    return res


def szcore_family(recs, thresholds=(0.5,)) -> dict:
    out = {}
    for th in thresholds:
        scores = []
        for r in recs:
            gated = s2.rms_gate(r["y_pred"], r["rms1"], r["rms2"], as_published=True)
            pp = s2.post_processing(gated, fs=1, th=th, margin=10)
            hyp = mask_to_events(pp > 0)
            ref = mask_to_events(r["y_true"] > 0)
            # reference = annotated seizures: window label grid shifted back by 1 s -> seizure seconds
            ref = [(a + 1, b) for a, b in ref]
            scores.append(score_recording(r["subject"], r["recording"], ref, hyp, r["duration_s"]))
        agg = aggregate(scores)
        out[f"{th:.2f}"] = {"mean_over_subjects": agg["mean_over_subjects"], "pooled": agg["pooled"],
                            "per_subject": agg["per_subject"]}
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", required=True)
    ap.add_argument("--predictions", default=None, help="default: cache/predictions/<run id>")
    ap.add_argument("--baseline", default="chrononet", choices=list(PUBLISHED))
    ap.add_argument("--final-test", action="store_true")
    ap.add_argument("--curve", action="store_true", help="also SzCORE at 11 thresholds (slow)")
    args = ap.parse_args()
    run = Path(args.run)
    recs = load(Path(args.predictions) if args.predictions else REPO / "cache" / "predictions" / run.name)
    subjects = sorted({r["subject"] for r in recs})
    require_test_access(subjects, args.final_test)
    if touches_test(subjects):
        log_test_access(run, "evaluation on test patients")
    pub = seizeit2_family(recs, as_published=True)
    cor = seizeit2_family(recs, as_published=False)
    sz = szcore_family(recs, np.round(np.linspace(0, 1, 11), 2) if args.curve else (0.5,))
    metrics = {"n_recordings": len(recs), "subjects": subjects, "seizeit2_as_published": pub,
               "seizeit2_corrected": cor, "szcore": sz, "published": PUBLISHED[args.baseline]}
    (run / "metrics.json").write_text(json.dumps(metrics, indent=1) + "\n")
    p05, c05, s05 = pub["at_0.5"], cor["at_0.5"], sz["0.50"]["mean_over_subjects"]
    P = PUBLISHED[args.baseline]
    md = [f"# {run.name}: {len(recs)} recordings, {len(subjects)} subjects\n",
          "## SeizeIT2-paper metrics (threshold 0.5)\n",
          "| | Sens OVLP (%) | FA/h | AUROC | AUPR | score |", "|---|---|---|---|---|---|",
          f"| published ({args.baseline}) | {P['sens']} | {P['fa_h']} | {P['auroc']} | {P['aupr']} | |",
          f"| ours, as published | {100 * p05['sens_ovlp']:.1f} | {p05['fa_ovlp']:.1f} | {pub['auroc']:.4f} | {pub['aupr']:.4f} | {p05['score']:.1f} |",
          f"| ours, corrected | {100 * c05['sens_ovlp']:.1f} | {c05['fa_ovlp']:.1f} | {cor['auroc']:.4f} | {cor['aupr']:.4f} | {c05['score']:.1f} |",
          "\nFA/h here is the any-overlap false-alarm rate (FP events per hour); the epoch-based rate is "
          f"{p05['fa_epoch']:.1f} (as published). The paper does not say which one Table 2 uses.\n",
          "## SzCORE (official post-processing, threshold 0.5; not comparable with the table above)\n",
          "| Sensitivity | Precision | F1 | FP/24h | sample F1 |", "|---|---|---|---|---|",
          f"| {s05['sensitivity']:.3f} | {s05['precision']:.3f} | {s05['f1']:.3f} | {s05['fp_per_24h']:.1f} | {s05['sample_f1']:.3f} |"]
    (run / "metrics.md").write_text("\n".join(md) + "\n")
    print("\n".join(md))
    return 0


if __name__ == "__main__":
    sys.exit(main())
