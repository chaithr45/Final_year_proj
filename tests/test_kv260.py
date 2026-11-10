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
                                             ("seizelut_axi.v", "lutnet_classifier.v", "seizelut_bist_rom.v")]
    subprocess.run(["iverilog", "-g2005", "-o", str(exe), *map(str, srcs)], check=True)
    r = subprocess.run(["vvp", "-n", str(exe), f"+vec={KIT / 'sim/vectors/sub-097_run-10.hex'}", "+n=424"],
                       capture_output=True, text=True, check=True)
    assert "PASS 424 windows, 0 mismatches" in r.stdout, r.stdout[-2000:]
    assert "BIST_ERR 0" in r.stdout


def test_register_map_matches_generator():
    from seizelut.hw.kv260 import REGS
    cfg = json.loads((KIT / "rtl/seizelut_regs.json").read_text())
    assert cfg["registers"] == REGS
    assert cfg["n_features"] == 38 and cfg["latency_cycles"] == 3
