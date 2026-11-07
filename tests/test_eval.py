import math

import numpy as np
import pytest

from seizelut.eval import seizeit2 as s2
from seizelut.eval.events import events_to_mask, mask_to_events
from seizelut.eval.stats import bootstrap_ci, paired_wilcoxon
from seizelut.eval.szcore import aggregate, score_recording
from seizelut.models.postprocess import alarm_events, k_of_n, postprocess

pytest.importorskip("timescoring")


def test_mask_events_roundtrip():
    m = np.array([0, 1, 1, 0, 0, 1, 0, 1, 1, 1], bool)
    ev = mask_to_events(m)
    assert ev == [(1, 3), (5, 6), (7, 10)]
    assert np.array_equal(events_to_mask(ev, 10), m)


# ------------------------------------------------------------------ SzCORE

def test_szcore_tolerance_counts_early_alarm_as_tp():
    r = score_recording("s", "r", [(100, 160)], [(80, 95)], 3600)
    assert (r.ref_events, r.tp, r.fp) == (1, 1, 0)


def test_szcore_far_alarm_is_fp_and_miss():
    r = score_recording("s", "r", [(100, 160)], [(1000, 1010)], 3600)
    assert (r.tp, r.fp) == (0, 1)


def test_szcore_merges_events_closer_than_90s():
    r = score_recording("s", "r", [(100, 120), (180, 200)], [], 3600)
    assert r.ref_events == 1


def test_szcore_splits_events_longer_than_5min():
    r = score_recording("s", "r", [(100, 800)], [(110, 120)], 3600)
    assert r.ref_events == 3 and r.tp == 1


def test_sample_scoring():
    r = score_recording("s", "r", [(10, 20)], [(15, 25)], 100)
    assert (r.s_tp, r.s_fp, r.s_fn) == (5, 5, 5) and r.s_tn == 85


def test_aggregate_per_subject_mean_and_zero_precision():
    a = score_recording("A", "r1", [(100, 160)], [(110, 120)], 43200)   # TP, 12 h
    b = score_recording("A", "r2", [], [(1000, 1010)], 43200)           # FP, 12 h
    c = score_recording("B", "r1", [(100, 160)], [], 86400)             # miss, no detections
    agg = aggregate([a, b, c])
    A, B = agg["per_subject"]["A"], agg["per_subject"]["B"]
    assert A["sensitivity"] == 1 and A["precision"] == 0.5 and A["fp_per_24h"] == pytest.approx(1.0)
    assert B["sensitivity"] == 0 and B["precision"] == 0.0 and B["f1"] == 0.0
    assert agg["mean_over_subjects"]["sensitivity"] == pytest.approx(0.5)
    assert agg["pooled"]["sensitivity"] == pytest.approx(0.5) and agg["pooled"]["fp_per_24h"] == pytest.approx(0.5)


def test_fixed_overlap_matches_timescoring_without_tolerance():
    rng = np.random.default_rng(3)
    params = dict(toleranceStart=0, toleranceEnd=0, minOverlap=0, maxEventDuration=1e9, minDurationBetweenEvents=0)
    for _ in range(200):
        n = 600
        y_true = np.zeros(n, int)
        for _ in range(rng.integers(0, 4)):
            a = rng.integers(0, n - 60)
            y_true[a:a + rng.integers(3, 60)] = 1
        y_pred = np.zeros(n, int)
        for _ in range(rng.integers(0, 6)):
            a = rng.integers(0, n - 30)
            y_pred[a:a + rng.integers(1, 30)] = 1
        tp, fp, fn = s2.perf_measure_ovlp(y_true, y_pred, fs=1, fixed=True)
        r = score_recording("s", "r", mask_to_events(y_true), mask_to_events(y_pred), n, params)
        assert (tp, fp, tp + fn) == (r.tp, r.fp, r.ref_events)


# ------------------------------------------------------------------ SeizeIT2 paper metrics

def test_official_postprocessing_merges_2s_and_drops_short():
    y = np.zeros(60)
    y[10:15] = 0.9   # 5 s
    y[16:20] = 0.9   # gap 1 s -> merged to 10 s event
    y[40:45] = 0.9   # 5 s alone -> dropped (< 8 s)
    pp = s2.post_processing(y, fs=1, th=0.5)
    assert pp[10:20].all() and not pp[40:45].any()


