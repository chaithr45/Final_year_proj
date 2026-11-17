"""KV260 kit: the generated AXI core must reproduce the golden outputs through its registers (Icarus Verilog)."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
KIT = REPO / "hw/kv260"


@pytest.mark.skipif(shutil.which("iverilog") is None, reason="needs Icarus Verilog")
def test_axi_core_bundled_recording(tmp_path):
    exe = tmp_path / "tb.vvp"
    srcs = [KIT / "sim/tb_seizelut_axi.v"] + [KIT / "rtl" / f for f in
                                             ("seizelut_axi.v", "lutnet_classifier.v", "seizelut_bist_rom.v",
                                              "fe_engine_inline.v")]
    subprocess.run(["iverilog", "-g2005", "-o", str(exe), *map(str, srcs)], check=True)
    r = subprocess.run(["vvp", "-n", str(exe), f"+vec={KIT / 'sim/vectors/sub-097_run-10.hex'}", "+n=424",
                        f"+fi={KIT / 'sim/fi_cases.hex'}", "+nfi=150"],
                       capture_output=True, text=True, check=True)
    assert "PASS 424 windows, 0 mismatches" in r.stdout, r.stdout[-2000:]
    assert "BIST_ERR 0" in r.stdout
    assert "FAULT CASES 150, mismatches with the prediction 0" in r.stdout


def test_register_map_matches_generator():
    from seizelut.hw.kv260 import REGS
    cfg = json.loads((KIT / "rtl/seizelut_regs.json").read_text())
    assert cfg["registers"] == REGS
    assert cfg["n_features"] == 38 and cfg["latency_cycles"] == 3


def test_fabric_frontend_path_emulated():
    """Kit v6 board software, emulated core: raw samples through the feature-engine registers (FE window, FE_CTRL
    events, auto transfer into the classifier) give the golden features and outputs on the bundled EEG recording."""
    import sys

    import numpy as np
    sys.path.insert(0, str(KIT / "board"))
    from seizelut_kv260 import SeizeLUT
    core = SeizeLUT("emu")
    assert core.has_fabric_fe() and core.cfg["fe"]["window"] == 0x1000
    z = np.load(KIT / "board/raw/sub-097_run-10.npz")
    raw = {k: z[k] for k in z.files if k not in ("golden_features", "golden_art", "n_win")}
    n_win = int(z["n_win"])
    hw = core.fe_run_recording(raw, n_win, use_fast=False)
    spec = [f["spec_index"] for f in core.cfg["features"]]
    v = np.load(KIT / "board/vectors/sub-097_run-10.npz")
    assert (hw["window"] == np.arange(n_win)).all()
    assert (hw["feats"] == z["golden_features"][:, spec]).all()
    assert (hw["score"] == v["score"]).all() and (hw["decision"] == v["decision"]).all()
    assert (hw["alarm"] == v["alarm"]).all() and hw["fe_windows"] == n_win


def test_fe_engine_inline_rtl_matches_images():
    """The engine Vivado builds (rtl/fe_engine_inline.v) holds exactly the program and register file of rtl/fe/."""
    import re
    meta = json.loads((KIT / "rtl/fe/fe_engine.json").read_text())
    src = (KIT / "rtl/fe_engine_inline.v").read_text()
    rom = [int(x, 16) for x in (KIT / "rtl/fe/fe_rom.hex").read_text().split()][: meta["n_rom"]]
    ram = [int(x, 16) for x in (KIT / "rtl/fe/fe_ram.hex").read_text().split()][: meta["n_ram"]]
    got_rom = {int(i): int(v, 16) for i, v in re.findall(r"rom\[(\d+)\] = 32'h([0-9a-f]+);", src)}
    got_ram = {int(i): int(v, 16) for i, v in re.findall(r"ram\[(\d+)\] = 40'h([0-9a-f]+);", src)}
    assert got_rom == dict(enumerate(rom)) and got_ram == dict(enumerate(ram))
    assert "$readmemh" not in src
    board = (KIT / "board/fe_ram.hex").read_text().split()
    assert [int(x, 16) for x in board][: meta["n_ram"]] == ram
