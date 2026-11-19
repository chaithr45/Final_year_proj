#!/usr/bin/env python3
"""Doctor alert (ESP32 notification): which measured signs can describe a seizure, checked on TRAINING patients only.

For every annotated seizure of the 96 training patients (sub-001..sub-096; the test patients are never read), the
signs the alert would show are computed from the cached integer features (the same features the board computes):
  heart rate   ecg_log_rr (log2 of the mean RR interval, 2^-3 steps) -> beats per minute, before vs during
  movement     mov_acc_mag, mov_acc_act (chest accelerometer)          -> ratio to before, share of time moving
  muscle       emg_mav (EMG > 20 Hz)                                    -> ratio to before
  brain        eeg_ll_mean (EEG line length), delta/theta/beta power    -> ratio to before, dominant band change
"before" = the 60 s ending 10 s before the annotated onset; "during" = the first 30 s from onset (an alert is early).
The motor / non-motor hint is a single threshold on the movement ratio, chosen on patients 1-48 (maximum balanced
accuracy) and reported on patients 49-96, against the annotation (eventType *_m* motor or f2b vs *_nm*).
Usage: python scripts/alert_signs_analysis.py      Output: results/tables/alert_signs.json
"""
from __future__ import annotations

import csv
import json
import re
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
FEAT = REPO / "cache/features/int"
RAW = REPO / "data/raw/ds005873"
I = {"eeg_ll_mean": 3, "eeg_delta_mean": 15, "eeg_theta_mean": 18, "eeg_beta_mean": 24, "ecg_log_rr": 53,
     "ecg_quality_bad": 55, "emg_mav": 56, "mov_acc_mag": 60, "mov_acc_act": 62}


def unlog(v: float) -> float:
    """Inverse of the front end's log2 (leading-one position + 3 mantissa bits, 2^-3 steps)."""
    lp, m = int(v) >> 3, int(v) & 7
    return (1 << lp) * (1 + m / 8.0)


def bpm(log_rr: np.ndarray) -> float:
    return float(np.median([60.0 * 256.0 / unlog(v) for v in log_rr]))


def motor_class(t: str) -> str | None:
    if t.startswith("sz_foc_f2b") or "_m_" in t + "_" and "_nm" not in t and "_um" not in t:
        return "motor"
    if "_nm" in t:
        return "nonmotor"
    return None                           # unknown motor status (_um, plain sz_foc_ia ...)


