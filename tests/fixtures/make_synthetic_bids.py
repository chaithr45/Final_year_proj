#!/usr/bin/env python3
"""Generate a tiny synthetic SeizeIT2-like BIDS tree for CI. NOT real patient data.

It mirrors the real layout and the quirks the data audit found: 256 Hz and
250 Hz files, 12 motion channels at 25 Hz, three EEG montages, a run without
ECG/EMG/motion, impedance-check events, a flat-line span and a seizure that
starts within the first window.

Usage:  python tests/fixtures/make_synthetic_bids.py [out_dir]
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
try:
    from seizelut.data.edf import EdfSignal, write_edf
except ImportError:  # running from a checkout without `pip install -e .`
    import importlib.util
    spec = importlib.util.spec_from_file_location("edf", Path(__file__).resolve().parents[2] / "src/data/edf.py")
    edf = importlib.util.module_from_spec(spec)
    sys.modules["edf"] = edf
    spec.loader.exec_module(edf)
    EdfSignal, write_edf = edf.EdfSignal, edf.write_edf

DEFAULT_OUT = Path(__file__).resolve().parent / "synthetic_bids"
TASK = "szMonitoring"
MOV_LABELS = [f"{dev} SD {kind} {ax}" for dev in ("EEG", "ECGEMG")
              for kind, axes in (("ACC", "XYZ"), ("GYR", "ABC")) for ax in axes]

# subject, run, seconds, fs, montage, modalities, events [(onset, dur, type)]
RUNS = [
    ("sub-001", "run-01", 120, 256, "left", ("eeg", "ecg", "emg", "mov"),
     [(5.0, 20.0, "impd"), (40.0, 30.0, "sz_foc_ia_m_automatisms")]),
    ("sub-001", "run-02", 60, 256, "left", ("eeg",), [(0.0, 60.0, "bckg")]),
    ("sub-002", "run-01", 90, 250, "right", ("eeg", "ecg", "emg", "mov"),
     [(0.5, 3.0, "sz_foc_a"), (50.0, 12.0, "sz_foc_f2b")]),
    ("sub-097", "run-01", 90, 256, "bilateral", ("eeg", "ecg", "emg", "mov"),
     [(30.0, 15.0, "sz_uo")]),
]
EEG_LABELS = {"left": ["BTEleft SD", "CROSStop SD"], "right": ["BTEright SD", "CROSStop SD"],
              "bilateral": ["BTEleft SD", "BTEright SD"]}


def _uv_signal(rng, n, fs, amp_uv, freq_hz, seizure_mask=None):
    t = np.arange(n) / fs
    x = amp_uv * np.sin(2 * np.pi * freq_hz * t) + rng.normal(0, amp_uv / 3, n)
    if seizure_mask is not None:
        x = x + seizure_mask * 4 * amp_uv * np.sin(2 * np.pi * 5.0 * t)
    return x


def _to_signal(label, x_phys, fs, pmin, pmax, unit):
    gain = (pmax - pmin) / 65535.0
    dig = np.clip(np.round((x_phys - pmin) / gain - 32768), -32768, 32767).astype(np.int16)
    return EdfSignal(label=label, digital=dig, fs=fs, physical_min=pmin, physical_max=pmax, physical_dim=unit)


def _sidecar(mod, fs, n_ch, montage, seconds):
    key = mod.upper()
    d = {f"{key}Reference": "n/a", "SamplingFrequency": fs, "PowerLineFrequency": "n/a",
         "SoftwareFilters": "n/a", f"{key}ChannelCount": n_ch, f"{key}Montage": montage if mod == "eeg" else "n/a",
         "RecordingType": "discontinuous", "RecordingDuration": float(seconds), "TaskName": TASK}
    if mod == "eeg":
        d["EEGPlacementScheme"] = "behind-the-ear"
    return d


def generate(out: Path = DEFAULT_OUT) -> Path:
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    (out / "dataset_description.json").write_text(json.dumps(
        {"Name": "SeizeIT2 synthetic CI fixture (not patient data)", "BIDSVersion": "1.8.0",
         "DatasetType": "raw", "License": "CC0"}, indent=2) + "\n")
    (out / "participants.tsv").write_text("participant_id\tsex\nsub-001\tf\nsub-002\tm\nsub-097\tm\n")

    for i, (sub, run, seconds, fs, montage, mods, events) in enumerate(RUNS):
        rng = np.random.default_rng(1000 + i)
        stem = f"{sub}_ses-01_task-{TASK}_{run}"
        n = seconds * fs
        t = np.arange(n) / fs
        sz = np.zeros(n)
        for onset, dur, typ in events:
            if typ.startswith("sz"):
                sz[(t >= onset) & (t < onset + dur)] = 1.0
        for mod in mods:
            d = out / sub / "ses-01" / mod
            d.mkdir(parents=True, exist_ok=True)
            if mod == "eeg":
                sigs = []
                for c, lb in enumerate(EEG_LABELS[montage]):
                    x = _uv_signal(rng, n, fs, 20.0 + 10 * c, 10.0, sz)
                    if sub == "sub-001" and run == "run-01" and c == 0:
                        x[100 * fs:103 * fs] = x[100 * fs]       # 3 s flat-line
                    sigs.append(_to_signal(lb, x, fs, -1500.0, 1500.0, "uV"))
            elif mod == "ecg":
                beats = (np.sin(2 * np.pi * 1.2 * t) > 0.97).astype(float) * 800.0
                sigs = [_to_signal("ECG SD", beats + rng.normal(0, 10, n), fs, -2000.0, 2000.0, "uV")]
            elif mod == "emg":
                sigs = [_to_signal("EMG SD", _uv_signal(rng, n, fs, 15.0, 40.0, sz), fs, -3000.0, 3000.0, "uV")]
            else:
                m = seconds * 25
                sigs = [_to_signal(lb, rng.normal(0, 0.05, m) + (1.0 if lb.endswith("ACC Z") else 0.0),
                                   25, -4.0, 4.0, "g") for lb in MOV_LABELS]
            write_edf(d / f"{stem}_{mod}.edf", sigs)
            (d / f"{stem}_{mod}.json").write_text(
                json.dumps(_sidecar(mod, sigs[0].fs, len(sigs), montage, seconds), indent=4) + "\n")
        rows = ["onset\tduration\teventType\tlateralization\tlocalization\tvigilance\tconfidence\tchannels\tdateTime\trecordingDuration"]
        for onset, dur, typ in events:
            sz_row = typ.startswith("sz")
            rows.append("\t".join([f"{onset:.2f}", f"{dur:.2f}", typ, "left" if sz_row else "n/a",
                                   "temp" if sz_row else "n/a", "awake" if sz_row else "n/a",
                                   "n/a", "n/a", "2000-01-01 00:00:00", f"{seconds:.2f}"]))
        (out / sub / "ses-01" / "eeg" / f"{stem}_events.tsv").write_text("\n".join(rows) + "\n")
    return out


if __name__ == "__main__":
    print(generate(Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUT))
