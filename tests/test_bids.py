import json

import numpy as np

from seizelut.data.bids import discover_runs, subjects_in
from seizelut.data.montage import eeg_channel_pair, montage_type


def test_discover_runs(bids_root):
    runs = discover_runs(bids_root)
    assert [r.key for r in runs] == ["sub-001_run-01", "sub-001_run-02", "sub-002_run-01", "sub-097_run-01"]
    assert subjects_in(runs) == ["sub-001", "sub-002", "sub-097"]
    assert runs[0].modalities == ["eeg", "ecg", "emg", "mov"]
    assert runs[1].modalities == ["eeg"]            # missing ECG/EMG/motion
    assert all(r.events is not None for r in runs)


def test_subject_filter(bids_root):
    assert {r.subject for r in discover_runs(bids_root, ["sub-097"])} == {"sub-097"}


def test_sampling_rates_come_from_files(bids_root):
    for r in discover_runs(bids_root):
        for m in r.modalities:
            side = r.read_sidecar(m)
            h = r.read_header(m)
            rates = {h.sampling_rate(lb) for lb in h.labels}
            assert rates == {side["SamplingFrequency"]}
    fs = {r.key: r.read_sidecar("eeg")["SamplingFrequency"] for r in discover_runs(bids_root)}
    assert fs["sub-002_run-01"] == 250 and fs["sub-001_run-01"] == 256


def test_motion_has_12_channels_at_25hz(bids_root):
    r = discover_runs(bids_root)[0]
    d = r.read_signals("mov")
    assert len(d.labels) == 12 and set(d.fs.values()) == {25.0}


def test_montages(bids_root):
    got = {r.key: montage_type(r.read_header("eeg").labels) for r in discover_runs(bids_root)}
    assert got == {"sub-001_run-01": "left", "sub-001_run-02": "left",
                   "sub-002_run-01": "right", "sub-097_run-01": "bilateral"}
    assert eeg_channel_pair(["CROSStop SD", "BTEleft SD"]) == ("BTEleft SD", "CROSStop SD")
    assert eeg_channel_pair(["BTEright SD", "CROSStop SD"]) == ("BTEright SD", "CROSStop SD")
    assert eeg_channel_pair(["BTEright SD", "BTEleft SD"]) == ("BTEleft SD", "BTEright SD")


def test_signal_duration_matches_annotation(bids_root):
    for r in discover_runs(bids_root):
        ann = r.read_annotations()
        assert r.read_signals("eeg").duration_s == ann.recording_duration


def test_fixture_is_reproducible(bids_root, tmp_path):
    import importlib.util
    spec = importlib.util.spec_from_file_location("gen", bids_root.parent / "make_synthetic_bids.py")
    gen = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gen)
    out = gen.generate(tmp_path / "regen")
    for f in sorted(bids_root.rglob("*")):
        if f.is_file():
            assert (out / f.relative_to(bids_root)).read_bytes() == f.read_bytes(), f
