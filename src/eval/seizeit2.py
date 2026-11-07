"""Metrics of the SeizeIT2 dataset paper (Bhagubai et al., 2025, Table 2).

A port of the official evaluation code (biomedepi/seizeit2, net/utils.py and
net/main_func.py::evaluate), kept literal so the published numbers can be
reproduced. Two defects of the original are exposed as switches:

* `fixed=False` (as published): in any-overlap matching a predicted event that
  overlaps k reference events adds k true positives, and k predicted events on one
  reference event add k true positives.
  `fixed=True`: TP = number of reference events overlapped by >= 1 prediction.
* `rms_gate(..., as_published=True)`: `rmsa = rmsa_f and rmsa_c` on two Python
  lists returns the second list, so only the cross channel gates the predictions.
  `as_published=False`: a window is valid only if both channels are in 13-150 uV.

Rules (from the code): predictions at 1 Hz; threshold; events closer than
0.2*margin = 2 s merged; events shorter than 0.8*margin = 8 s dropped; any-overlap
with no tolerance; false alarms per hour = FP * 3600 / recording seconds; every
metric computed per recording and averaged over recordings (nanmean); the paper's
operating point is threshold 0.5. These metrics are NOT comparable with SzCORE.
"""
from __future__ import annotations

import math

import numpy as np

THRESHOLDS = np.around(np.linspace(0, 1, 51), 2)   # official sweep; index 25 = 0.5


# ---------------------------------------------------------------- literal ports

def mask2eventList(mask, fs):
    """Port of net/utils.py::mask2eventList (including its edge-case behaviour)."""
    events, tmp = [], []
    m = np.array(mask, dtype=int)
    start_i = np.where(np.diff(m) == 1)[0]
    end_i = np.where(np.diff(m) == -1)[0]
    if len(start_i) == 0 and m[0]:
        events.append([0, (len(m) - 1) / fs])
    else:
        if m[0]:
            events.append([0, (end_i[0] + 1) / fs])
            end_i = np.delete(end_i, 0)
        if m[-1]:
            if len(start_i):
                tmp = [[(start_i[-1] + 1) / fs, len(m) / fs]]
                start_i = np.delete(start_i, len(start_i) - 1)
        for i in range(len(start_i)):
            events.append([(start_i[i] + 1) / fs, (end_i[i] + 1) / fs])
        events += tmp
    return events


def eventList2Mask(events, total_len, fs):
    mask = np.zeros(total_len)
    for a, b in events:
        mask[min(int(a * fs), total_len):min(int(b * fs), total_len)] = 1
    return mask


def merge_events(events, distance):
    events = [list(e) for e in events]
    i = 1
    while i < len(events):
        if events[i][0] - events[i - 1][1] < distance:
            events[i - 1][1] = events[i][1]
            events.pop(i)
        else:
            i += 1
    return events


def get_events(events, margin):
    merged = merge_events(events, 0.2 * margin)
    return [e for e in merged if e[1] - e[0] >= margin * 0.8]


def post_processing(y_pred, fs, th, margin=10):
    """Threshold, merge events < 2 s apart, drop events < 8 s (official)."""
    pred = np.asarray(y_pred) > th
    events = get_events(mask2eventList(pred, fs), margin)
    return eventList2Mask(events, len(y_pred), fs)


def _overlap(a, b):
    return max(0, min(a[1], b[1]) - max(a[0], b[0]))


def perf_measure_epoch(y_true, y_pred):
    t = np.asarray(y_true).astype(bool)
    p = np.asarray(y_pred).astype(bool)
    return int(np.sum(t & p)), int(np.sum(p & ~t)), int(np.sum(~t & ~p)), int(np.sum(~p & t))


def perf_measure_ovlp(y_true, y_pred, fs, fixed=False):
    true_events = mask2eventList(y_true, fs) if np.any(y_true) else []
    pred_events = mask2eventList(y_pred, fs) if np.any(y_pred) else []
    if fixed:
        tp = sum(1 for tr in true_events if any(_overlap(tr, pr) > 0 for pr in pred_events))
        fp = sum(1 for pr in pred_events if not any(_overlap(pr, tr) > 0 for tr in true_events))
        return tp, fp, len(true_events) - tp
    tp = fp = fn = 0
    for pr in pred_events:
        found = False
        for tr in true_events:
            if _overlap(pr, tr) > 0:
                tp += 1
                found = True
        if not found:
            fp += 1
    for tr in true_events:
        if not any(_overlap(tr, pr) > 0 for pr in pred_events):
            fn += 1
    return tp, fp, fn