def test_published_overlap_double_counts_tp():
    y_true = np.zeros(100, int)
    y_true[10:20] = 1
    y_true[30:40] = 1
    y_true[70:80] = 1
    y_pred = np.zeros(100, int)
    y_pred[15:35] = 1          # one alarm spans two seizures
    assert s2.perf_measure_ovlp(y_true, y_pred, 1) == (2, 0, 1)
    y_pred2 = np.zeros(100, int)
    y_pred2[11:13] = 1
    y_pred2[15:17] = 1         # two alarms on one seizure, two seizures missed
    assert s2.perf_measure_ovlp(y_true, y_pred2, 1) == (2, 0, 2)               # sens 0.5 (wrong)
    assert s2.perf_measure_ovlp(y_true, y_pred2, 1, fixed=True) == (1, 0, 2)   # sens 1/3


def test_get_metrics_scoring_and_score():
    y_true = np.zeros(3600, int)
    y_true[1000:1060] = 1
    y_pred = np.zeros(3600)
    y_pred[1010:1030] = 0.8
    y_pred[2000:2010] = 0.9    # 10 s false alarm survives post-processing
    m = s2.get_metrics_scoring(y_pred, y_true, 1, 0.5)
    assert m["sens_ovlp"] == 1 and m["fa_ovlp"] == pytest.approx(1.0) and m["fa_epoch"] == pytest.approx(10.0)
    res = s2.evaluate_recordings([(y_pred, y_true)])
    assert res["at_0.5"]["score"] == pytest.approx(100 - 0.4 * 10.0)


def test_recordings_without_seizures_are_nan_and_skipped_by_nanmean():
    y_true = np.zeros(600, int)
    m = s2.get_metrics_scoring(np.zeros(600), y_true, 1, 0.5)
    assert math.isnan(m["sens_ovlp"]) and m["fa_ovlp"] == 0


def test_rms_gate_as_published_uses_second_channel_only():
    pred = np.ones(4)
    ch1 = np.array([5, 50, 50, 500.0])
    ch2 = np.array([50, 50, 5, 50.0])
    assert s2.rms_gate(pred, ch1, ch2, as_published=True).tolist() == [1, 1, 0, 1]
    assert s2.rms_gate(pred, ch1, ch2, as_published=False).tolist() == [0, 1, 0, 0]


# ------------------------------------------------------------------ post-processing and stats

def test_k_of_n_and_alarm_events():
    dec = np.zeros(40, bool)
    dec[5:13] = True
    alarm = k_of_n(dec, k=8, n=10)
    assert np.flatnonzero(alarm).tolist() == [12, 13, 14]
    assert alarm_events(alarm) == [(12, 15)]
    assert postprocess(np.where(dec, 9, 0), 5) == [(12, 15)]
    assert alarm_events(np.isin(np.arange(300), [10, 11, 200]), merge_s=90) == [(10, 12), (200, 201)]


def test_stats():
    a = np.arange(20.0)
    assert paired_wilcoxon(a + 1, a)["p"] < 0.001
    ci = bootstrap_ci(np.ones(10) * 3, n_boot=200)
    assert ci["low"] == ci["high"] == 3


def test_recording_auc_means_over_recordings_with_seizures():
    from sklearn.metrics import average_precision_score, roc_auc_score
    rng = np.random.default_rng(0)
    recs = []
    for has_sz in (True, True, False):
        t = np.zeros(300, int)
        if has_sz:
            t[100:140] = 1
        recs.append((np.clip(0.3 * t + rng.random(300) * 0.8, 0, 1), t))
    out = s2.recording_auc(recs)
    assert out["n_rec_auc"] == 2
    assert out["auroc_rec_mean"] == pytest.approx(np.mean([roc_auc_score(t, p) for p, t in recs[:2]]))
    assert out["aupr_rec_mean"] == pytest.approx(np.mean([average_precision_score(t, p) for p, t in recs[:2]]))
    assert math.isnan(s2.recording_auc(recs[2:])["aupr_rec_mean"])
