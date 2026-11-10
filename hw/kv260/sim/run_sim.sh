#!/usr/bin/env bash
# AXI4-Lite testbench of the SeizeLUT core (Icarus Verilog):  bash sim/run_sim.sh [vectors.hex windows]
# Default: the bundled 424-window recording. Expected last line: "PASS <n> windows, 0 mismatches".
set -euo pipefail
cd "$(dirname "$0")/.."
VEC=${1:-sim/vectors/sub-097_run-10.hex}
N=${2:-424}
mkdir -p build
iverilog -g2005 -o build/tb.vvp sim/tb_seizelut_axi.v rtl/seizelut_axi.v rtl/lutnet_classifier.v rtl/seizelut_bist_rom.v
vvp -n build/tb.vvp +vec="$VEC" +n="$N" +thr2=2 +k2=10
