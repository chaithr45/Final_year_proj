"""Driver for the SeizeLUT core on the Kria KV260 (PYNQ), with a register emulator for testing without a board.

Backends:
  pynq    load out/seizelut.bit (+ .hwh) with PYNQ and access the core through its AXI4-Lite registers (the board)
  devmem  the bitstream is already loaded by other means; map the registers from /dev/mem at --base
  emu     no hardware: the same registers emulated in Python with the reference model (tests the scripts)

Register map: seizelut_regs.json (generated with the RTL by src/hw/kv260.py).
"""
from __future__ import annotations

import ctypes
import json
import mmap
import os
import subprocess
import time
from collections import deque
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent


def pack_words(feats: np.ndarray) -> np.ndarray:
    """(n, n_features) int16 -> (n, n_words) uint32, feature 2k in bits [15:0] and 2k+1 in bits [31:16]."""
    f = feats.astype(np.int64) & 0xFFFF
    if f.shape[1] % 2:
        f = np.concatenate([f, np.zeros((len(f), 1), np.int64)], axis=1)
    return (f[:, 0::2] | (f[:, 1::2] << 16)).astype(np.uint32)


def decode_result(r: int) -> tuple[int, int, int, int, int, int, int]:
    """RESULT word -> (score, decision, alarm, valid, seq, decision2, alarm2); 2 = programmable operating point."""
    s = r & 0xFF
    s = s - 256 if s & 0x80 else s
    return s, (r >> 8) & 1, (r >> 9) & 1, (r >> 15) & 1, (r >> 16) & 0xFFFF, (r >> 10) & 1, (r >> 11) & 1


# ---------------------------------------------------------------------------------------------- backends
class _MemBackend:
    """32-bit register access through an mmap of /dev/mem (works with any loader)."""

    def __init__(self, base: int, size: int = 0x1000):
        self.base, self.size = int(base), int(size)
        fd = os.open("/dev/mem", os.O_RDWR | os.O_SYNC)
        try:
            self.mm = mmap.mmap(fd, self.size, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE, offset=self.base)
        finally:
            os.close(fd)
        self.arr = np.frombuffer(self.mm, dtype=np.uint32)

    def read(self, off: int) -> int:
        return int(self.arr[off >> 2])

    def write(self, off: int, v: int) -> None:
        self.arr[off >> 2] = np.uint32(v & 0xFFFFFFFF)


class _PynqBackend(_MemBackend):
    def __init__(self, bitfile: str):
        from pynq import Overlay   # imported here so the emulator works without PYNQ
        t0 = time.time()
        self.overlay = Overlay(str(bitfile))
        self.download_s = time.time() - t0
        keys = [k for k in self.overlay.ip_dict if "seizelut" in k.lower()]
        if not keys:
            raise RuntimeError(f"no seizelut IP in the overlay; IPs: {list(self.overlay.ip_dict)}")
        ip = self.overlay.ip_dict[keys[0]]
        self.ip_name = keys[0]
        super().__init__(ip["phys_addr"], max(0x1000, int(ip.get("addr_range", 0x1000))))