def get_metrics_scoring(y_pred, y_true, fs, th, fixed=False):
    """Port of net/utils.py::get_metrics_scoring for one recording."""
    nan = float("nan")
    total_n = len(y_pred) * (1 / fs)
    total_seiz = np.sum(y_true)
    y_pp = post_processing(y_pred, fs=fs, th=th, margin=10)
    tp_e, fp_e, tn_e, fn_e = perf_measure_epoch(y_true, y_pp)
    tp_o, fp_o, fn_o = perf_measure_ovlp(y_true, y_pp, fs=1 / 2, fixed=fixed)
    if total_seiz == 0:
        sens_o = prec_o = f1_o = nan
    else:
        sens_o = tp_o / (tp_o + fn_o)
        if tp_o == 0 and fp_o == 0:
            prec_o = f1_o = nan
        else:
            prec_o = tp_o / (tp_o + fp_o)
            f1_o = nan if prec_o + sens_o == 0 else 2 * prec_o * sens_o / (prec_o + sens_o)
    fa_o = fp_o * 3600 / total_n
    fa_e = fp_e * 3600 / total_n
    if total_seiz == 0:
        sens_e = prec_e = f1_e = nan
    else:
        sens_e = tp_e / (tp_e + fn_e)
        if tp_o == 0 and fp_o == 0:          # sic: the original tests the OVLP counts here
            prec_e = f1_e = nan
        else:
            prec_e = tp_e / (tp_e + fp_e) if (tp_e + fp_e) else nan
            f1_e = nan if not (prec_e + sens_e) or math.isnan(prec_e) else 2 * prec_e * sens_e / (prec_e + sens_e)
    spec_e = tn_e / (tn_e + fp_e) if (tn_e + fp_e) else nan
    return dict(sens_ovlp=sens_o, prec_ovlp=prec_o, fa_ovlp=fa_o, f1_ovlp=f1_o, sens_epoch=sens_e,
                spec_epoch=spec_e, prec_epoch=prec_e, fa_epoch=fa_e, f1_epoch=f1_e)


# ---------------------------------------------------------------- RMS gate

def rms_valid(rms: np.ndarray, low: float = 13.0, high: float = 150.0) -> np.ndarray:
    return ((rms > low) & (rms < high)).astype(int)


def rms_gate(y_pred, rms_ch1, rms_ch2, as_published=True):
    """Zero the predictions of windows rejected by the RMS rule."""
    valid = rms_valid(np.asarray(rms_ch2)) if as_published else \
        rms_valid(np.asarray(rms_ch1)) & rms_valid(np.asarray(rms_ch2))
    y_pred = np.asarray(y_pred, dtype=float)
    valid = valid[: len(y_pred)]
    return np.where(valid == 0, 0, y_pred[: len(valid)])


# ---------------------------------------------------------------- evaluation

def evaluate_recordings(recs, fixed=False, thresholds=THRESHOLDS):
    """recs: iterable of (y_pred, y_true) per recording (already RMS-gated), 1 Hz.

    Returns per-threshold metrics averaged over recordings (nanmean), the official
    score (100*sens_ovlp - 0.4*FA_epoch, per recording, then mean) and the
    operating point at threshold 0.5.
    """
    keys = ["sens_ovlp", "prec_ovlp", "fa_ovlp", "f1_ovlp", "sens_epoch", "spec_epoch", "prec_epoch",
            "fa_epoch", "f1_epoch"]
    per = {k: [] for k in keys + ["score"]}
    for y_pred, y_true in recs:
        rows = [get_metrics_scoring(y_pred, y_true, 1, th, fixed=fixed) for th in thresholds]
        for k in keys:
            per[k].append([r[k] for r in rows])
        per["score"].append([r["sens_ovlp"] * 100 - 0.4 * r["fa_epoch"] for r in rows])
    with np.errstate(all="ignore"):
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            curves = {k: np.nanmean(np.array(v, dtype=float), axis=0) for k, v in per.items()}
    i05 = int(np.argmin(np.abs(np.asarray(thresholds) - 0.5)))
    return {"thresholds": list(map(float, thresholds)), "curves": {k: v.tolist() for k, v in curves.items()},
            "at_0.5": {k: float(v[i05]) for k, v in curves.items()}, "n_recordings": len(per["score"])}


def epoch_auc(y_score_all: np.ndarray, y_true_all: np.ndarray) -> dict:
    """AUROC and AUPR over all 1 s epochs pooled (definition assumed; the paper only
    says 'epoch-based')."""
    from sklearn.metrics import average_precision_score, roc_auc_score
    y_true_all = np.asarray(y_true_all).astype(int)
    if y_true_all.min() == y_true_all.max():
        return {"auroc": float("nan"), "aupr": float("nan")}
    return {"auroc": float(roc_auc_score(y_true_all, y_score_all)),
            "aupr": float(average_precision_score(y_true_all, y_score_all))}


def recording_auc(recs) -> dict:
    """The other reading of 'epoch-based' AUROC/AUPR: per recording, then the mean over the
    recordings that contain a seizure (the others have no AUC; every other Table 2 metric is
    averaged over recordings the same way). recs: iterable of (y_score, y_true) at 1 Hz."""
    from sklearn.metrics import average_precision_score, roc_auc_score
    roc, pr = [], []
    for y_score, y_true in recs:
        y_true = np.asarray(y_true).astype(int)
        if y_true.min() == y_true.max():
            continue
        roc.append(roc_auc_score(y_true, y_score))
        pr.append(average_precision_score(y_true, y_score))
    nan = float("nan")
    return {"auroc_rec_mean": float(np.mean(roc)) if roc else nan,
            "aupr_rec_mean": float(np.mean(pr)) if pr else nan, "n_rec_auc": len(roc)}
