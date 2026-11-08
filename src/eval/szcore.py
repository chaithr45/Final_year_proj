"""SzCORE event- and sample-based scoring (Dan et al., Epilepsia 2024).

Counting is delegated to the `timescoring` library (as the prompt requires);
this module only aggregates. Event rules: any overlap, 30 s pre-ictal and 60 s
post-ictal tolerance, events closer than 90 s merged, events longer than 5 min
split. Sample rules: 1 Hz labels.

Aggregation (Section 7.4): counts are summed over the recordings of a subject,
metrics are computed per subject and averaged over subjects; precision counts
as 0 for a subject with no detections. Pooled totals are reported as well.
"""
from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass

import numpy as np

SZCORE_PARAMS = dict(toleranceStart=30.0, toleranceEnd=60.0, minOverlap=0.0,
                     maxEventDuration=300.0, minDurationBetweenEvents=90.0)


@dataclass
class RecordingScore:
    subject: str
    recording: str
    duration_s: float
    ref_events: int
    tp: int
    fp: int
    s_tp: int
    s_fp: int
    s_fn: int
    s_tn: int


def score_recording(subject: str, recording: str, ref_events, hyp_events, duration_s: float,
                    params: dict | None = None) -> RecordingScore:
    """Score one recording. Events are (start_s, end_s) lists."""
    from timescoring import scoring
    from timescoring.annotations import Annotation

    n = int(math.ceil(duration_s))
    clip = lambda evs: [(max(0.0, float(a)), min(float(n), float(b))) for a, b in evs if min(float(n), b) > max(0.0, a)]
    ref = Annotation(clip(ref_events), 1, n)
    hyp = Annotation(clip(hyp_events), 1, n)
    ev = scoring.EventScoring(ref, hyp, scoring.EventScoring.Parameters(**(params or SZCORE_PARAMS)))
    sm = scoring.SampleScoring(ref, hyp, fs=1)
    s_tn = int(n - sm.tp - sm.fp - (sm.refTrue - sm.tp))
    return RecordingScore(subject, recording, float(duration_s), int(ev.refTrue), int(ev.tp), int(ev.fp),
                          int(sm.tp), int(sm.fp), int(sm.refTrue - sm.tp), s_tn)


def _metrics(tp, fp, ref, hours):
    sens = tp / ref if ref else float("nan")
    prec = tp / (tp + fp) if (tp + fp) else 0.0
    f1 = 2 * sens * prec / (sens + prec) if ref and (sens + prec) > 0 else (0.0 if ref else float("nan"))
    return {"sensitivity": sens, "precision": prec, "f1": f1, "fp_per_24h": 24 * fp / hours if hours else float("nan")}


def aggregate(scores: list[RecordingScore]) -> dict:
    """Per-subject metrics, their mean over subjects, and pooled totals."""
    by = defaultdict(list)
    for s in scores:
        by[s.subject].append(s)
    per_subject = {}
    for sub, rs in sorted(by.items()):
        tp, fp, ref = sum(r.tp for r in rs), sum(r.fp for r in rs), sum(r.ref_events for r in rs)
        hours = sum(r.duration_s for r in rs) / 3600
        stp, sfp, sfn = sum(r.s_tp for r in rs), sum(r.s_fp for r in rs), sum(r.s_fn for r in rs)
        m = _metrics(tp, fp, ref, hours)
        m.update(hours=hours, ref_events=ref, tp=tp, fp=fp,
                 sample_sensitivity=stp / (stp + sfn) if (stp + sfn) else float("nan"),
                 sample_precision=stp / (stp + sfp) if (stp + sfp) else 0.0)
        ss, sp = m["sample_sensitivity"], m["sample_precision"]
        m["sample_f1"] = 2 * ss * sp / (ss + sp) if (stp + sfn) and (ss + sp) > 0 else (0.0 if (stp + sfn) else float("nan"))
        per_subject[sub] = m
    keys = ["sensitivity", "precision", "f1", "fp_per_24h", "sample_sensitivity", "sample_precision", "sample_f1"]
    mean = {k: float(np.nanmean([m[k] for m in per_subject.values()])) for k in keys}
    tp, fp, ref = sum(s.tp for s in scores), sum(s.fp for s in scores), sum(s.ref_events for s in scores)
    pooled = _metrics(tp, fp, ref, sum(s.duration_s for s in scores) / 3600)
    pooled.update(tp=tp, fp=fp, ref_events=ref)
    return {"per_subject": per_subject, "mean_over_subjects": mean, "pooled": pooled}