class _EmuBackend:
    """Register-level emulator of seizelut_axi.v (software model, no timing)."""

    def __init__(self, cfg: dict, model):
        self.cfg, self.model, self.r = cfg, model, cfg["registers"]
        self.nw = cfg["n_feature_words"]
        self.feat = [0] * self.nw
        self.scratch = 0
        self.hist = deque(maxlen=cfg["n"])
        self.seq, self.valid, self.res = 0, 0, (0, 0, 0, 0, 0)
        self.nwin = self.ndec = self.nalarm = self.ndec2 = self.nalarm2 = 0
        self.op_thr, self.op_k = cfg["decision_threshold"], cfg["k"]
        self.hist2 = deque(maxlen=cfg["n"])
        self.bist_runs = self.bist_ok = 0
        self.cycles0 = time.perf_counter()
        # demo I/O and debug taps (same behaviour as the RTL; the button is pressed with press_button())
        self.io_ctrl, self.io_manual = 0b0101, 0
        self.bits = np.zeros(cfg.get("n_bits", 146), dtype=np.uint8)
        self.luts = np.zeros(cfg.get("n_last_luts", 50), dtype=np.uint8)
        self.res_seen, self.heartbeat = 0, 0
        self.btn_pressed, self.btn_count = 0, 0

    def press_button(self, down: bool = True) -> None:
        if down and not self.btn_pressed:
            self.btn_count = (self.btn_count + 1) & 0xFFFF
        self.btn_pressed = int(down)

    def _io_state(self) -> int:
        if not self.io_ctrl & 1:
            return self.io_manual & 0x7F
        s, d, a, d2, a2 = self.res
        prog = self.io_ctrl & 2
        thr = self.op_thr if prog else self.cfg["decision_threshold"]
        dec, alarm = (d2, a2) if prog else (d, a)
        buzz = alarm & (self.io_ctrl >> 2) & ((self.read(self.r["CYCLES"]) >> 24) & 1)
        bar = [self.res_seen and s >= thr - 9, self.res_seen and s >= thr - 6, self.res_seen and s >= thr - 3]
        v = int(bar[0]) | int(bar[1]) << 1 | int(bar[2]) << 2 | dec << 3 | alarm << 4
        return v | (buzz ^ ((self.io_ctrl >> 3) & 1)) << 5 | self.heartbeat << 6

    def _feats(self) -> np.ndarray:
        f = []
        for w in self.feat:
            for v in (w & 0xFFFF, (w >> 16) & 0xFFFF):
                f.append(v - 0x10000 if v & 0x8000 else v)
        return np.array(f[: self.cfg["n_features"]], dtype=np.int64)[None, :]

    def write(self, off: int, v: int) -> None:
        r = self.r
        if off >= r["FEAT0"]:
            k = (off - r["FEAT0"]) >> 2
            if k < self.nw:
                self.feat[k] = v & 0xFFFFFFFF
        elif off == r["CTRL"]:
            if v & 1:
                self.hist.clear(); self.hist2.clear(); self.valid = 0
            if v & 2:
                self.seq = self.nwin = self.ndec = self.nalarm = self.ndec2 = self.nalarm2 = 0
            if v & 4:
                self.bist_runs, self.bist_ok = 1, self.cfg["bist"]["n"]
        elif off == r["COMMIT"]:
            hd = self.model.head
            bits, luts, sc = self.model.forward(self._feats())
            s = int(sc[0])
            self.bits, self.luts = bits[0], luts[0]
            self.res_seen, self.heartbeat = 1, self.heartbeat ^ 1
            gate = False
            if hd["artefact_gate"] == "both":
                gate = (v & 3) == 3
            elif hd["artefact_gate"] == "any":
                gate = (v & 3) != 0
            d = int(s >= hd["decision_threshold"] and not gate)
            self.hist.append(d)
            a = int(sum(self.hist) >= hd["k"])
            d2 = int(s >= self.op_thr)
            self.hist2.append(d2)
            a2 = int(sum(self.hist2) >= self.op_k)
            self.seq = (self.seq + 1) & 0xFFFF
            self.valid, self.res = 1, (s, d, a, d2, a2)
            self.nwin += 1; self.ndec += d; self.nalarm += a; self.ndec2 += d2; self.nalarm2 += a2
        elif off == r["SCRATCH"]:
            self.scratch = v & 0xFFFFFFFF
        elif off == r["OP_THR"]:
            b = v & 0xFF
            self.op_thr = b - 256 if b & 0x80 else b
        elif off == r["OP_K"]:
            self.op_k = v & 0xF
        elif off == r.get("IO_CTRL"):
            self.io_ctrl = v & 0xF
        elif off == r.get("IO_MANUAL"):
            self.io_manual = v & 0x7F

    def read(self, off: int) -> int:
        r = self.r
        if off >= r["FEAT0"]:
            k = (off - r["FEAT0"]) >> 2
            return self.feat[k] if k < self.nw else 0
        if off == r["ID"]:
            return self.cfg["id"]
        if off == r["INFO"]:
            return self.cfg["info"]
        if off == r["STATUS"]:
            done = 1 if self.bist_runs else 0
            return (done << 3) | (done << 2) | self.valid
        if "DBG_BITS0" in r and r["DBG_BITS0"] <= off < r["DBG_BITS0"] + 20:
            k = (off - r["DBG_BITS0"]) >> 2
            return int(sum(int(b) << j for j, b in enumerate(self.bits[32 * k: 32 * k + 32])))
        if "DBG_LUTS0" in r and r["DBG_LUTS0"] <= off < r["DBG_LUTS0"] + 8:
            k = (off - r["DBG_LUTS0"]) >> 2
            return int(sum(int(b) << j for j, b in enumerate(self.luts[32 * k: 32 * k + 32])))
        if off == r.get("IO_CTRL"):
            return self.io_ctrl
        if off == r.get("IO_MANUAL"):
            return self.io_manual
        if off == r.get("BTN"):
            return (self.btn_count << 16) | self.btn_pressed
        if off == r.get("IO_STATE"):
            return self._io_state()
        if off == r["RESULT"]:
            s, d, a, d2, a2 = self.res
            return ((self.seq << 16) | (self.valid << 15) | (a2 << 11) | (d2 << 10) | (a << 9) | (d << 8)
                    | (s & 0xFF))
        return {r["NWIN"]: self.nwin, r["NDEC"]: self.ndec, r["NALARM"]: self.nalarm,
                r["LATENCY"]: self.cfg["latency_cycles"], r["SCRATCH"]: self.scratch,
                r["CYCLES"]: int((time.perf_counter() - self.cycles0) * 1e8) & 0xFFFFFFFF,
                r["BIST_N"]: self.cfg["bist"]["n"], r["BIST_OK"]: self.bist_ok, r["BIST_ERR"]: 0,
                r["BIST_CYC"]: self.cfg["bist"]["n"] + self.cfg["latency_cycles"] + 1,
                r["BIST_RUNS"]: self.bist_runs, r["BIST_FIRSTERR"]: 0xFFFFFFFF,
                r["OP_THR"]: self.op_thr & 0xFFFFFFFF, r["OP_K"]: self.op_k, r["NDEC2"]: self.ndec2,
                r["NALARM2"]: self.nalarm2}.get(off, 0xDEADBEEF)


