#!/usr/bin/env python3
"""Bit-exact check of the RTL impairment emulator (ms/fpga/rtl/ms_impair.v) against its golden model (impair.py).

config_words() packs a compiled impairment into the RTL's 80 configuration words; the Verilator testbench
(ms/fpga/sim/tb_ms_impair.v) streams samples through the RTL; the outputs must equal impair.apply() word for word.

Usage: python ms/py/impair_rtl.py [--quick]  -> ms/results/phase1/impair_rtl_check.json
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "ms/py"))
import impair as IMP                       # noqa: E402
from seizelut.features.fixedpoint import csd  # noqa: E402

RTL = REPO / "ms/fpga/rtl/ms_impair.v"
TB = REPO / "ms/fpga/sim/tb_ms_impair.v"
AXI_RTL = REPO / "ms/fpga/rtl/ms_impair_axi.v"
AXI_TB = REPO / "ms/fpga/sim/tb_ms_impair_axi.v"
W_Q, W_OFF, W_SEEDW, W_DK, W_NM, W_PH, W_INC, W_TERMS, W_FLAGS = 0, 1, 2, 14, 15, 16, 23, 30, 72
P_WHITE, P_PINK, P_DRIFT, P_GAIN, P_MAINS, P_HP, P_LP = 0, 1, 2, 3, 4, 11, 16
M32 = 0xFFFFFFFF


def term_bytes(c: int) -> list[int]:
    """Signed-power-of-two digits of the integer constant c as RTL term bytes (valid, negative, shift)."""
    d = csd(int(c))
    if len(d) > 8:
        raise ValueError(f"constant {c} needs {len(d)} terms (> 8)")
    out = [0x80 | (0x40 if s < 0 else 0) | k for s, k in d]
    assert sum(s * (1 << k) for s, k in d) == c
    return out + [0] * (8 - len(out))


def config_words(c: IMP.Compiled, key: tuple[int, ...]) -> list[int]:
    w = [0] * 80
    w[W_Q] = c.q_shift | ((c.clip_code.bit_length() - 1) << 8)
    w[W_OFF] = c.offset_i & M32
    for i, kind in enumerate((1, 2, 3)):                      # streams: white, pink, drift (impair.apply)
        s0, s1 = IMP.stream_state(*key, kind)
        w[W_SEEDW + 4 * i: W_SEEDW + 4 * i + 4] = [s0 & M32, s0 >> 32, s1 & M32, s1 >> 32]
    w[W_DK] = c.drift_k
    w[W_NM] = len(c.mains_c)
    if c.mains_c:
        st = np.array(IMP.stream_state(*key, 4), dtype=np.uint64)
        ph = [int(v) >> 32 for v in IMP._raw(st, IMP.MAINS_HARMONICS)]
        for h in range(len(c.mains_c)):
            w[W_PH + h] = ph[h]
            w[W_INC + h] = c.mains_inc[h] & M32

    def put(pid, const):
        b = term_bytes(const)
        w[W_TERMS + 2 * pid] = b[0] | b[1] << 8 | b[2] << 16 | b[3] << 24
        w[W_TERMS + 2 * pid + 1] = b[4] | b[5] << 8 | b[6] << 16 | b[7] << 24

    put(P_WHITE, c.white_c); put(P_PINK, c.pink_c); put(P_DRIFT, c.drift_c); put(P_GAIN, c.gain_c)
    for h, m in enumerate(c.mains_c):
        put(P_MAINS + h, m)
    for base, sec in ((P_HP, c.hp), (P_LP, c.lp)):
        if sec is not None:
            assert sec[5] == IMP.AFE_F
            for j in range(5):
                put(base + j, sec[j])
    w[W_FLAGS] = ((c.hp is not None) | (c.lp is not None) << 1 | (c.white_c != 0) << 2 | (c.pink_c != 0) << 3
                  | (c.drift_c != 0) << 4 | (c.gain_c != 0) << 5)
    return w


CASES = {
    "identity": dict(),
    "q4_clip1024": dict(lsb=1.0, clip=256.0),
    "q2_clip64_clipping": dict(lsb=0.5, clip=64.0),
    "white_1uV": dict(white_density=0.1),
    "pink_10Hz": dict(white_density=0.1, pink_corner_hz=10.0),
    "drift_100uV": dict(drift_rms=100.0, drift_tau_s=16.0),
    "mains_h1_h5": dict(mains_peak=(100.0, 0.0, 30.0, 0.0, 10.0), aa_hz=100.0),
    "gain_-0.2": dict(gain_err=-0.2),
    "offset_hp": dict(offset=500.0, hp_hz=0.5),
    "lp_40": dict(lp_hz=40.0),
    "everything": dict(lsb=0.5, clip=2048.0, white_density=0.05, pink_corner_hz=3.0, drift_rms=20.0, gain_err=0.07,
                       offset=-200.0, mains_peak=(50.0, 0.0, 0.0, 0.0, 5.0), hp_hz=0.3, lp_hz=70.0),
}


def build(work: Path, axi: bool = False) -> Path:
    sin_hex = work / "sin4096.hex"
    sin_hex.write_text("\n".join(f"{int(v) & 0xFFFF:04x}" for v in IMP.SIN_TABLE) + "\n")
    top = "tb_ms_impair_axi" if axi else "tb_ms_impair"
    srcs = [RTL, AXI_RTL, AXI_TB] if axi else [RTL, TB]
    subprocess.run(["verilator", "--binary", "--timing", "-j", "4", "-Wno-fatal", "-Wno-lint", "-Wno-style",
                    "--top-module", top, f"-GSIN_HEX=\"{sin_hex}\"", *map(str, srcs),
                    "--Mdir", str(work / "obj")], check=True, capture_output=True, text=True)
    return work / "obj" / f"V{top}"


def run_case(exe: Path, work: Path, name: str, kw: dict, x: np.ndarray, key=(11, 22, 33), corrupt=None) -> dict:
    c = IMP.compile_impairment(IMP.Impairment(**kw), 256.0, 0.25)
    ref, st = IMP.apply(x, c, key)
    words = config_words(c, key)
    if corrupt is not None:                     # negative control: one wrong configuration word
        words[corrupt[0]] ^= corrupt[1]
    (work / "cfg.hex").write_text("\n".join(f"{v:08x}" for v in words) + "\n")
    (work / "in.hex").write_text("\n".join(f"{int(v) & 0xFFFF:04x}" for v in x) + "\n")
    t0 = time.time()
    r = subprocess.run([str(exe), f"+CFG={work / 'cfg.hex'}", f"+IN={work / 'in.hex'}", f"+OUT={work / 'out.txt'}",
                        f"+N={len(x)}"], capture_output=True, text=True, cwd=work)
    if r.returncode != 0:
        raise RuntimeError(r.stdout[-2000:] + r.stderr[-2000:])
    lines = (work / "out.txt").read_text().split()
    got = np.array([int(v) for v in lines[1:]], dtype=np.int64)
    clips = int(lines[0])
    n_bad = int(np.sum(got != ref.astype(np.int64))) if len(got) == len(ref) else -1
    first = int(np.flatnonzero(got != ref)[0]) if n_bad > 0 else None
    return {"case": name, "samples": len(x), "mismatches": n_bad, "first_mismatch": first,
            "samples_changed_by_impairment": int(np.sum(ref != x)),
            "clipped_rtl": clips, "clipped_model": st["clipped"], "rtl_seconds": round(time.time() - t0, 1)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--quick", action="store_true", help="5,000 samples per case")
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--axi", action="store_true", help="through the AXI4-Lite wrapper (ms_impair_axi.v), driven as "
                                                       "the ARM would -> impair_rtl_axi_check.json")
    args = ap.parse_args()
    if not shutil.which("verilator"):
        raise SystemExit("verilator not found")
    work = Path(tempfile.mkdtemp(prefix="ms_impair_"))
    exe = build(work, args.axi)
    rng = np.random.default_rng(5)
    n = 5_000 if args.quick else 70_000                         # 70,000 samples reach Voss row 15 (2^16 hold)
    x = np.clip(np.round(rng.normal(0, 40, n) + 400 * np.sin(2 * np.pi * 7 * np.arange(n) / 256)),
                -32768, 32767).astype(np.int16)
    res = [run_case(exe, work, k, v, x) for k, v in CASES.items()]
    # negative control: flip one bit of the white-noise seed; the check must report mismatches
    neg = run_case(exe, work, "NEGATIVE_CONTROL_white_seed_bit_flipped", CASES["white_1uV"], x, corrupt=(W_SEEDW, 1))
    for r in res + [neg]:
        print(r, flush=True)
    ok = all(r["mismatches"] == 0 and r["clipped_rtl"] == r["clipped_model"] for r in res) and neg["mismatches"] > 0
    res.append(neg)
    what = ("RTL impairment emulator behind its AXI4-Lite wrapper (ms/fpga/rtl/ms_impair_axi.v, bus transactions "
            "in Verilator)" if args.axi else "RTL impairment emulator (ms/fpga/rtl/ms_impair.v, Verilator)")
    out = {"what": what + " vs golden model (ms/py/impair.py)", "all_bit_exact": ok, "cases": res}
    if not args.quick:
        name = "impair_rtl_axi_check.json" if args.axi else "impair_rtl_check.json"
        (REPO / "ms/results/phase1" / name).write_text(json.dumps(out, indent=1) + "\n")
    print("ALL BIT-EXACT" if ok else "MISMATCHES FOUND")
    if not args.keep:
        shutil.rmtree(work, ignore_errors=True)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
