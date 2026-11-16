#!/usr/bin/env python3
"""Driver and board self-test of the impairment emulator in the "ms1" kit (ms/fpga/vivado/build_ms1.tcl).

Backends:
  pynq    load ms/fpga/out/ms1.bit (+ .hwh) with PYNQ and use the ms_impair_axi registers (the board)
  devmem  the bitstream is already loaded; map the registers from /dev/mem at --base
  emu     no hardware: the register protocol in Python, outputs taken from the vectors (tests this script only;
          it cannot test the arithmetic)

Self-test: every case of vectors/impair_cases.npz (made by ms/fpga/make_board_files.py from the golden model) is
configured, its 70,000 input samples are streamed through the fabric, and every output word and the clip count are
compared with the golden model; then a negative control (one seed bit flipped) must report mismatches.

Usage (on the board, from ms/fpga/board):  sudo python3 ms_impair_kv260.py selftest [--backend pynq]
Output: results/selftest_<UTC time>.json
Register map: header of ms/fpga/rtl/ms_impair_axi.v.
"""
from __future__ import annotations

import argparse
import json
import mmap
import os
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
INFO, CTRL, STATUS, CLIPS, DATA_IN, DATA_OUT, N_OUT, DROPS, CFG = 0x00, 0x04, 0x08, 0x0C, 0x10, 0x18, 0x1C, 0x20, 0x100
INFO_WORD = 0x4D530100
MAX_OUTSTANDING = 400          # below the 512-entry FIFOs, as in the Verilator testbench


class MemBackend:
    def __init__(self, base: int, size: int = 0x1000):
        fd = os.open("/dev/mem", os.O_RDWR | os.O_SYNC)
        try:
            self.mm = mmap.mmap(fd, size, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE, offset=int(base))
        finally:
            os.close(fd)
        self.arr = np.frombuffer(self.mm, dtype=np.uint32)

    def read(self, off: int) -> int:
        return int(self.arr[off >> 2])

    def write(self, off: int, v: int) -> None:
        self.arr[off >> 2] = np.uint32(v & 0xFFFFFFFF)


class PynqBackend(MemBackend):
    def __init__(self, bitfile: Path):
        from pynq import Overlay
        self.overlay = Overlay(str(bitfile))
        keys = [k for k in self.overlay.ip_dict if "ms_impair" in k.lower()]
        if not keys:
            raise RuntimeError(f"no ms_impair IP in the overlay; IPs: {list(self.overlay.ip_dict)}")
        ip = self.overlay.ip_dict[keys[0]]
        super().__init__(ip["phys_addr"], ip["addr_range"])


class EmuBackend:
    """Register protocol only (FIFOs, counters, start); output k of a run = golden output k of the case whose
    configuration was loaded, or the input unchanged if the configuration matches no case."""

    def __init__(self, vec):
        self.vec = vec
        self.cfg = np.zeros(80, np.uint32)
        self._start()

    def _start(self):
        self.fin, self.fout, self.n, self.drops, self.case = [], [], 0, 0, None
        for i in range(len(self.vec["names"])):
            if np.array_equal(self.vec["cfg"][i], self.cfg):
                self.case = i

    def write(self, off, v):
        if CFG <= off < CFG + 320:
            self.cfg[(off - CFG) >> 2] = v
        elif off == CTRL and v & 1:
            self._start()
        elif off == DATA_IN:
            if len(self.fin) + len(self.fout) >= 512:
                self.drops += 1
                return
            x = np.int16(np.uint16(v & 0xFFFF))
            y = x if self.case is None else self.vec["y"][self.case][self.n]
            self.fout.append(int(y) & 0xFFFF)
            self.n += 1

    def read(self, off):
        if off == INFO:
            return INFO_WORD
        if off == STATUS:
            return (len(self.fout) << 16) | (int(bool(self.fout)) << 1) | 1
        if off == CLIPS:
            return int(self.vec["clipped"][self.case]) if self.case is not None else 0
        if off == DATA_OUT:
            return (1 << 16) | self.fout.pop(0) if self.fout else 0
        if off == N_OUT:
            return self.n
        if off == DROPS:
            return self.drops
        return 0


