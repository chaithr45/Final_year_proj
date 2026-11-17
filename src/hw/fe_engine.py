"""Integer front end in the FPGA fabric: a small microcoded feature engine (SeizeLUT N10).

The engine is an accumulator machine with one 40-bit adder and two 5-bit shifters, a register file in block RAM and a program ROM.
Samples arrive at 256 Hz (biopotentials) and 25 Hz (motion) while the fabric runs at 100 MHz, so one shared datapath
computes every filter, statistic and feature in turn: each filter coefficient is a sum of at most five signed powers
of two (spec/fixed_point.md), so a multiplication is a few shifted additions and the engine has no multiplier.

This module defines the instruction set, assembles the program that computes exactly the 38 features the classifier
reads (bit-exact with src/features/golden.py "int" and hw/kv260/board/frontend/seizelut_fe.c), and writes the ROM and
RAM images for hw/kv260/rtl/fe_engine.v. Events (host writes the inputs, then starts the program at an entry):
  BIO    one biopotential sample: IN_EEG1, IN_EEG2, IN_ECG, IN_EMG (256 Hz)
  MOV    one motion sample: IN_AX, IN_AY, IN_AZ, IN_GX, IN_GY, IN_GZ (25 Hz)
  SEC    end of one second (block): finishes the block and, from the third second on, computes the window that ended
         one second ago (R-peak look-ahead, as the C streaming front end); WIN_VALID / WIN_INDEX / FEAT_0..37
  FLUSH  the last window of a recording (no look-ahead block)
Sensor presence (PRES_ECG, PRES_EMG, PRES_ACC, PRES_GYR) is configured once; absent sensors give zero features.

Instruction word (32 bits): [31:27] op, [26:24] cond, [23] neg, [22] idx, [21:16] sh, [15:0] addr or branch target.
  LD     A = +-(R[ea] << sh)            ADD   A = A +- (R[ea] << sh)       ADDABS A = A + |R[ea]|
  ST     R[ea] = A                      ASR   A = A >>> sh (floor)          ABS    A = |A|
  SAT    A = clamp(A, -2^19, 2^19 - 1)  LOG2  A = ilog2 with 3 fraction bits (0 for A <= 0)
  MAX    A = max(A, R[ea])              LDX   X = R[ea]                     J / BR (cond on A) / HALT
  ea = addr + (idx ? X : 0)
"""
from __future__ import annotations

import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PARAMS = REPO / "hw/kv260/board/frontend/seizelut_fe_params.h"

OPS = {"HALT": 0, "LD": 1, "ADD": 2, "ST": 3, "ASR": 4, "ABS": 5, "SAT": 6, "LOG2": 7, "MAX": 8, "J": 10, "BR": 11,
       "LDX": 12, "ADDABS": 13}
COND = {"LT": 0, "GE": 1, "EQ": 2, "NE": 3, "GT": 4, "LE": 5}
ENTRIES = ("BIO", "MOV", "SEC", "FLUSH")
DW = 40                      # datapath width: worst-case biquad accumulator < 2^38 for any input (see verify_fe_engine.py)
RAM_DEPTH = 1024
BIG = 1 << 30                # empty beat slot time (never <= a window end; recordings are < 2^26 samples)


def read_params() -> tuple[dict, dict]:
    txt = PARAMS.read_text()
    consts = {k: int(v) for k, v in re.findall(r"#define (\w+) (-?\d+)\s*$", txt, re.M)}
    coefs = {}
    for name, body in re.findall(r"fe_coef C_(\w+) = \{([^}]*)\}", txt):
        v = [int(x) for x in body.split(",")]
        coefs[name] = {"b": v[:3], "a": v[3:5], "frac": v[5]}
    return consts, coefs


def csd(v: int) -> list[tuple[int, int]]:
    """Canonical signed-digit terms of an integer: [(shift, +1/-1)], value = sum(sign << shift)."""
    out, k, s, v = [], 0, (1 if v >= 0 else -1), abs(v)
    while v:
        if v & 1:
            d = 2 - (v & 3)
            out.append((k, d * s))
            v -= d
        v >>= 1
        k += 1
    return out


