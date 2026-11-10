#!/usr/bin/env python3
"""SeizeLUT on the Kria KV260: complete hardware test campaign. Run on the board as root in the PYNQ environment:

    sudo -i
    source /etc/profile.d/pynq_venv.sh
    cd /home/ubuntu/seizelut && python3 run_tests.py

Steps (each reported as PASS/FAIL, all numbers saved to results/kv260_results_<time>.json):
  1 overlay load, core identity (ID/INFO), register read/write test
  2 built-in self-test: 1,024 golden vectors from on-chip memory at one window per clock, checked in hardware
  3 latency: clock cycles from COMMIT to RESULT
  4 replay of the 10 test recordings (431,960 one-second windows) through the AXI registers; every score,
    decision and alarm compared with the software model (bit-exact) and with the golden vectors
  5 seizure-detection metrics computed from the FPGA's own alarms (the dataset paper's definitions)
  6 power of the SOM (INA260 monitor): overlay idle versus the classifier running continuously (BIST loop)
  7 end to end from raw samples: the integer front end in C on the ARM (all 117 features, compared with the golden
    model) feeding the classifier in the fabric; time per hour of signal
Options: --quick (3 short recordings), --backend emu (no board: emulated registers), --no-power, --power-seconds N,
         --no-e2e
"""
from __future__ import annotations

import argparse
import datetime as dt
import glob
import json
import os
import platform
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from seizelut_kv260 import SeizeLUT  # noqa: E402
from seizelut_model import SeizeLUTModel  # noqa: E402

QUICK = ["sub-097_run-10", "sub-100_run-03", "sub-099_run-02"]


# ---------------------------------------------------------------------------------------- metrics
def _events(m: np.ndarray):
    """Event ranges [start, end) as the dataset paper's mask2eventList builds them (fs = 1), with its edge case."""
    m = m.astype(bool)
    d = np.diff(m.astype(np.int8))
    st = np.where(d == 1)[0] + 1
    en = np.where(d == -1)[0] + 1
    if len(st) == 0 and m[0]:
        return np.array([0]), np.array([len(m) - 1])
    if m[0]:
        st = np.concatenate([[0], st])
    if m[-1]:
        en = np.concatenate([en, [len(m)]])
    return st, en


def _covered(st, en, n):
    d = np.zeros(n + 1, dtype=np.int64)
    np.add.at(d, st, 1)
    np.add.at(d, en, -1)
    return np.concatenate([[0], np.cumsum(np.cumsum(d[:n]) > 0)])


def paper_counts(y: np.ndarray, alarm: np.ndarray):
    """(tp, fp, fn) with any-overlap scoring as in the dataset paper's released code (with its TP fix)."""
    e = np.array([], dtype=np.int64)
    ts, te = _events(y) if y.any() else (e, e)
    ps, pe = _events(alarm) if alarm.any() else (e, e)
    n = len(y)
    cy, ca = _covered(ts, te, n), _covered(ps, pe, n)
    tp = int(np.sum((ca[te] - ca[ts]) > 0)) if len(ts) else 0
    fp = int(np.sum((cy[pe] - cy[ps]) == 0)) if len(ps) else 0
    return tp, fp, len(ts) - tp


# ---------------------------------------------------------------------------------------- power
def find_power_sensor():
    """hwmon device of the SOM power monitor (INA260 on the K26); returns (name, path to power input) or None."""
    cands = []
    for d in sorted(glob.glob("/sys/class/hwmon/hwmon*")):
        try:
            name = Path(d, "name").read_text().strip()
        except OSError:
            continue
        for f in ("power1_input", "power2_input"):
            if Path(d, f).exists():
                cands.append((name, str(Path(d, f))))
    for name, p in cands:
        if "ina260" in name.lower():
            return name, p
    return cands[0] if cands else None


def sample_power(path: str, seconds: float, hz: float = 10.0) -> dict:
    vals = []
    t_end = time.time() + seconds
    while time.time() < t_end:
        try:
            vals.append(int(Path(path).read_text()) / 1e6)   # microwatts -> watts
        except (OSError, ValueError):
            pass
        time.sleep(1.0 / hz)
    a = np.array(vals)
    return {"n": int(len(a)), "mean_w": float(a.mean()) if len(a) else None,
            "std_w": float(a.std(ddof=1)) if len(a) > 1 else None}


