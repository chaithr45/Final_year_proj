#!/usr/bin/env bash
# Yosys cost estimate of the MS emulator blocks (Xilinx UltraScale+ cells; Vivado's numbers will differ).
# Usage: bash ms/fpga/synth_yosys.sh [ms_impair|ms_impair_axi] -> ms/results/phase1/<top>_yosys.txt
# Needs yowasp-yosys (pip) or yosys on PATH. The sine table file is generated from ms/py/impair.py.
set -euo pipefail
cd "$(dirname "$0")/../.."
TOP=${1:-ms_impair_axi}
YOSYS=$(command -v yowasp-yosys || command -v yosys)
PY=${PY:-python}
W=$(mktemp -d)
$PY -c "import sys; sys.path.insert(0, 'ms/py'); import impair as I
open('$W/sin4096.hex', 'w').write('\n'.join(f'{int(v) & 0xFFFF:04x}' for v in I.SIN_TABLE) + '\n')"
cp ms/fpga/rtl/ms_impair.v ms/fpga/rtl/ms_impair_axi.v "$W/"
OUT=ms/results/phase1/${TOP}_yosys.txt
{
  echo "# $($YOSYS -V | head -1); read_verilog ms_impair.v ms_impair_axi.v; synth_xilinx -family xcup -top $TOP -flatten -abc9; stat"
  echo "# run $(date -u +'%d %b %Y') (bash ms/fpga/synth_yosys.sh $TOP)"
  (cd "$W" && $YOSYS -q -p "read_verilog ms_impair.v ms_impair_axi.v; chparam -set SIN_HEX \"sin4096.hex\" ms_impair; synth_xilinx -family xcup -top $TOP -flatten -abc9; tee -o stat.txt stat" >/dev/null && sed -n '/Printing statistics/,$p' stat.txt)
} > "$OUT"
rm -rf "$W"
grep -E "LUT[1-6]|FDRE|FDSE|RAMB|DSP|CARRY" "$OUT"
