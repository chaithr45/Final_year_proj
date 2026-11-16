#!/usr/bin/env python3
"""Files the "ms1" kit needs, generated from the golden model (ms/py/impair.py):

  ms/fpga/rtl/sin4096.hex                  sine table read by ms_impair.v ($readmemh) in Vivado synthesis
  ms/fpga/board/vectors/impair_cases.npz   board self-test: for each case of ms/py/impair_rtl.py, the 80
                                           configuration words, and the golden output of the shared input signal

The board script (ms/fpga/board/ms_impair_kv260.py selftest) streams the input through the fabric emulator and
compares every output word with these; it needs only numpy on the board.

Usage: python ms/fpga/make_board_files.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "ms/py"))
import impair as IMP          # noqa: E402
import impair_rtl as R        # noqa: E402

N = 70_000
KEY = (11, 22, 33)


def main() -> int:
    (REPO / "ms/fpga/rtl/sin4096.hex").write_text("\n".join(f"{int(v) & 0xFFFF:04x}" for v in IMP.SIN_TABLE) + "\n")
    rng = np.random.default_rng(5)                 # the input of impair_rtl.py
    x = np.clip(np.round(rng.normal(0, 40, N) + 400 * np.sin(2 * np.pi * 7 * np.arange(N) / 256)),
                -32768, 32767).astype(np.int16)
    names, cfgs, outs, clips = [], [], [], []
    for name, kw in R.CASES.items():
        c = IMP.compile_impairment(IMP.Impairment(**kw), 256.0, 0.25)
        y, st = IMP.apply(x, c, KEY)
        names.append(name); cfgs.append(R.config_words(c, KEY)); outs.append(y.astype(np.int16))
        clips.append(st["clipped"])
    d = REPO / "ms/fpga/board/vectors"
    d.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(d / "impair_cases.npz", names=np.array(names), cfg=np.array(cfgs, dtype=np.uint32),
                        x=x, y=np.array(outs), clipped=np.array(clips, dtype=np.int64))
    print(f"{len(names)} cases x {N} samples -> {d / 'impair_cases.npz'}; sine table -> ms/fpga/rtl/sin4096.hex")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
