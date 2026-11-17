#!/usr/bin/env python3
"""N10: the front end in the fabric. Builds the feature-engine program (src/hw/fe_engine.py), writes its ROM/RAM
images for hw/kv260/rtl/fe_engine.v, and checks it instruction by instruction (C simulator hw/kv260/sim/fe_isa_sim.c)
against the C front end (hw/kv260/board/frontend, itself bit-exact with the golden model) on the exported
recordings: all 38 classifier features of every window must be equal.
Usage: python scripts/verify_fe_engine.py [--quick] [--tb]
  --tb  also writes testbench files for the RTL (hw/kv260/sim/fe_vectors/<rec>.*) for the bundled short recordings
Output: hw/kv260/results/fe_engine_isa_verification.json
"""
from __future__ import annotations

import argparse
import ctypes
import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "hw/kv260/board/frontend"))
VD = REPO / "export/n4_distill_s0/vectors"
KEYMAP = {"ecg_ECG_SD": "ecg", "emg_EMG_SD": "emg", "mov_ECGEMG_SD_ACC_X": "acc_x", "mov_ECGEMG_SD_ACC_Y": "acc_y",
          "mov_ECGEMG_SD_ACC_Z": "acc_z", "mov_ECGEMG_SD_GYR_A": "gyr_x", "mov_ECGEMG_SD_GYR_B": "gyr_y",
          "mov_ECGEMG_SD_GYR_C": "gyr_z", "eeg_CROSStop_SD": "eeg2"}
BIO = ("eeg1", "eeg2", "ecg", "emg")
IO = ("IN_EEG1", "IN_EEG2", "IN_ECG", "IN_EMG", "IN_AX", "IN_AY", "IN_AZ", "IN_GX", "IN_GY", "IN_GZ", "PRES_ECG",
      "PRES_EMG", "PRES_ACC", "PRES_GYR", "WIN_VALID", "WIN_INDEX", "FEAT_0")