class Asm:
    def __init__(self):
        self.code: list[dict] = []
        self.labels: dict[str, int] = {}
        self.regs: dict[str, int] = {}
        self.init: dict[int, int] = {}
        self.consts: dict[int, int] = {}
        self._n = 0

    # registers
    def reg(self, name: str, init: int = 0, size: int = 1) -> int:
        if name in self.regs:
            return self.regs[name]
        a = self._alloc
        self.regs[name] = a
        for i in range(size):
            self.init[a + i] = init
        self._alloc_next(size)
        return a

    @property
    def _alloc(self) -> int:
        return getattr(self, "_next", 0)

    def _alloc_next(self, size: int) -> None:
        self._next = self._alloc + size
        assert self._next <= RAM_DEPTH, "register file full"

    def const(self, v: int) -> int:
        if v not in self.consts:
            self.consts[v] = self.reg(f"#const{v}", init=v)
        return self.consts[v]

    def label(self) -> str:
        self._n += 1
        return f"L{self._n}"

    def here(self, name: str) -> None:
        assert name not in self.labels, name
        self.labels[name] = len(self.code)

    def emit(self, op, addr=0, sh=0, neg=0, idx=0, cond=0, target=None):
        assert 0 <= sh < 32, "the RTL shifters take 5-bit amounts"
        self.code.append({"op": op, "addr": addr, "sh": sh, "neg": int(neg), "idx": int(idx), "cond": cond,
                          "target": target})

    # instructions
    def ld(self, r, sh=0, neg=False, idx=False): self.emit("LD", r, sh, neg, idx)
    def add(self, r, sh=0, neg=False, idx=False): self.emit("ADD", r, sh, neg, idx)
    def sub(self, r, idx=False): self.emit("ADD", r, 0, True, idx)
    def addabs(self, r, idx=False): self.emit("ADDABS", r, idx=idx)
    def st(self, r, idx=False): self.emit("ST", r, idx=idx)
    def asr(self, s): self.emit("ASR", sh=s)
    def abs_(self): self.emit("ABS")
    def sat(self): self.emit("SAT")
    def log2(self): self.emit("LOG2")
    def max_(self, r): self.emit("MAX", r)
    def ldx(self, r): self.emit("LDX", r)
    def j(self, lab): self.emit("J", target=lab)
    def br(self, cond, lab): self.emit("BR", cond=COND[cond], target=lab)
    def halt(self): self.emit("HALT")

    # macros
    def mov(self, dst, src):
        self.ld(src)
        self.st(dst)

    def zero(self, *regs):
        self.ld(self.const(0))
        for r in regs:
            self.st(r)

    def inc(self, r):
        self.ld(r)
        self.add(self.const(1))
        self.st(r)

    def assemble(self) -> list[int]:
        words = []
        for ins in self.code:
            addr = ins["addr"] if ins["target"] is None else self.labels[ins["target"]]
            assert 0 <= addr < (1 << 16)
            words.append((OPS[ins["op"]] << 27) | (ins["cond"] << 24) | (ins["neg"] << 23) | (ins["idx"] << 22)
                         | (ins["sh"] << 16) | addr)
        return words


# ---------------------------------------------------------------------------------------------- program pieces
def biquad(A: Asm, name: str, coef: dict, x: int, out: int) -> None:
    """y = bq(state, coef, x): the C bq() with error feedback and 20-bit saturation; result in register out."""
    s = {k: A.reg(f"{name}.{k}") for k in ("x1", "x2", "y1", "y2", "e1", "e2")}
    tacc, tv = A.reg("#tacc"), A.reg("#tv")
    first = True
    for c, src in ((coef["b"][0], x), (coef["b"][1], s["x1"]), (coef["b"][2], s["x2"]),
                   (-coef["a"][0], s["y1"]), (-coef["a"][1], s["y2"])):
        for sh, sg in csd(c):
            if first:
                A.ld(src, sh, sg < 0)
                first = False
            else:
                A.add(src, sh, sg < 0)
    if first:
        A.ld(A.const(0))
    A.add(s["e1"], 1)                  # + 2 e1
    A.sub(s["e2"])                     # - e2
    A.st(tacc)
    A.asr(coef["frac"])
    A.st(tv)                           # v = floor(acc / 2^frac)
    A.mov(s["e2"], s["e1"])
    A.ld(tacc)
    A.add(tv, coef["frac"], True)
    A.st(s["e1"])                      # e1 = acc - (v << frac)
    A.ld(tv)
    A.sat()
    A.st(out)
    A.mov(s["x2"], s["x1"])
    A.mov(s["x1"], x)
    A.mov(s["y2"], s["y1"])
    A.mov(s["y1"], out)


def block_stats(A: Asm, name: str, v: int, want: set[str]) -> dict:
    """bs_step(): per-block MAV, line length, zero crossings, extrema of signal v (only the wanted ones)."""
    r = {k: A.reg(f"{name}.{k}") for k in ("prev", "psign", "slope", "started", "mav", "ll", "zc", "ext")}
    one, zero, m1 = A.const(1), A.const(0), A.const(-1)
    td = A.reg("#td")
    if "mav" in want:
        A.ld(r["mav"])
        A.addabs(v)
        A.st(r["mav"])
    go, end = A.label(), A.label()
    A.ld(r["started"])
    A.br("NE", go)
    A.mov(r["prev"], v)
    if "zc" in want:
        n0, done = A.label(), A.label()
        A.ld(v)
        A.br("LT", n0)
        A.mov(r["psign"], one)
        A.j(done)
        A.here(n0)
        A.mov(r["psign"], zero)
        A.here(done)
    A.mov(r["slope"], zero)
    A.mov(r["started"], one)
    A.j(end)
    A.here(go)
    A.ld(v)
    A.sub(r["prev"])
    A.st(td)
    if "ll" in want:
        A.ld(r["ll"])
        A.addabs(td)
        A.st(r["ll"])
    if "zc" in want:
        vneg, done = A.label(), A.label()
        A.ld(v)
        A.br("LT", vneg)
        A.ld(r["psign"])                 # s = 1
        A.br("NE", done)
        A.inc(r["zc"])
        A.mov(r["psign"], one)
        A.j(done)
        A.here(vneg)                     # s = 0
        A.ld(r["psign"])
        A.br("EQ", done)
        A.inc(r["zc"])
        A.mov(r["psign"], zero)
        A.here(done)
    if "ext" in want:
        dneg, done, s1, s2 = A.label(), A.label(), A.label(), A.label()
        A.ld(td)
        A.br("EQ", done)
        A.br("LT", dneg)
        A.ld(r["slope"])                 # d > 0: an extremum if the slope was negative
        A.br("GE", s1)
        A.inc(r["ext"])
        A.here(s1)
        A.mov(r["slope"], one)
        A.j(done)
        A.here(dneg)                     # d < 0: an extremum if the slope was positive
        A.ld(r["slope"])
        A.br("LE", s2)
        A.inc(r["ext"])
        A.here(s2)
        A.mov(r["slope"], m1)
        A.here(done)
    A.mov(r["prev"], v)
    A.here(end)
    return r