# ---------------------------------------------------------------------------------------------- driver
class SeizeLUT:
    def __init__(self, backend: str = "pynq", bitfile: str | None = None, base: int | None = None,
                 regs: str | None = None, model_dir: str | None = None):
        self.cfg = json.loads(Path(regs or HERE / "seizelut_regs.json").read_text())
        self.R = self.cfg["registers"]
        self.backend_name = backend
        self.fast = None
        if backend == "pynq":
            self.hw = _PynqBackend(bitfile or str(HERE / "seizelut.bit"))
            self.base = self.hw.base
        elif backend == "devmem":
            if base is None:
                raise ValueError("devmem backend needs --base (e.g. 0x80000000)")
            self.hw = _MemBackend(base)
            self.base = base
        elif backend == "emu":
            from seizelut_model import SeizeLUTModel
            self.hw = _EmuBackend(self.cfg, SeizeLUTModel(model_dir or HERE / "model"))
            self.base = None
        else:
            raise ValueError(backend)

    # ---- registers
    def read(self, name) -> int:
        return self.hw.read(self.R[name] if isinstance(name, str) else name)

    def write(self, name, v: int) -> None:
        self.hw.write(self.R[name] if isinstance(name, str) else name, v)

    def identify(self) -> dict:
        info = self.read("INFO")
        return {"id": f"0x{self.read('ID'):08X}", "id_ok": self.read("ID") == self.cfg["id"],
                "version": info & 0xFF, "n_features": (info >> 8) & 0xFF, "n_luts": (info >> 16) & 0xFF,
                "latency_cycles": (info >> 24) & 0xFF, "info_ok": info == self.cfg["info"]}

    def scratch_test(self, n: int = 64) -> bool:
        rng = np.random.default_rng(1)
        for v in rng.integers(0, 2 ** 32, n, dtype=np.uint64):
            self.write("SCRATCH", int(v))
            if self.read("SCRATCH") != int(v):
                return False
        return True

    def soft_reset(self, clear_counters: bool = True) -> None:
        """Reset the classifier history (and counters). On AXI a read may overtake an earlier write, so wait
        until the reset is visible before anything reads the result counter."""
        self.write("CTRL", 0x1 | (0x2 if clear_counters else 0))
        time.sleep(0.001)
        if clear_counters:
            for _ in range(10000):
                if self.read("NWIN") == 0 and (self.read("RESULT") >> 16) == 0:
                    break
            else:
                raise TimeoutError("soft reset not visible")

    def set_operating_point(self, threshold: int, k: int) -> None:
        """Programmable decision threshold and k of the second (programmable) result path."""
        self.write("OP_THR", int(threshold) & 0xFF)
        self.write("OP_K", int(k) & 0xF)
        time.sleep(0.001)
        b = self.read("OP_THR") & 0xFF
        if (b - 256 if b & 0x80 else b) != int(threshold) or self.read("OP_K") != int(k):
            raise RuntimeError("operating point registers did not take the new values")

    # ---- live demo: debug taps, LEDs, button
    def debug_taps(self) -> tuple[np.ndarray, np.ndarray]:
        """Comparator bits and last-layer LUT outputs of the latest window, read back from the core."""
        nb, nl = self.cfg.get("n_bits", 146), self.cfg.get("n_last_luts", 50)
        wb = [self.read(self.R["DBG_BITS0"] + 4 * k) for k in range((nb + 31) // 32)]
        wl = [self.read(self.R["DBG_LUTS0"] + 4 * k) for k in range((nl + 31) // 32)]
        bits = np.array([(wb[j >> 5] >> (j & 31)) & 1 for j in range(nb)], dtype=np.uint8)
        luts = np.array([(wl[j >> 5] >> (j & 31)) & 1 for j in range(nl)], dtype=np.uint8)
        return bits, luts

    def set_io(self, auto: bool = True, follow_programmable: bool = False, buzzer: bool = True,
               buzzer_active_low: bool = False) -> None:
        """PMOD outputs: auto (driven by the result in hardware) or manual (IO_MANUAL); which result path the
        LEDs follow; buzzer on/off and polarity."""
        self.write("IO_CTRL", int(auto) | int(follow_programmable) << 1 | int(buzzer) << 2
                   | int(buzzer_active_low) << 3)

    def set_leds_manual(self, mask: int) -> None:
        self.write("IO_MANUAL", int(mask) & 0x7F)

    def io_state(self) -> int:
        """The seven PMOD output pins as the fabric drives them (A1..A4, B1..B3 = bits 0..6)."""
        return self.read("IO_STATE") & 0x7F

    def button(self) -> tuple[int, int]:
        """(pressed now, number of presses since reset) of the PMOD push button."""
        v = self.read("BTN")
        return v & 1, (v >> 16) & 0xFFFF

    def counters(self) -> dict:
        return {k.lower(): self.read(k) for k in ("NWIN", "NDEC", "NALARM", "NDEC2", "NALARM2", "LATENCY")}

    # ---- one window
    def classify(self, feat_row: np.ndarray, art: int = 0, timeout_polls: int = 100000) -> tuple[int, int, int]:
        seq = (self.read("RESULT") >> 16) & 0xFFFF
        for k, w in enumerate(pack_words(np.asarray(feat_row)[None, :])[0]):
            self.write(self.R["FEAT0"] + 4 * k, int(w))
        self.write("COMMIT", int(art) & 3)
        for _ in range(timeout_polls):
            s, d, a, valid, sq, _, _ = decode_result(self.read("RESULT"))
            if valid and sq == ((seq + 1) & 0xFFFF):
                return s, d, a
        raise TimeoutError("no result from the core")

    # ---- whole recording
    def _load_fast(self) -> bool:
        if self.fast is not None:
            return bool(self.fast)
        self.fast = False
        if self.base is None:
            return False
        so = HERE / "libfastio.so"
        try:
            if not so.exists() or so.stat().st_mtime < (HERE / "fastio.c").stat().st_mtime:
                subprocess.run(["gcc", "-O2", "-shared", "-fPIC", "-o", str(so), str(HERE / "fastio.c")],
                               check=True, capture_output=True)
            lib = ctypes.CDLL(str(so))
            lib.sl_open.argtypes = [ctypes.c_uint64, ctypes.c_uint32]
            lib.sl_run.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_void_p,
                                   ctypes.c_void_p]
            if lib.sl_open(self.base, 0x1000) != 0:
                return False
            self.fast = lib
        except Exception as e:   # no compiler or no /dev/mem access: fall back to Python
            print(f"[seizelut] fast C path unavailable ({e}); using the Python path")
            self.fast = False
        return bool(self.fast)

    def run_recording(self, feats: np.ndarray, art: np.ndarray, use_fast: bool = True) -> dict:
        """Soft reset, then every window through the core; returns the hardware's score/decision/alarm."""
        self.soft_reset()
        words = np.ascontiguousarray(pack_words(feats))
        artc = np.ascontiguousarray((art[:, 0] | (art[:, 1] << 1)).astype(np.uint8))
        n, nw = words.shape
        if use_fast and self._load_fast():
            res = np.zeros(n, dtype=np.uint32)
            secs = np.zeros(2, dtype=np.float64)
            rc = self.fast.sl_run(words.ctypes.data, artc.ctypes.data, n, nw, res.ctypes.data, secs.ctypes.data)
            if rc != 0:
                print(f"[seizelut] fast C path: no result for window {-rc - 1}; repeating with the Python path")
                self.fast = False
                out = self.run_recording(feats, art, use_fast=False)
                out["method"] = "python (C path timed out)"
                return out
            method, seconds, worst = "c", float(secs[0]), float(secs[1])
        else:
            res = np.zeros(n, dtype=np.uint32)
            R = self.R
            f0, rc_off, cm = R["FEAT0"], R["RESULT"], R["COMMIT"]
            wr, rd = self.hw.write, self.hw.read
            seq = (rd(rc_off) >> 16) & 0xFFFF
            t0 = time.perf_counter()
            worst = 0.0
            wl = words.tolist()
            al = artc.tolist()
            for i in range(n):
                ti = time.perf_counter()
                for k, w in enumerate(wl[i]):
                    wr(f0 + 4 * k, w)
                wr(cm, al[i])
                seq = (seq + 1) & 0xFFFF
                for _ in range(100000):
                    r = rd(rc_off)
                    if (r >> 15) & 1 and (r >> 16) == seq:
                        break
                else:
                    raise TimeoutError(f"no result for window {i}")
                res[i] = r
                worst = max(worst, time.perf_counter() - ti)
            method, seconds = "python", time.perf_counter() - t0
        s = (res & 0xFF).astype(np.int16)
        s[s > 127] -= 256
        return {"score": s.astype(np.int8), "decision": ((res >> 8) & 1).astype(np.uint8),
                "alarm": ((res >> 9) & 1).astype(np.uint8), "decision2": ((res >> 10) & 1).astype(np.uint8),
                "alarm2": ((res >> 11) & 1).astype(np.uint8), "seconds": seconds, "worst_window_s": worst,
                "method": method, "counters": self.counters()}

    # ---- built-in self-test
    def bist(self, timeout_s: float = 5.0) -> dict:
        runs0 = self.read("BIST_RUNS")
        self.write("CTRL", 0x4)
        time.sleep(0.01)           # 1,024 vectors take ~10 us; also orders this read after the start write
        t0 = time.time()
        while time.time() - t0 < timeout_s:
            st = self.read("STATUS")
            if st & 0x4 and not st & 0x2:
                break
        else:
            return {"pass": False, "error": "BIST did not finish"}
        st = self.read("STATUS")
        n, ok, err, cyc = self.read("BIST_N"), self.read("BIST_OK"), self.read("BIST_ERR"), self.read("BIST_CYC")
        fe = self.read("BIST_FIRSTERR")
        return {"pass": bool(st & 0x8) and err == 0 and ok == n, "vectors": n, "ok": ok, "errors": err,
                "cycles": cyc, "windows_per_cycle": n / cyc if cyc else None,
                "first_error": None if fe == 0xFFFFFFFF else fe}

    def bist_loop(self, on: bool) -> None:
        self.write("CTRL", (0x4 | 0x8) if on else 0x0)