def load_raw(rec):
    raw = {}
    for p in sorted((VD / rec / "inputs").glob("*.i16")):
        k = "eeg1" if p.stem.startswith("eeg_BTE") else KEYMAP.get(p.stem)
        if k:
            raw[k] = np.fromfile(p, dtype=np.int16)
    return raw


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--tb", action="store_true")
    args = ap.parse_args()
    from seizelut.hw.fe_engine import build, write_images
    import frontend as fe
    th = json.loads((REPO / "hw/kv260/board/model/thresholds.json").read_text())
    order = [f["name"] for f in th["features"]]
    spec_idx = [f["spec_index"] for f in th["features"]]
    prog = build(order)
    write_images(prog, REPO / "hw/kv260/rtl/fe")
    so = REPO / "hw/kv260/build/libfe_isa.so"
    so.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["gcc", "-O2", "-shared", "-fPIC", "-o", str(so), str(REPO / "hw/kv260/sim/fe_isa_sim.c")], check=True)
    lib = ctypes.CDLL(str(so))
    P = ctypes.c_void_p
    lib.fe_new.restype = P
    lib.fe_new.argtypes = [P, ctypes.c_int, P, ctypes.c_int]
    lib.fe_run_recording.restype = ctypes.c_int
    lib.fe_run_recording.argtypes = [P, P, P, ctypes.c_int, ctypes.c_int] + [P] * 10 + [P, ctypes.c_int, P]
    lib.fe_instr.restype = ctypes.c_uint64
    lib.fe_instr.argtypes = [P]
    lib.fe_maxabs.restype = ctypes.c_int64
    lib.fe_maxabs.argtypes = [P]
    lib.fe_bad_op.argtypes = [P]
    rom = np.array(prog["rom"], dtype=np.uint32)
    ram = np.array(prog["ram"], dtype=np.int64)
    io = np.array([prog["regs"][n] for n in IO], dtype=np.int32)
    entry = np.array([prog["entries"][e] for e in ("BIO", "MOV", "SEC", "FLUSH")], dtype=np.int32)
    man = json.loads((VD / "manifest.json").read_text())
    recs = sorted(man["recordings"])
    if args.quick:
        recs = ["sub-097_run-10", "sub-100_run-03"]
    out, tot_ev = {}, np.zeros(3, np.uint64)
    tot_sec, maxabs = 0, 0
    for rec in recs:
        raw = load_raw(rec)
        n_sec = min(len(v) // (256 if k in BIO else 25) for k, v in raw.items())
        n_win = man["recordings"][rec]["n_windows"]
        t0 = time.time()
        Xb, _ = fe.extract(raw, n_win)
        gold = Xb[:, spec_idx].astype(np.int16)
        arrs = {k: np.ascontiguousarray(v) for k, v in raw.items()}
        ptr = lambda k: arrs[k].ctypes.data if k in arrs else None
        h = lib.fe_new(rom.ctypes.data, len(rom), ram.ctypes.data, len(ram))
        res = np.zeros((n_win, len(order)), np.int16)
        ev = np.zeros(3, np.uint64)
        n_out = lib.fe_run_recording(h, io.ctypes.data, entry.ctypes.data, len(order), n_sec,
                                     *(ptr(k) for k in ("eeg1", "eeg2", "ecg", "emg", "acc_x", "acc_y", "acc_z",
                                                        "gyr_x", "gyr_y", "gyr_z")),
                                     res.ctypes.data, n_win, ev.ctypes.data)
        bad = np.nonzero((res[:n_out] != gold[:n_out]).any(1))[0]
        mx = lib.fe_maxabs(h)
        maxabs = max(maxabs, mx)
        tot_ev += ev
        tot_sec += n_sec
        cols = [order[c] for c in np.nonzero((res[:n_out] != gold[:n_out]).any(0))[0]][:6]
        out[rec] = {"seconds": n_sec, "windows": int(n_out), "windows_expected": n_win, "mismatch_windows": int(len(bad)),
                    "first_bad": int(bad[0]) if len(bad) else None, "bad_features": cols,
                    "max_abs_value": int(mx), "bad_ops": lib.fe_bad_op(h),
                    "instructions_per_second": round(float(ev.sum()) / max(1, n_sec)),
                    "seconds_sim": round(time.time() - t0, 1)}
        print(rec, out[rec], flush=True)
        if len(bad):
            w = bad[0]
            diff = np.nonzero(res[w] != gold[w])[0][:6]
            print("   window", w, [(order[c], int(res[w, c]), int(gold[w, c])) for c in diff])
        if args.tb and rec in ("sub-097_run-10", "sub-100_run-03"):
            tb = REPO / "hw/kv260/sim/fe_vectors"
            tb.mkdir(parents=True, exist_ok=True)
            # one line per second: 256 x 4 bio samples, then 25 x 6 motion samples (16-bit hex), absent = 0
            lines = []
            for b in range(n_sec):
                vals = []
                for i in range(256):
                    for k in BIO:
                        vals.append(int(arrs[k][b * 256 + i]) if k in arrs else 0)
                for i in range(25):
                    for k in ("acc_x", "acc_y", "acc_z", "gyr_x", "gyr_y", "gyr_z"):
                        vals.append(int(arrs[k][b * 25 + i]) if k in arrs else 0)
                lines.append("".join(f"{v & 0xFFFF:04x}" for v in reversed(vals)))
            (tb / f"{rec}.samples.hex").write_text("\n".join(lines) + "\n")
            (tb / f"{rec}.feats.hex").write_text("\n".join("".join(f"{int(v) & 0xFFFF:04x}" for v in reversed(row))
                                                           for row in gold[:n_out]) + "\n")
            pres = [int("ecg" in arrs), int("emg" in arrs), int("acc_x" in arrs), int("gyr_x" in arrs)]
            (tb / f"{rec}.json").write_text(json.dumps({"seconds": n_sec, "windows": int(n_out), "presence": pres}))
    secs = max(1, tot_sec)
    per_s = {"bio_event": round(float(tot_ev[0]) / (secs * 256), 1), "mov_event": round(float(tot_ev[1]) / (secs * 25), 1),
             "sec_event": round(float(tot_ev[2]) / secs, 1),
             "per_second_of_signal": round(float(tot_ev.sum()) / secs, 0)}
    summary = {"what": "feature-engine program (instruction-level C simulator) against the C front end, 38 classifier "
                       "features of every window", "recordings": len(recs), "windows": int(sum(r["windows"] for r in out.values())),
               "mismatch_windows": int(sum(r["mismatch_windows"] for r in out.values())),
               "rom_instructions": prog["n_rom"], "ram_registers": prog["n_ram"],
               "instructions_mean": per_s,
               "instructions_per_second_worst_recording": max(r["instructions_per_second"] for r in out.values()),
               "cycles_per_second_worst_recording": 3 * max(r["instructions_per_second"] for r in out.values()),
               "max_abs_value": int(maxabs),
               "bits_needed_signed": int(maxabs).bit_length() + 1, "datapath_bits": prog["dw"], "runs": out}
    summary["all_bit_exact"] = summary["mismatch_windows"] == 0 and all(r["windows"] == r["windows_expected"] for r in out.values())
    (REPO / "hw/kv260/results/fe_engine_isa_verification.json").write_text(json.dumps(summary, indent=1))
    print(json.dumps({k: v for k, v in summary.items() if k != "runs"}, indent=1))
    return 0 if summary["all_bit_exact"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