def context(A: Asm, name: str, src: int, out: int, guard: int, shift: int) -> None:
    """Difference from a causal EMA started at the first valid window (X = f - (e >> G); e += ((f << G) - e) >> S)."""
    e, started = A.reg(f"{name}.e"), A.reg(f"{name}.started")
    go, t = A.label(), A.reg("#tctx")
    A.ld(started)
    A.br("NE", go)
    A.ld(src, guard)
    A.st(e)
    A.mov(started, A.const(1))
    A.here(go)
    A.ld(e)
    A.asr(guard)
    A.st(t)
    A.ld(src)
    A.sub(t)
    A.st(out)
    A.ld(src, guard)
    A.sub(e)
    A.asr(shift)
    A.add(e)
    A.st(e)


# ---------------------------------------------------------------------------------------------- the program
def build(feature_order: list[str]) -> dict:
    K, C = read_params()
    G = K["EMA_GUARD_BITS"]
    A = Asm()
    one, zero = A.const(1), A.const(0)
    io = {n: A.reg(n) for n in ("IN_EEG1", "IN_EEG2", "IN_ECG", "IN_EMG", "IN_AX", "IN_AY", "IN_AZ", "IN_GX", "IN_GY",
                                "IN_GZ", "PRES_ECG", "PRES_EMG", "PRES_ACC", "PRES_GYR", "WIN_VALID", "WIN_INDEX")}
    feat = [A.reg(f"FEAT_{i}") for i in range(len(feature_order))]
    bcount = A.reg("BCOUNT")
    # block summaries: current (cur), previous (B = block w+1) and the one before (A = block w)
    BLK = [f"eeg{c}.{k}" for c in (1, 2) for k in ("mav", "ll", "ext", "delta", "theta", "alpha", "beta", "hf")]
    BLK += ["eeg.agree", "emg.mav", "emg.ll", "emg.zc", "acc.mag", "acc.jerk", "acc.act", "gyr.mag", "gyr.jerk", "gyr.act"]
    blkA = {k: A.reg(f"A.{k}") for k in BLK}
    blkB = {k: A.reg(f"B.{k}") for k in BLK}

    # ======================================================================== BIO: one biopotential sample
    A.here("BIO")
    eeg_cur = {}
    xbp = {}
    for c, src in ((1, io["IN_EEG1"]), (2, io["IN_EEG2"])):
        r = {k: A.reg(f"eeg{c}.{k}") for k in ("h1", "xbp", "de", "t1", "th", "t2", "al", "t3", "be", "t4", "hf")}
        biquad(A, f"eeg{c}.f0", C["eeg_hp1"], src, r["h1"])
        biquad(A, f"eeg{c}.f1", C["eeg_lp25"], r["h1"], r["xbp"])
        biquad(A, f"eeg{c}.f2", C["eeg_lp4"], r["h1"], r["de"])
        biquad(A, f"eeg{c}.f3", C["eeg_hp4"], src, r["t1"])
        biquad(A, f"eeg{c}.f4", C["eeg_lp8"], r["t1"], r["th"])
        biquad(A, f"eeg{c}.f5", C["eeg_hp8"], src, r["t2"])
        biquad(A, f"eeg{c}.f6", C["eeg_lp13"], r["t2"], r["al"])
        biquad(A, f"eeg{c}.f7", C["eeg_hp13"], src, r["t3"])
        biquad(A, f"eeg{c}.f8", C["eeg_lp25"], r["t3"], r["be"])
        biquad(A, f"eeg{c}.f9", C["eeg_hp25"], src, r["t4"])
        biquad(A, f"eeg{c}.f10", C["eeg_lp60"], r["t4"], r["hf"])
        bs = block_stats(A, f"eeg{c}.bs", r["xbp"], {"mav", "ll", "ext"})
        cur = {"mav": bs["mav"], "ll": bs["ll"], "ext": bs["ext"]}
        for band, sig in (("delta", "de"), ("theta", "th"), ("alpha", "al"), ("beta", "be"), ("hf", "hf")):
            acc = A.reg(f"eeg{c}.cur.{band}")
            A.ld(acc)
            A.addabs(r[sig])
            A.st(acc)
            cur[band] = acc
        eeg_cur[c] = cur
        xbp[c] = r["xbp"]
    agree = A.reg("eeg.cur.agree")
    a0neg, no, done = A.label(), A.label(), A.label()
    A.ld(xbp[1])
    A.br("LT", a0neg)
    A.ld(xbp[2])
    A.br("LT", no)
    A.inc(agree)
    A.j(done)
    A.here(a0neg)
    A.ld(xbp[2])
    A.br("GE", no)
    A.inc(agree)
    A.here(no)
    A.here(done)

    # ---- ECG: filters, integrated |derivative|, adaptive-threshold R-peak detector, beat ring buffer
    E = {n: A.reg(f"ecg.{n}") for n in ("e", "t", "e1", "e2", "m", "spk", "npk", "cand", "rising", "prevm", "thr",
                                         "ri", "n", "d", "r", "tail", "havebeat", "haveprr", "prevbt", "prevrr", "rr")}
    E["candi"] = A.reg("ecg.candi", init=-1)
    E["lastbeat"] = A.reg("ecg.lastbeat", init=-K["ECG_REFRACTORY"])
    rhist = A.reg("ecg.rhist", size=K["ECG_INTEG"])
    NB = 64
    BT = A.reg("ecg.bt", init=BIG, size=NB)
    BRR, BHASRR, BBAD, BHASD, BDRR = (A.reg(f"ecg.b{n}", size=NB) for n in ("rr", "hasrr", "bad", "hasd", "drr"))
    skip_ecg = A.label()
    A.ld(io["PRES_ECG"])
    A.br("EQ", skip_ecg)
    biquad(A, "ecg.f1", C["ecg_hp5"], io["IN_ECG"], E["t"])
    biquad(A, "ecg.f2", C["ecg_lp15"], E["t"], E["e"])
    A.ld(E["e"])
    A.sub(E["e2"])
    A.st(E["d"])                                     # d = e - e2 (e2 = 0 for the first two samples)
    A.mov(E["e2"], E["e1"])
    A.mov(E["e1"], E["e"])
    A.ld(E["d"])
    A.abs_()
    A.st(E["r"])
    A.ldx(E["ri"])
    A.ld(E["m"])
    A.add(E["r"])
    A.add(rhist, 0, True, True)                       # m += r - rhist[i % 32]
    A.st(E["m"])
    A.ld(E["r"])
    A.st(rhist, True)
    ri_ok = A.label()
    A.inc(E["ri"])
    A.sub(A.const(K["ECG_INTEG"]))
    A.br("NE", ri_ok)
    A.mov(E["ri"], zero)
    A.here(ri_ok)
    after_warm, wskip, ecg_end = A.label(), A.label(), A.label()
    A.ld(E["n"])
    A.sub(A.const(K["ECG_WARMUP"]))
    A.br("GE", after_warm)
    A.ld(E["m"])                                      # warm-up: track the largest integrated value
    A.sub(E["spk"])
    A.br("LE", wskip)
    A.ld(E["m"])
    A.st(E["spk"])
    A.asr(3)
    A.st(E["npk"])
    A.here(wskip)
    A.mov(E["prevm"], E["m"])
    A.j(ecg_end)
    A.here(after_warm)
    not_rise, rise_done, nobeat, beat_done = A.label(), A.label(), A.label(), A.label()
    A.ld(E["m"])
    A.sub(E["prevm"])
    A.br("LE", not_rise)
    A.mov(E["rising"], one)                          # rising: remember the candidate peak
    A.ld(E["m"])
    A.sub(E["cand"])
    A.br("LE", rise_done)
    A.mov(E["cand"], E["m"])
    A.mov(E["candi"], E["n"])
    A.j(rise_done)
    A.here(not_rise)
    A.ld(E["m"])
    A.sub(E["prevm"])
    A.br("GE", rise_done)                            # falling (m < prev_m) after a rise: decide
    A.ld(E["rising"])
    A.br("EQ", rise_done)
    A.mov(E["rising"], zero)
    A.ld(E["spk"])
    A.sub(E["npk"])
    A.asr(K["ECG_THR_SHIFT"])
    A.add(E["npk"])
    A.st(E["thr"])
    A.ld(E["cand"])
    A.sub(E["thr"])
    A.br("LE", nobeat)
    A.ld(E["candi"])
    A.sub(E["lastbeat"])
    A.sub(A.const(K["ECG_REFRACTORY"]))
    A.br("LT", nobeat)
    # beat at candi: ring buffer slot = tail
    A.ldx(E["tail"])
    A.ld(E["candi"])
    A.st(BT, True)
    A.ld(E["havebeat"])
    A.st(BHASRR, True)
    nohave, hv_done, bad1, bad_done, nod, d_done = (A.label() for _ in range(6))
    A.br("EQ", nohave)
    A.ld(E["candi"])
    A.sub(E["prevbt"])
    A.st(E["rr"])
    A.st(BRR, True)
    A.sub(A.const(K["ECG_RR_MIN"]))
    A.br("LT", bad1)
    A.ld(E["rr"])
    A.sub(A.const(K["ECG_RR_MAX"]))
    A.br("GT", bad1)
    A.ld(zero)
    A.st(BBAD, True)
    A.j(bad_done)
    A.here(bad1)
    A.ld(one)
    A.st(BBAD, True)
    A.here(bad_done)
    A.ld(E["haveprr"])
    A.st(BHASD, True)
    A.br("EQ", nod)
    A.ld(E["rr"])
    A.sub(E["prevrr"])
    A.abs_()
    A.st(BDRR, True)
    A.j(d_done)
    A.here(nod)
    A.ld(zero)
    A.st(BDRR, True)
    A.here(d_done)
    A.mov(E["prevrr"], E["rr"])
    A.mov(E["haveprr"], one)
    A.j(hv_done)
    A.here(nohave)
    A.ld(zero)
    A.st(BRR, True)
    A.st(BBAD, True)
    A.st(BHASD, True)
    A.st(BDRR, True)
    A.here(hv_done)
    A.mov(E["prevbt"], E["candi"])
    A.mov(E["havebeat"], one)
    tail_ok = A.label()
    A.inc(E["tail"])
    A.sub(A.const(NB))
    A.br("NE", tail_ok)
    A.mov(E["tail"], zero)
    A.here(tail_ok)
    A.mov(E["lastbeat"], E["candi"])
    A.ld(E["cand"])
    A.sub(E["spk"])
    A.asr(K["ECG_SPK_SHIFT"])
    A.add(E["spk"])
    A.st(E["spk"])
    A.j(beat_done)
    A.here(nobeat)
    A.ld(E["cand"])
    A.sub(E["npk"])
    A.asr(K["ECG_SPK_SHIFT"])
    A.add(E["npk"])
    A.st(E["npk"])
    A.here(beat_done)
    A.mov(E["cand"], zero)
    A.here(rise_done)
    A.mov(E["prevm"], E["m"])
    A.here(ecg_end)
    A.inc(E["n"])
    A.here(skip_ecg)

    # ---- EMG: 20 Hz high-pass, block MAV, line length, zero crossings
    skip_emg = A.label()
    A.ld(io["PRES_EMG"])
    A.br("EQ", skip_emg)
    g = A.reg("emg.g")
    biquad(A, "emg.f0", C["emg_hp20"], io["IN_EMG"], g)
    emg_bs = block_stats(A, "emg.bs", g, {"mav", "ll", "zc"})
    A.here(skip_emg)
    A.halt()

    # ======================================================================== MOV: one motion sample
    A.here("MOV")
    mov_cur = {}
    for sn, ins, pres in (("acc", ("IN_AX", "IN_AY", "IN_AZ"), "PRES_ACC"), ("gyr", ("IN_GX", "IN_GY", "IN_GZ"), "PRES_GYR")):
        skip, init_done = A.label(), A.label()
        A.ld(io[pres])
        A.br("EQ", skip)
        minit = A.reg(f"{sn}.minit")
        mm = [A.reg(f"{sn}.mm{k}") for k in range(3)]
        A.ld(minit)
        A.br("NE", init_done)
        for k in range(3):
            A.ld(io[ins[k]], G)
            A.st(mm[k])
        A.mov(minit, one)
        A.here(init_done)
        l1, diff, y = A.reg("#l1"), A.reg("#diff"), A.reg("#y")
        A.mov(l1, zero)
        lls = []
        for k in range(3):
            A.ld(io[ins[k]], G)
            A.sub(mm[k])
            A.st(diff)                       # xi - m
            A.asr(G)
            A.st(y)                          # y = (xi - m) >> G
            A.ld(diff)
            A.asr(K["MOV_OFFSET_SHIFT"])
            A.add(mm[k])
            A.st(mm[k])                      # m += (xi - m) >> MOV_OFFSET_SHIFT
            A.ld(l1)
            A.addabs(y)
            A.st(l1)
            bs = block_stats(A, f"{sn}.bs{k}", y, {"ll"})
            lls.append(bs["ll"])
        mag, act = A.reg(f"{sn}.cur.mag"), A.reg(f"{sn}.cur.act")
        A.ld(mag)
        A.add(l1)
        A.st(mag)
        noact = A.label()
        A.ld(l1)
        A.sub(A.const(K["MOV_ACT_THR"]))
        A.br("LE", noact)
        A.inc(act)
        A.here(noact)
        mov_cur[sn] = {"mag": mag, "act": act, "lls": lls}
        A.here(skip)
    A.halt()

    # ======================================================================== window computation (subroutine-free)
    feats_reg: dict[str, int] = {}

    def window_code():
        """Features of the window [w, w+2) from block summaries A (w) and B (w+1); ECG beats up to end = BCOUNT*256."""
        V = {}
        for c in (1, 2):
            for k in ("mav", "ll", "delta", "theta", "alpha", "beta", "hf"):
                r = A.reg(f"v{c}.{k}")
                A.ld(blkA[f"eeg{c}.{k}"])
                A.add(blkB[f"eeg{c}.{k}"])
                A.log2()
                A.st(r)
                V[(c, k)] = r
            r = A.reg(f"v{c}.ext")
            A.ld(blkA[f"eeg{c}.ext"])
            A.add(blkB[f"eeg{c}.ext"])
            A.st(r)
            V[(c, "ext")] = r
            r = A.reg(f"v{c}.mob")
            A.ld(V[(c, "ll")])
            A.sub(V[(c, "mav")])
            A.st(r)
            V[(c, "mob")] = r

        def cross(k, kind):
            r = A.reg(f"x.{k}.{kind}")
            a, b = V[(1, k)], V[(2, k)]
            if kind == "mean":
                A.ld(a)
                A.add(b)
                A.asr(1)
            elif kind == "max":
                A.ld(a)
                A.max_(b)
            else:
                A.ld(a)
                A.sub(b)
                A.abs_()
            A.st(r)
            return r

        F = feats_reg
        for k, kinds in (("theta", ("mean", "max", "absdiff")), ("delta", ("mean", "max", "absdiff")),
                         ("hf", ("mean", "max", "absdiff")), ("beta", ("mean",)), ("alpha", ("mean",)),
                         ("mav", ("absdiff",)), ("ll", ("absdiff",)), ("ext", ("absdiff",)), ("mob", ("mean",))):
            for kind in kinds:
                F[f"eeg_{k}_{kind}"] = cross(k, kind)
        for c in (1, 2):
            for k in ("theta", "hf", "mav", "alpha"):
                F[f"eeg_ch{c}_{k}"] = V[(c, k)]
        r = A.reg("x.agree")
        A.ld(blkA["eeg.agree"])
        A.add(blkB["eeg.agree"])
        A.st(r)
        F["eeg_sign_agree"] = r
        for k in ("beta_mean", "hf_mean", "hf_max", "theta_max", "theta_mean", "alpha_mean", "mob_mean", "hf_absdiff"):
            out = A.reg(f"c.eeg_{k}")
            context(A, f"ctx.eeg_{k}", F[f"eeg_{k}"], out, G, K["CONTEXT_SHIFT"])
            F[f"eeg_{k}_ctx"] = out

        # ---- ECG
        for n in ("ecg_log_rr", "ecg_log_masrd", "ecg_quality_bad", "ecg_log_rr_ctx", "ecg_log_masrd_ctx"):
            F[n] = A.reg(f"f.{n}")
        absent, ecg_done = A.label(), A.label()
        A.ld(io["PRES_ECG"])
        A.br("EQ", absent)
        end, lo, last, k = A.reg("w.end"), A.reg("w.lo"), A.reg("w.last"), A.reg("w.k")
        srr, nrr, nbad, sd, nd, tt = (A.reg(f"w.{n}") for n in ("srr", "nrr", "nbad", "sd", "nd", "t"))
        A.ld(bcount, 8)
        A.st(end)
        A.sub(A.const(K["ECG_HR_WINDOW_S"] * K["FS_BIO"]))
        A.st(lo)
        A.zero(srr, nrr, nbad, sd, nd, k)
        A.mov(last, A.const(-1))
        loop, skip_all, nrr_l = A.label(), A.label(), A.label()
        A.here(loop)
        A.ldx(k)
        A.ld(BT, idx=True)
        A.st(tt)
        A.sub(end)
        A.br("GT", skip_all)                 # beat after the window end (or an empty slot)
        A.ld(last)
        A.max_(tt)
        A.st(last)
        A.ld(tt)
        A.sub(lo)
        A.br("LE", skip_all)                 # beat before the 10-s RR window
        A.ld(BHASRR, idx=True)
        A.br("EQ", nrr_l)
        A.ld(srr)
        A.add(BRR, idx=True)
        A.st(srr)
        A.inc(nrr)
        A.ld(nbad)
        A.add(BBAD, idx=True)
        A.st(nbad)
        A.here(nrr_l)
        A.ld(BHASD, idx=True)
        A.br("EQ", skip_all)
        A.ld(sd)
        A.add(BDRR, idx=True)
        A.st(sd)
        A.inc(nd)
        A.here(skip_all)
        A.inc(k)
        A.sub(A.const(NB))
        A.br("NE", loop)
        since, nolast, since_done = A.reg("w.since"), A.label(), A.label()
        A.ld(last)
        A.br("LT", nolast)
        A.ld(end)
        A.sub(last)
        A.st(since)
        A.j(since_done)
        A.here(nolast)
        A.mov(since, end)
        A.here(since_done)
        qb, qset, qdone = F["ecg_quality_bad"], A.label(), A.label()
        A.ld(nrr)
        A.sub(A.const(K["ECG_MIN_RR"]))
        A.br("LT", qset)
        A.ld(nbad)
        A.br("GT", qset)
        A.ld(since)
        A.sub(A.const(K["ECG_MAX_GAP_S"] * K["FS_BIO"]))
        A.br("GT", qset)
        A.mov(qb, zero)
        A.j(qdone)
        A.here(qset)
        A.mov(qb, one)
        A.here(qdone)
        t1 = A.reg("#t1")
        zr, rr_done = A.label(), A.label()
        A.ld(nrr)
        A.br("LE", zr)
        A.ld(nrr)
        A.log2()
        A.st(t1)
        A.ld(srr)
        A.log2()
        A.sub(t1)
        A.st(F["ecg_log_rr"])
        A.j(rr_done)
        A.here(zr)
        A.mov(F["ecg_log_rr"], zero)
        A.here(rr_done)
        zd, d_done2 = A.label(), A.label()
        A.ld(nd)
        A.br("LE", zd)
        A.ld(nd)
        A.max_(one)
        A.log2()
        A.st(t1)
        A.ld(sd)
        A.max_(one)
        A.log2()
        A.sub(t1)
        A.st(F["ecg_log_masrd"])
        A.j(d_done2)
        A.here(zd)
        A.mov(F["ecg_log_masrd"], zero)
        A.here(d_done2)
        context(A, "ctx.ecg_log_rr", F["ecg_log_rr"], F["ecg_log_rr_ctx"], G, K["CONTEXT_SHIFT"])
        context(A, "ctx.ecg_log_masrd", F["ecg_log_masrd"], F["ecg_log_masrd_ctx"], G, K["CONTEXT_SHIFT"])
        A.j(ecg_done)
        A.here(absent)
        A.zero(*(F[n] for n in ("ecg_log_rr", "ecg_log_masrd", "ecg_quality_bad", "ecg_log_rr_ctx", "ecg_log_masrd_ctx")))
        A.here(ecg_done)

        # ---- EMG
        for n in ("emg_mav", "emg_ll", "emg_zc"):
            F[n] = A.reg(f"f.{n}")
        absent, done2 = A.label(), A.label()
        A.ld(io["PRES_EMG"])
        A.br("EQ", absent)
        for n, kk, lg in (("emg_mav", "mav", True), ("emg_ll", "ll", True), ("emg_zc", "zc", False)):
            A.ld(blkA[f"emg.{kk}"])
            A.add(blkB[f"emg.{kk}"])
            if lg:
                A.log2()
            A.st(F[n])
        A.j(done2)
        A.here(absent)
        A.zero(F["emg_mav"], F["emg_ll"], F["emg_zc"])
        A.here(done2)

        # ---- motion
        for sn, pres in (("acc", "PRES_ACC"), ("gyr", "PRES_GYR")):
            names = [f"mov_{sn}_mag", f"mov_{sn}_jerk"]
            for n in names:
                F[n] = A.reg(f"f.{n}")
            ctxn = {"acc": ("mov_acc_jerk", "mov_acc_jerk_ctx"), "gyr": ("mov_gyr_act", "mov_gyr_act_ctx")}[sn]
            F[ctxn[1]] = A.reg(f"f.{ctxn[1]}")
            absent, done3 = A.label(), A.label()
            A.ld(io[pres])
            A.br("EQ", absent)
            for n, kk in ((f"mov_{sn}_mag", "mag"), (f"mov_{sn}_jerk", "jerk")):
                A.ld(blkA[f"{sn}.{kk}"])
                A.add(blkB[f"{sn}.{kk}"])
                A.log2()
                A.st(F[n])
            if sn == "gyr":
                F["mov_gyr_act"] = A.reg("f.mov_gyr_act")
                A.ld(blkA["gyr.act"])
                A.add(blkB["gyr.act"])
                A.st(F["mov_gyr_act"])
            context(A, f"ctx.{ctxn[0]}", F[ctxn[0]], F[ctxn[1]], G, K["CONTEXT_SHIFT"])
            A.j(done3)
            A.here(absent)
            A.zero(*(F[n] for n in names + [ctxn[1]]))
            A.here(done3)

        # ---- outputs in the classifier's register order
        for i, n in enumerate(feature_order):
            A.mov(feat[i], F[n])
        A.mov(io["WIN_VALID"], one)
        A.ld(bcount)
        A.sub(A.const(2))
        A.st(io["WIN_INDEX"])

    # ======================================================================== SEC / FLUSH share the window code
    flushf = A.reg("#flush")
    A.here("SEC")
    A.mov(flushf, zero)
    A.j("WINDOW")
    A.here("FLUSH")
    A.mov(flushf, one)
    A.here("WINDOW")
    nowin, stop = A.label(), A.label()
    A.mov(io["WIN_VALID"], zero)
    A.ld(bcount)
    A.sub(A.const(2))
    A.br("LT", nowin)
    window_code()
    A.here(nowin)
    A.ld(flushf)
    A.br("NE", stop)                     # FLUSH: the last window only, no new block
    # current block summaries -> B, B -> A, clear the current ones
    cur = {}
    for c in (1, 2):
        for k, r in eeg_cur[c].items():
            cur[f"eeg{c}.{k}"] = r
    cur["eeg.agree"] = agree
    cur["emg.mav"], cur["emg.ll"], cur["emg.zc"] = emg_bs["mav"], emg_bs["ll"], emg_bs["zc"]
    jerk_tmp = {}
    for sn in ("acc", "gyr"):
        t = A.reg(f"{sn}.cur.jerk")
        lls = mov_cur[sn]["lls"]
        A.ld(lls[0])
        A.add(lls[1])
        A.add(lls[2])
        A.st(t)
        cur[f"{sn}.mag"], cur[f"{sn}.act"], cur[f"{sn}.jerk"] = mov_cur[sn]["mag"], mov_cur[sn]["act"], t
        jerk_tmp[sn] = lls
    assert set(cur) == set(BLK), set(BLK) ^ set(cur)
    for k in BLK:
        A.mov(blkA[k], blkB[k])
        A.mov(blkB[k], cur[k])
    A.ld(zero)
    for k in BLK:
        A.st(cur[k])
    for sn in ("acc", "gyr"):
        for r in jerk_tmp[sn]:
            A.st(r)
    A.inc(bcount)
    A.here(stop)
    A.halt()

    words = A.assemble()
    ram = [0] * RAM_DEPTH
    for a, v in A.init.items():
        ram[a] = v
    return {"rom": words, "ram": ram, "regs": A.regs, "entries": {e: A.labels[e] for e in ENTRIES},
            "feature_order": feature_order, "n_ram": A._alloc, "n_rom": len(words), "dw": DW}