def main() -> int:
    rows = []
    for f in sorted(RAW.glob("sub-*/ses-01/eeg/*_events.tsv")):
        sub = int(re.search(r"sub-(\d+)", f.name).group(1))
        if sub > 96:                       # test patients: never read
            continue
        run = re.search(r"run-(\d+)", f.name).group(1)
        fz = FEAT / f"sub-{sub:03d}_run-{run}.npz"
        if not fz.exists():
            continue
        z = np.load(fz)
        X, pres = z["X"].astype(np.int64), z["present"]
        for r in csv.DictReader(open(f), delimiter="\t"):
            t = r["eventType"].strip()
            if t in ("bckg", "impd"):
                continue
            on, dur = float(r["onset"]), float(r["duration"])
            a, b = int(on) - 70, int(on) - 10            # before
            c, d = int(on), int(on) + int(min(30, max(dur, 4)))
            if a < 0 or d > len(X):
                continue
            row = {"sub": sub, "run": run, "type": t, "motor": motor_class(t), "duration_s": dur,
                   "lateralization": r["lateralization"].strip()}
            pre, dur_ = X[a:b], X[c:d]
            if pres[c:d, 0].all() and pres[a:b, 0].all():
                okp, okd = pre[:, I["ecg_quality_bad"]] == 0, dur_[:, I["ecg_quality_bad"]] == 0
                if okp.sum() >= 20 and okd.sum() >= 2:
                    row["hr_before"] = bpm(pre[okp, I["ecg_log_rr"]])
                    row["hr_during"] = bpm(dur_[okd, I["ecg_log_rr"]])
            if pres[c:d, 2].all() and pres[a:b, 2].all():
                row["mov_ratio"] = float(2 ** ((np.median(dur_[:, I["mov_acc_mag"]]) - np.median(pre[:, I["mov_acc_mag"]])) / 8))
                row["mov_active_frac"] = float(np.mean(dur_[:, I["mov_acc_act"]]) / 50.0)
            if pres[c:d, 1].all() and pres[a:b, 1].all():
                row["emg_ratio"] = float(2 ** ((np.median(dur_[:, I["emg_mav"]]) - np.median(pre[:, I["emg_mav"]])) / 8))
            row["eeg_ratio"] = float(2 ** ((np.median(dur_[:, I["eeg_ll_mean"]]) - np.median(pre[:, I["eeg_ll_mean"]])) / 8))
            band = {k: float(np.median(dur_[:, I[f"eeg_{k}_mean"]]) - np.median(pre[:, I[f"eeg_{k}_mean"]])) / 8
                    for k in ("delta", "theta", "beta")}
            row["eeg_band_rise_log2"] = band
            rows.append(row)

    def stats(vals):
        v = np.array([x for x in vals if x is not None], float)
        return None if not len(v) else {"n": int(len(v)), "median": round(float(np.median(v)), 3),
                                        "q25": round(float(np.percentile(v, 25)), 3),
                                        "q75": round(float(np.percentile(v, 75)), 3)}

    out = {"what": __doc__.split("\n")[0], "patients": "training only (sub-001..sub-096)", "seizures": len(rows),
           "by_motor_class": {}}
    for cls in ("motor", "nonmotor", None):
        g = [r for r in rows if r["motor"] == cls]
        out["by_motor_class"][str(cls)] = {
            "seizures": len(g),
            "hr_before": stats([r.get("hr_before") for r in g]), "hr_during": stats([r.get("hr_during") for r in g]),
            "hr_rise_pct": stats([100 * (r["hr_during"] / r["hr_before"] - 1) for r in g if "hr_during" in r]),
            "mov_ratio": stats([r.get("mov_ratio") for r in g]),
            "mov_active_frac": stats([r.get("mov_active_frac") for r in g]),
            "emg_ratio": stats([r.get("emg_ratio") for r in g]), "eeg_ratio": stats([r.get("eeg_ratio") for r in g])}

    # motor hint: threshold on the movement ratio, chosen on patients 1-48, reported on 49-96
    lab = [r for r in rows if r["motor"] in ("motor", "nonmotor") and "mov_ratio" in r]
    def bal_acc(rs, thr):
        tp = sum(1 for r in rs if r["motor"] == "motor" and r["mov_ratio"] >= thr)
        p = sum(1 for r in rs if r["motor"] == "motor")
        tn = sum(1 for r in rs if r["motor"] == "nonmotor" and r["mov_ratio"] < thr)
        n = sum(1 for r in rs if r["motor"] == "nonmotor")
        return (tp / p if p else 0, tn / n if n else 0, p, n)
    dev = [r for r in lab if r["sub"] <= 48]
    held = [r for r in lab if r["sub"] > 48]
    grid = sorted({round(2 ** (k / 8), 4) for k in range(0, 41)})
    best = max(grid, key=lambda th: sum(bal_acc(dev, th)[:2]))
    sd, sp, p, n = bal_acc(dev, best)
    sh, sph, ph, nh = bal_acc(held, best)
    out["motor_hint"] = {"rule": "movement ratio (during / before) >= threshold -> 'motor (movement)' else "
                                 "'non-motor (little movement)'",
                         "threshold_ratio": best, "chosen_on": "patients 1-48", "reported_on": "patients 49-96",
                         "dev": {"motor_seizures": p, "nonmotor_seizures": n, "motor_recall": round(sd, 3),
                                 "nonmotor_recall": round(sp, 3)},
                         "held_out": {"motor_seizures": ph, "nonmotor_seizures": nh, "motor_recall": round(sh, 3),
                                      "nonmotor_recall": round(sph, 3),
                                      "balanced_accuracy": round((sh + sph) / 2, 3)}}
    out["rows"] = rows
    (REPO / "results/tables/alert_signs.json").write_text(json.dumps(out, indent=1))
    print(json.dumps({k: v for k, v in out.items() if k != "rows"}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
