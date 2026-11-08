import pytest

from seizelut.data.bids import discover_runs
from seizelut.data.events import merge_intervals, seizure_class


def test_read_events(bids_root):
    runs = {r.key: r for r in discover_runs(bids_root)}
    ann = runs["sub-001_run-01"].read_annotations()
    assert ann.recording_duration == 120.0
    assert [e.event_type for e in ann.seizures] == ["sz_foc_ia_m_automatisms"]
    assert len(ann.impedance_checks) == 1
    assert ann.seizure_intervals() == [(40.0, 70.0)]
    assert runs["sub-001_run-02"].read_annotations().seizures == []   # bckg only


@pytest.mark.parametrize("t,cls", [
    ("sz_foc_a", "FA"), ("sz_foc_a_m_clonic", "FA"), ("sz_foc_ia", "FIA"),
    ("sz_foc_ia_nm_behavior", "FIA"), ("sz_foc_f2b", "FBTC"), ("sz_foc", "focal_unknown_awareness"),
    ("sz_foc_ua_m", "focal_unknown_awareness"), ("sz_uo_m", "unknown_onset"),
    ("sz_gen_m_tonic", "generalized"), ("sz", "unclassified")])
def test_seizure_class(t, cls):
    assert seizure_class(t) == cls


def test_non_seizure_rejected():
    with pytest.raises(ValueError):
        seizure_class("impd")


def test_merge_intervals():
    assert merge_intervals([(5, 8), (0, 2), (7, 10), (10, 11)]) == [(0, 2), (5, 11)]
