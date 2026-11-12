#!/bin/bash
# Rehearse the demo on the laptop, no board needed (WSL Ubuntu, Linux or macOS):   bash rehearse_laptop.sh [1|2]
# The classifier runs as the software model of the FPGA core; the dashboard says so.
# Needs python3 with numpy (your conda env works: conda activate seizelut).
cd "$(dirname "$0")" || exit 1
DEMO=${1:-1}
python3 -c "import numpy" 2>/dev/null || { echo "numpy missing: conda activate seizelut   (or: pip install numpy)"; exit 1; }
echo "Open http://localhost:8080 in your browser (Windows: Chrome or Edge). Ctrl+C stops."
exec python3 seizelut_demo.py --backend emu --demo "$DEMO" --no-board-leds --port 8080