def write_images(prog: dict, out_dir: Path) -> None:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    depth = 1 << max(1, (len(prog["rom"]) - 1).bit_length())
    (out_dir / "fe_rom.hex").write_text("\n".join(f"{w:08x}" for w in prog["rom"] + [0] * (depth - len(prog["rom"]))) + "\n")
    mask = (1 << DW) - 1
    (out_dir / "fe_ram.hex").write_text("\n".join(f"{(v & mask):010x}" for v in prog["ram"]) + "\n")
    meta = {k: prog[k] for k in ("entries", "feature_order", "n_ram", "n_rom", "dw")}
    meta["rom_depth"] = depth
    meta["io"] = {k: v for k, v in prog["regs"].items() if k.isupper() and not k.startswith("#")}
    (out_dir / "fe_engine.json").write_text(json.dumps(meta, indent=1))
    vh = ["// Generated by src/hw/fe_engine.py -- do not edit. Register addresses and program entries of fe_engine."]
    vh += [f"localparam integer FE_ENTRY_{e} = {a};" for e, a in prog["entries"].items()]
    vh += [f"localparam integer FE_{k} = {a};" for k, a in meta["io"].items() if not k.startswith("FEAT_")]
    vh += [f"localparam integer FE_FEAT0 = {prog['regs']['FEAT_0']};",
           f"localparam integer FE_NFEAT = {len(prog['feature_order'])};",
           f"localparam integer FE_ROM_DEPTH = {depth};", f"localparam integer FE_DW = {DW};"]
    (out_dir / "fe_io.vh").write_text("\n".join(vh) + "\n")