# ---------------------------------------------------------------------------------------- campaign
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--backend", default="pynq", choices=["pynq", "devmem", "emu"])
    ap.add_argument("--bit", default=str(HERE / "seizelut.bit"))
    ap.add_argument("--base", type=lambda s: int(s, 0), default=None, help="register base for --backend devmem")
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--recordings", nargs="*")
    ap.add_argument("--no-power", action="store_true")
    ap.add_argument("--power-seconds", type=float, default=20.0)
    ap.add_argument("--python-path", action="store_true", help="do not use the compiled C streaming helper")
    ap.add_argument("--op2-threshold", type=int, default=2,
                    help="programmable operating point: decision threshold (2 = the final model's <= 1 FA/h point, "
                         "chosen on the training patients)")
    ap.add_argument("--op2-k", type=int, default=10, help="programmable operating point: k of the last 10 decisions")
    ap.add_argument("--no-e2e", action="store_true", help="skip the end-to-end test from raw samples")
    args = ap.parse_args()

    out = {"started": dt.datetime.now().isoformat(timespec="seconds"), "backend": args.backend,
           "host": platform.node(), "python": platform.python_version(), "steps": {}}
    ok_all = True

    def step(name, passed, **info):
        nonlocal ok_all
        ok_all &= bool(passed)
        out["steps"][name] = {"pass": bool(passed), **info}
        print(f"[{'PASS' if passed else 'FAIL'}] {name}: " + ", ".join(f"{k}={v}" for k, v in info.items()
                                                                       if not isinstance(v, (list, dict))))

    # 1 load and identity
    t0 = time.time()
    core = SeizeLUT(args.backend, bitfile=args.bit, base=args.base)
    idt = core.identify()
    step("1_identity", idt["id_ok"] and idt["info_ok"], load_s=round(time.time() - t0, 2),
         base=None if core.base is None else hex(core.base), **idt)
    step("1_register_rw", core.scratch_test())

    # 2 BIST
    b = core.bist()
    step("2_bist", b["pass"], **b, clock_mhz=100.0,
         windows_per_second_at_100mhz=None if not b.get("windows_per_cycle") else round(b["windows_per_cycle"] * 1e8))

    # 3 latency (one real window)
    vec_dir = HERE / "vectors"
    index = json.loads((vec_dir / "index.json").read_text())
    recs = args.recordings or (QUICK if args.quick else sorted(index["recordings"]))
    first = np.load(vec_dir / f"{recs[0]}.npz")
    core.soft_reset()
    core.classify(first["feats"][0], int(first["art"][0, 0] | (first["art"][0, 1] << 1)))
    lat = core.read("LATENCY")
    step("3_latency", lat == core.cfg["latency_cycles"], cycles=lat, ns_at_100mhz=lat * 10)

    # 4 replay, 5 metrics (frozen operating point and the programmable one, in the same pass)
    model = SeizeLUTModel(HERE / "model")
    core.set_operating_point(args.op2_threshold, args.op2_k)
    out["operating_points"] = {"frozen": {"threshold": core.cfg["decision_threshold"], "k": core.cfg["k"]},
                               "programmable": {"threshold": args.op2_threshold, "k": args.op2_k}}
    per = {}
    n_tot = n_bad = n_bad_sw = n_bad2 = 0
    t_hw = t_sw = 0.0
    for rec in recs:
        z = np.load(vec_dir / f"{rec}.npz")
        feats, art = z["feats"], z["art"]
        hw = core.run_recording(feats, art, use_fast=not args.python_path)
        ts = time.perf_counter()
        sw = model.run(feats, art)
        t_sw += time.perf_counter() - ts
        sw2 = model.run(feats, art, threshold=args.op2_threshold, k=args.op2_k)
        bad2 = int(np.sum((hw["decision2"] != sw2["decision"]) | (hw["alarm2"] != sw2["alarm"])))
        n_bad2 += bad2
        t_hw += hw["seconds"]
        exact_golden = bool((hw["score"] == z["score"]).all() and (hw["decision"] == z["decision"]).all()
                            and (hw["alarm"] == z["alarm"]).all())
        bad = int(np.sum((hw["score"] != z["score"]) | (hw["decision"] != z["decision"]) | (hw["alarm"] != z["alarm"])))
        bad_sw = int(np.sum((hw["score"] != sw["score"]) | (hw["decision"] != sw["decision"])
                            | (hw["alarm"] != sw["alarm"])))
        n_tot += len(feats)
        n_bad += bad
        n_bad_sw += bad_sw
        tp, fp, fn = paper_counts(z["y"].astype(np.int64), hw["alarm"])
        tp2, fp2, fn2 = paper_counts(z["y"].astype(np.int64), hw["alarm2"])
        c = hw["counters"]
        per[rec] = {"windows": int(len(feats)), "hours": len(feats) / 3600.0, "mismatch_vs_golden": bad,
                    "mismatch_vs_software": bad_sw, "bit_exact": exact_golden, "seizures": int(len(z["seizures"])),
                    "tp": tp, "fp": fp, "fn": fn, "alarm_windows": int(hw["alarm"].sum()),
                    "op2_mismatch_vs_software": bad2, "op2_tp": tp2, "op2_fp": fp2, "op2_fn": fn2,
                    "counters_ok": c["nwin"] == len(feats) and c["nalarm"] == int(hw["alarm"].sum())
                    and c["ndec"] == int(hw["decision"].sum()) and c["ndec2"] == int(hw["decision2"].sum())
                    and c["nalarm2"] == int(hw["alarm2"].sum()),
                    "seconds": round(hw["seconds"], 3), "worst_window_ms": round(1e3 * hw["worst_window_s"], 3),
                    "method": hw["method"]}
        print(f"    {rec}: {len(feats)} windows, mismatches {bad}+{bad2}, frozen: {tp}/{tp + fn} seizures, "
              f"{fp} false alarms; programmable: {tp2}/{tp2 + fn2}, {fp2}; {hw['seconds']:.2f} s ({hw['method']})")
    step("4_replay_bit_exact", n_bad == 0 and n_bad_sw == 0 and n_bad2 == 0
         and all(p["counters_ok"] for p in per.values()),
         windows=n_tot, mismatches_vs_golden=n_bad, mismatches_vs_software=n_bad_sw,
         programmable_path_mismatches=n_bad2,
         hw_seconds=round(t_hw, 2), hw_us_per_window=round(1e6 * t_hw / max(1, n_tot), 2),
         sw_model_us_per_window=round(1e6 * t_sw / max(1, n_tot), 2), recordings=per)
    def metrics(pre):
        with_sz = [p for p in per.values() if p[pre + "tp"] + p[pre + "fn"] > 0]
        sens = float(np.mean([p[pre + "tp"] / (p[pre + "tp"] + p[pre + "fn"]) for p in with_sz])) if with_sz else None
        return {"seizures": int(sum(p[pre + "tp"] + p[pre + "fn"] for p in per.values())),
                "detected": int(sum(p[pre + "tp"] for p in per.values())),
                "false_alarms": int(sum(p[pre + "fp"] for p in per.values())),
                "sensitivity_mean_over_recordings": None if sens is None else round(sens, 4),
                "false_alarms_per_hour_mean_over_recordings": round(float(np.mean([p[pre + "fp"] / p["hours"]
                                                                                    for p in per.values()])), 4)}
    step("5_detection_metrics", True, recordings=len(per), hours=round(sum(p["hours"] for p in per.values()), 2),
         frozen_operating_point=metrics(""), programmable_operating_point=metrics("op2_"))
    for name, m in (("frozen", out["steps"]["5_detection_metrics"]["frozen_operating_point"]),
                    ("programmable", out["steps"]["5_detection_metrics"]["programmable_operating_point"])):
        print(f"    {name} operating point: {m['detected']}/{m['seizures']} seizures, {m['false_alarms']} false alarms")

    # 6 power
    if not args.no_power and args.backend != "emu":
        sensor = find_power_sensor()
        if sensor is None:
            step("6_power", False, error="no hwmon power sensor found (try: xmutil platformstats -p)")
        else:
            idle = sample_power(sensor[1], args.power_seconds)
            core.bist_loop(True)
            time.sleep(0.5)
            busy = sample_power(sensor[1], args.power_seconds)
            core.bist_loop(False)
            time.sleep(0.2)
            runs = core.read("BIST_RUNS")
            errs = core.read("BIST_ERR")
            delta = None if busy["mean_w"] is None or idle["mean_w"] is None else busy["mean_w"] - idle["mean_w"]
            step("6_power", True, sensor=sensor[0], idle_w=idle["mean_w"], idle_std_w=idle["std_w"],
                 classifier_running_w=busy["mean_w"], running_std_w=busy["std_w"], delta_w=delta,
                 bist_passes_during_measurement=runs, bist_errors_during_measurement=errs,
                 note="running = classifier + self-test streaming one window per clock (100 MHz), "
                      "an upper bound on the activity of real-time use (one window per second)")
    # 7 end to end: raw samples -> C front end (ARM) -> classifier (fabric)
    if not args.no_e2e:
        try:
            sys.path.insert(0, str(HERE / "frontend"))
            from frontend import extract
            spec_idx = [f["spec_index"] for f in core.cfg["features"]]
            e2e, ok7 = {}, True
            for p in sorted((HERE / "raw").glob("*.npz")):
                rec = p.stem
                z = np.load(p)
                raw = {k: z[k] for k in z.files if k not in ("golden_features", "golden_art", "n_win")}
                n_win = int(z["n_win"])
                t0 = time.perf_counter()
                X, art = extract(raw, n_win)
                t_fe = time.perf_counter() - t0
                feat_bad = int((X.astype(np.int16) != z["golden_features"]).sum() + (art != z["golden_art"]).sum())
                hw = core.run_recording(X[:, spec_idx].astype(np.int16), art, use_fast=not args.python_path)
                v = np.load(vec_dir / f"{rec}.npz")
                out_bad = int(np.sum((hw["score"] != v["score"]) | (hw["decision"] != v["decision"])
                                     | (hw["alarm"] != v["alarm"])))
                tp, fp, fn = paper_counts(v["y"].astype(np.int64), hw["alarm"])
                ok7 &= feat_bad == 0 and out_bad == 0
                e2e[rec] = {"windows": n_win, "sensors": sorted(raw), "feature_mismatches": feat_bad,
                            "output_mismatches": out_bad, "frontend_arm_s": round(t_fe, 3),
                            "frontend_realtime_factor": round(n_win / t_fe, 1) if t_fe > 0 else None,
                            "classifier_fabric_s": round(hw["seconds"], 3), "tp": tp, "fp": fp, "fn": fn}
                print(f"    {rec}: {n_win} windows from {len(raw)} raw signals, feature mismatches {feat_bad}, "
                      f"output mismatches {out_bad}, front end {t_fe:.2f} s ({n_win / max(t_fe, 1e-9):.0f}x real time)")
            step("7_end_to_end_raw", ok7, recordings=e2e)
        except Exception as e:   # report, do not hide, a failure of the optional end-to-end step
            step("7_end_to_end_raw", False, error=f"{type(e).__name__}: {e}")
    out["finished"] = dt.datetime.now().isoformat(timespec="seconds")
    out["all_pass"] = bool(ok_all)
    res_dir = HERE / "results"
    res_dir.mkdir(exist_ok=True)
    p = res_dir / f"kv260_results_{dt.datetime.now().strftime('%Y%m%d-%H%M%S')}_{args.backend}.json"
    p.write_text(json.dumps(out, indent=1, default=float))
    print(f"\n{'ALL TESTS PASSED' if ok_all else 'SOME TESTS FAILED'}; results: {p}")
    return 0 if ok_all else 1


if __name__ == "__main__":
    raise SystemExit(main())