class MsImpair:
    def __init__(self, backend):
        self.b = backend
        info = self.b.read(INFO)
        if info != INFO_WORD:
            raise RuntimeError(f"INFO register {info:#010x}, expected {INFO_WORD:#010x}: wrong bitstream or address")

    def configure(self, words) -> None:
        """Load the 80 configuration words (ms/py/impair_rtl.py config_words) and start a run."""
        for i, w in enumerate(words):
            self.b.write(CFG + 4 * i, int(w))
        self.b.write(CTRL, 1)

    def stream(self, x: np.ndarray) -> tuple[np.ndarray, int, int]:
        """Impair one channel: returns (output samples, clip count, dropped inputs)."""
        n = len(x)
        y = np.empty(n, np.int16)
        xs = (x.astype(np.int64) & 0xFFFF).tolist()
        wr = rd = 0
        while rd < n:
            while wr < n and wr - rd < MAX_OUTSTANDING:
                self.b.write(DATA_IN, xs[wr]); wr += 1
            lev = (self.b.read(STATUS) >> 16) & 0x3FF
            if lev == 0:
                continue
            for _ in range(min(lev, n - rd)):
                d = self.b.read(DATA_OUT)
                if not d >> 16 & 1:
                    raise RuntimeError("output FIFO empty although STATUS said otherwise")
                v = d & 0xFFFF
                y[rd] = v - 0x10000 if v & 0x8000 else v
                rd += 1
        if self.b.read(N_OUT) != n:
            raise RuntimeError(f"N_OUT {self.b.read(N_OUT)} != {n}")
        return y, self.b.read(CLIPS), self.b.read(DROPS)


def selftest(dev: MsImpair, vec, emu: bool) -> dict:
    res = []
    for i, name in enumerate(vec["names"]):
        t0 = time.time()
        dev.configure(vec["cfg"][i])
        y, clips, drops = dev.stream(vec["x"])
        bad = int(np.sum(y != vec["y"][i]))
        res.append({"case": str(name), "samples": len(y), "mismatches": bad, "clipped_board": int(clips),
                    "clipped_model": int(vec["clipped"][i]), "drops": int(drops), "seconds": round(time.time() - t0, 2)})
        print(res[-1], flush=True)
    neg_cfg = vec["cfg"][list(vec["names"]).index("white_1uV")].copy()
    neg_cfg[2] ^= 1                                          # one bit of the white-noise seed (word 2)
    dev.configure(neg_cfg)
    y, _, _ = dev.stream(vec["x"])
    neg = int(np.sum(y != vec["y"][list(vec["names"]).index("white_1uV")]))
    print({"case": "NEGATIVE_CONTROL_white_seed_bit_flipped", "mismatches": neg}, flush=True)
    ok = all(r["mismatches"] == 0 and r["clipped_board"] == r["clipped_model"] and r["drops"] == 0 for r in res)
    ok_neg = neg > 0 or emu                       # the emulator cannot compute, so its control is meaningless
    return {"all_bit_exact": bool(ok), "negative_control_mismatches": neg, "negative_control_ok": bool(ok_neg),
            "backend_is_emulator": emu, "cases": res}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["selftest", "info"])
    ap.add_argument("--backend", choices=["pynq", "devmem", "emu"], default="pynq")
    ap.add_argument("--bit", default=str(HERE.parent / "out/ms1.bit"))
    ap.add_argument("--base", type=lambda s: int(s, 0), default=None, help="register base address (devmem)")
    args = ap.parse_args()
    vec = dict(np.load(HERE / "vectors/impair_cases.npz"))
    if args.backend == "pynq":
        b = PynqBackend(Path(args.bit))
    elif args.backend == "devmem":
        if args.base is None:
            raise SystemExit("--base is required with devmem (see the address printed by build_ms1.tcl)")
        b = MemBackend(args.base)
    else:
        b = EmuBackend(vec)
    dev = MsImpair(b)
    if args.command == "info":
        print(f"INFO {dev.b.read(INFO):#010x}")
        return 0
    out = selftest(dev, vec, args.backend == "emu")
    out["backend"] = args.backend
    out["utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    d = HERE / "results"
    d.mkdir(exist_ok=True)
    p = d / f"selftest_{args.backend}_{time.strftime('%Y%m%d-%H%M%S', time.gmtime())}.json"
    p.write_text(json.dumps(out, indent=1) + "\n")
    print("ALL BIT-EXACT" if out["all_bit_exact"] and out["negative_control_ok"] else "MISMATCHES", "->", p)
    return 0 if out["all_bit_exact"] and out["negative_control_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