def write_inline_rtl(template: Path, fe_dir: Path, out: Path) -> None:
    """fe_engine.v with its ROM and RAM images as initial assignments instead of $readmemh (the form Vivado, Yosys,
    Icarus and Verilator all initialise block RAM from without extra files; the logic is unchanged)."""
    fe_dir = Path(fe_dir)
    meta = json.loads((fe_dir / "fe_engine.json").read_text())
    rom = [int(x, 16) for x in (fe_dir / "fe_rom.hex").read_text().split()][: meta["n_rom"]]
    ram = [int(x, 16) for x in (fe_dir / "fe_ram.hex").read_text().split()][: meta["n_ram"]]
    src = Path(template).read_text()
    old = "    initial begin\n        $readmemh(ROM_FILE, rom);\n        $readmemh(RAM_FILE, ram);\n    end\n"
    assert src.count(old) == 1, "fe_engine.v: $readmemh block not found"
    init = ["    initial begin                             // program (ROM) and initial register file (RAM)"]
    init += [f"        rom[{i}] = 32'h{w:08x};" for i, w in enumerate(rom)]
    init += [f"        ram[{i}] = {meta['dw']}'h{w:0{(meta['dw'] + 3) // 4}x};" for i, w in enumerate(ram)]
    init += ["    end", ""]
    head = ("// Generated by src/hw/fe_engine.py (write_inline_rtl) from rtl/fe_engine.v and rtl/fe/*.hex -- do not edit.\n"
            f"// {meta['n_rom']} instructions, {meta['n_ram']} registers, {meta['dw']}-bit datapath.\n")
    Path(out).write_text(head + src.replace(old, "\n".join(init)))


if __name__ == "__main__":
    th = json.loads((REPO / "hw/kv260/board/model/thresholds.json").read_text())
    p = build([f["name"] for f in th["features"]])
    print("ROM", p["n_rom"], "instructions; RAM", p["n_ram"], "registers; entries", p["entries"])
