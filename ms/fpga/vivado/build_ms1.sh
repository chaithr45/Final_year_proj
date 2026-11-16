#!/usr/bin/env bash
# Build the separate "ms1" kit (FCCM core + impairment emulator) on Linux or WSL:  bash ms/fpga/vivado/build_ms1.sh [-jobs 8]
# Writes only ms/fpga/build and ms/fpga/out; the FCCM kit in hw/kv260 is read, never changed.
set -euo pipefail
cd "$(dirname "$0")/../../.."
if ! command -v vivado >/dev/null 2>&1; then
  for s in /tools/Xilinx/Vivado/*/settings64.sh /tools/Xilinx/*/Vivado/settings64.sh /opt/Xilinx/Vivado/*/settings64.sh \
           "$HOME"/Xilinx/Vivado/*/settings64.sh "$HOME"/Xilinx/*/Vivado/settings64.sh; do
    if [ -f "$s" ]; then echo "using $s"; source "$s"; break; fi
  done
fi
command -v vivado >/dev/null 2>&1 || { echo "vivado not found: source <install>/Vivado/<version>/settings64.sh first"; exit 1; }
mkdir -p ms/fpga/out
vivado -mode batch -nojournal -log ms/fpga/out/vivado_build.log -source ms/fpga/vivado/build_ms1.tcl -tclargs "$@"
git status --short hw/ paper/ export/ src/ scripts/ results/ | grep . && echo "WARNING: FCCM files changed" || echo "FCCM files unchanged"
echo "Done. Copy ms/fpga/out/ms1.bit, ms1.hwh and ms/fpga/board/ to the board; run: sudo python3 ms_impair_kv260.py selftest"
