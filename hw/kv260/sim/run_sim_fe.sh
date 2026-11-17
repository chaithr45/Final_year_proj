#!/usr/bin/env bash
# Kit v6 end-to-end testbench (Icarus Verilog): raw samples -> feature engine -> classifier, through the AXI registers.
#   bash sim/run_sim_fe.sh [seconds]      default 6 s of the bundled EEG recording (about 3 minutes in Icarus)
# Expected last line: "PASS <n> windows, 0 mismatches". The full recordings were run in Verilator
# (results/fe_core_verification.json).
set -euo pipefail
cd "$(dirname "$0")/.."
S=${1:-6}
mkdir -p build
iverilog -g2005 -Irtl/fe -o build/tb_fe.vvp sim/tb_seizelut_fe.v rtl/seizelut_axi.v rtl/lutnet_classifier.v \
    rtl/seizelut_bist_rom.v rtl/fe_engine_inline.v
vvp -n build/tb_fe.vvp +samples=sim/fe_vectors/sub-097_run-10.samples.hex +vec=sim/vectors/sub-097_run-10.hex \
    +nsec="$S" +nwin=$((S - 1)) +pres=0 +ram=rtl/fe/fe_ram.hex +nram=930 +replay=4
