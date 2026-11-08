"""Interval-based SzCORE event scoring, equivalent to `timescoring` (tests/test_fastscore.py)
but fast enough for threshold sweeps over thousands of recordings.

Rules (timescoring EventScoring defaults = SzCORE): merge events separated by < 90 s
(reference and hypothesis alike), split events longer than 300 s, extend each reference
event by 30 s before / 60 s after (clipped to the file), a reference event is detected if any
hypothesis overlaps its extended span, a hypothesis is a false positive if it overlaps no
detected extended span. Reported numbers in the paper still come from `timescoring`.
"""
from __future__ import annotations

import numpy as np

TOL_PRE, TOL_POST, MERGE, MAXDUR = 30.0, 60.0, 90.0, 300.0


def _merge(ev, gap):
    out = []
    for a, b in ev:
        if out and a - out[-1][1] < gap:
            out[-1][1] = b
        else:
            out.append([a, b])
    return out


def _split(ev, maxdur):
    out = []
    for a, b in ev:
        while b - a > maxdur:
            out.append([a, a + maxdur])
            a = a + maxdur
        out.append([a, b])
    return out


def prepare_ref(ref_events, duration_s):
    ref = _split(_merge(sorted([list(e) for e in ref_events]), MERGE), MAXDUR)
    return [(max(0.0, a - TOL_PRE), min(duration_s, b + TOL_POST)) for a, b in ref]


def score_events(ext_ref, hyp_events) -> tuple[int, int, int]:
    """(tp, fp, n_ref) for one recording; ext_ref from prepare_ref."""
    hyp = _split(_merge(sorted([list(e) for e in hyp_events]), MERGE), MAXDUR)
    if not ext_ref:
        return 0, len(hyp), 0
    if not hyp:
        return 0, 0, len(ext_ref)
    h = np.array(hyp, dtype=float)
    r = np.array(ext_ref, dtype=float)
    ov = (h[:, None, 0] < r[None, :, 1]) & (h[:, None, 1] > r[None, :, 0])
    detected = ov.any(axis=0)
    fp = int((~(ov & detected[None, :]).any(axis=1)).sum())
    return int(detected.sum()), fp, len(ext_ref)
