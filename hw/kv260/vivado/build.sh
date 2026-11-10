#!/usr/bin/env bash
# Build the KV260 bitstream on Linux or WSL:  bash vivado/build.sh [-jobs 8] [-noboard] [-nooc]
# Needs Vivado (2022.1 - 2025.2, free Standard edition with Zynq UltraScale+ / Kria devices).
set -euo pipefail
cd "$(dirname "$0")/.."
if ! command -v vivado >/dev/null 2>&1; then
  for s in /tools/Xilinx/Vivado/*/settings64.sh /tools/Xilinx/*/Vivado/settings64.sh /opt/Xilinx/Vivado/*/settings64.sh \
           "$HOME"/Xilinx/Vivado/*/settings64.sh "$HOME"/Xilinx/*/Vivado/settings64.sh; do
    if [ -f "$s" ]; then echo "using $s"; source "$s"; break; fi
  done
fi
command -v vivado >/dev/null 2>&1 || { echo "vivado not found: run  source <install>/Vivado/<version>/settings64.sh  first"; exit 1; }
mkdir -p out
vivado -mode batch -nojournal -log out/vivado_build.log -source vivado/build_kv260.tcl -tclargs "$@"
python3 tools/parse_reports.py || echo "(report parsing skipped)"
echo "Done. Copy out/seizelut.bit and out/seizelut.hwh into board/ and follow README.md, part C."
