#!/usr/bin/env python3
"""Recorded inputs for the live demo (run in the project repository, not on the board).

Cuts short segments of raw integer samples out of the exported test vectors (export/<model>/vectors/<rec>/inputs/)
and writes demo/segments/<id>.npz (int16 per sensor: eeg1, eeg2 and, when recorded, ecg, emg, acc_x/y/z, gyr_x/y/z)
plus demo/segments/index.json. Each segment starts `pre` seconds before the part the audience watches, so the
filters and the 64-s context averages are settled; the demo server runs those seconds at full speed.

For each segment the outputs the demo will produce are computed here the same way (streaming C front end from the
segment's first sample, then the software model of the classifier) and stored as `expected`, together with what the
full-recording run gave at the same windows, so the guide can say what the audience will see.

The recordings come from held-out test patients (sub-097..sub-100), whose results were already reported in M6 and
whose vectors are part of the board kit; nothing here re-scores or tunes anything on them.

Usage: python hw/kv260/tools/make_demo_segments.py [--export export/n4_distill_s0]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

KIT = Path(__file__).resolve().parents[1]
REPO = KIT.parents[1]
sys.path.insert(0, str(KIT / "board"))
sys.path.insert(0, str(KIT / "board" / "frontend"))

KEYMAP = {"ecg_ECG_SD": "ecg", "emg_EMG_SD": "emg", "mov_ECGEMG_SD_ACC_X": "acc_x", "mov_ECGEMG_SD_ACC_Y": "acc_y",
          "mov_ECGEMG_SD_ACC_Z": "acc_z", "mov_ECGEMG_SD_GYR_A": "gyr_x", "mov_ECGEMG_SD_GYR_B": "gyr_y",
          "mov_ECGEMG_SD_GYR_C": "gyr_z", "eeg_CROSStop_SD": "eeg2"}
BIO = ("eeg1", "eeg2", "ecg", "emg")
OPS = {"strict": (None, 10), "balanced": (2, 10), "sensitive": (-7, 10)}   # None = the frozen threshold

# id, recording, watched part starts at (s), ends at (s), seizure index or None, title, story
SEGMENTS = [
    ("seizure_all_sensors", "sub-098_run-03", 70069 - 90, 70177 + 150, 0, "Patient 1: seizure, all sensors",
     "Behind-the-ear EEG, ECG, EMG and a 3-axis accelerometer. A 108-second seizure; the alarm is raised at every "
     "operating point, including the strict one frozen in the chip."),
    ("seizure_sensitive", "sub-099_run-01", 50766 - 90, 50903 + 150, 0, "Patient 2: seizure, needs the sensitive setting",
     "All sensors including the gyroscope. The strict setting stays silent; Balanced and Sensitive raise the alarm. "
     "Switch the operating point live to see the difference."),
    ("seizure_eeg_only", "sub-099_run-02", 4616 - 90, 4694 + 150, 0, "Patient 2: seizure, EEG only",
     "Only the two behind-the-ear EEG channels were recorded (the other sensors are missing). Detected at the "
     "Sensitive setting."),
    ("seizure_long", "sub-100_run-03", 2628 - 90, 2800 + 120, 0, "Patient 3: long seizure",
     "All sensors. A 172-second seizure, detected at the Sensitive setting about a minute after the annotated onset."),
    ("normal_moving", "sub-099_run-01", 34150 - 90, 34150 + 300, None, "Patient 2: normal activity, moving",
     "Six and a half minutes without a seizure while the patient moves about (accelerometer activity above the "
     "recording's median). No alarm at any setting."),
]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--export", default=str(REPO / "export/n4_distill_s0"))
    ap.add_argument("--pre", type=int, default=600, help="seconds of signal before the watched part (warm-up)")
    args = ap.parse_args()
    import frontend as fe
    from seizelut_model import SeizeLUTModel

    vd = Path(args.export) / "vectors"
    man = json.loads((vd / "manifest.json").read_text())
    spec = man["feature_names"]
    model = SeizeLUTModel(KIT / "board" / "model")
    names = [f["name"] for f in model.thresholds["features"]]
    col = [spec.index(n) for n in names]
    frozen = int(model.head["decision_threshold"])
    out = KIT / "demo" / "segments"
    out.mkdir(parents=True, exist_ok=True)
    index = {"source": "exported test vectors of the final model (held-out test patients)",
             "operating_points": {k: {"threshold": frozen if t is None else t, "k": kk} for k, (t, kk) in OPS.items()},
             "segments": []}
    for sid, rec, show_s, end_s, sz_i, title, story in SEGMENTS:
        raw = {}
        for p in sorted((vd / rec / "inputs").glob("*.i16")):
            key = "eeg1" if p.stem.startswith("eeg_BTE") else KEYMAP.get(p.stem)
            if key:
                raw[key] = np.fromfile(p, dtype=np.int16)
        t0 = show_s - args.pre
        n_rec = min(len(v) // (256 if k in BIO else 25) for k, v in raw.items())
        t1 = min(end_s, n_rec)
        assert t0 >= 0, sid
        seg = {k: v[t0 * (256 if k in BIO else 25): t1 * (256 if k in BIO else 25)].copy() for k, v in raw.items()}
        seizures = [list(map(float, s)) for s in man["recordings"][rec]["seizures_s"]]
        sz_seg = [[on - t0, off - t0] for on, off in seizures if off > t0 and on < t1]
        # what the demo will show: streaming front end from the segment's first sample, software classifier
        st = fe.Stream()
        feats, arts = [], []
        for b in range(t1 - t0):
            blk = {k: v[b * (256 if k in BIO else 25): (b + 1) * (256 if k in BIO else 25)] for k, v in seg.items()}
            w, X, art, _ = st.push(blk)
            if w is not None:
                feats.append(X[col]); arts.append(art)
        w, X, art = st.flush()
        if w is not None:
            feats.append(X[col]); arts.append(art)
        F = np.array(feats, dtype=np.int64)
        score = model.score(F)
        gold = np.load(KIT / "board" / "vectors" / f"{rec}.npz")["score"].astype(np.int64)[t0: t0 + len(F)]
        show = args.pre
        expected = {}
        for op, (thr, k) in OPS.items():
            thr = frozen if thr is None else thr
            res = model.run(F, threshold=thr, k=k)
            dec_g = (gold >= thr).astype(np.int64)
            c = np.concatenate(([0], np.cumsum(dec_g)))
            t = np.arange(1, len(dec_g) + 1)
            alarm_g = (c[t] - c[np.maximum(0, t - 10)]) >= k
            a = res["alarm"].astype(bool)
            idx = np.where(a[show:])[0]
            idx_g = np.where(alarm_g[show:])[0]
            first = int(idx[0] + show + 2) if len(idx) else None          # window t ends at segment second t + 2
            first_g = int(idx_g[0] + show + 2) if len(idx_g) else None
            e = {"threshold": thr, "k": k, "alarm_windows": int(a[show:].sum()),
                 "first_alarm_s": first, "full_recording_first_alarm_s": first_g,
                 "full_recording_alarm_windows": int(alarm_g[show:].sum())}
            if sz_seg and first is not None:
                e["after_onset_s"] = first - sz_seg[0][0]
            expected[op] = e
        np.savez_compressed(out / f"{sid}.npz", **seg)
        sensors = sorted(seg)
        index["segments"].append({
            "id": sid, "title": title, "story": story, "recording": rec, "record_start_s": t0,
            "seconds": t1 - t0, "watch_from_s": show, "seizures_s": sz_seg, "sensors": sensors,
            "seizure_duration_s": (sz_seg[0][1] - sz_seg[0][0]) if sz_seg else None,
            "expected": expected, "score_diff_vs_full_recording": int((score[show:] != gold[show:]).sum()),
            "windows_watched": int(len(F) - show)})
        print(sid, rec, t0, t1, sensors, {k: (v["first_alarm_s"], v["full_recording_first_alarm_s"])
                                           for k, v in expected.items()})
    (out / "index.json").write_text(json.dumps(index, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
