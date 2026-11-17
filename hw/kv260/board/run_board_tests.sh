#!/bin/bash
# SeizeLUT board test campaign. Run ON THE KV260 (Kria-PYNQ installed):   bash run_board_tests.sh [--quick]
# Needs seizelut.bit and seizelut.hwh (from the PC's Vivado build, out/ folder) in this board/ folder.
# Saves the console output next to the results JSON in board/results/.
cd "$(dirname "$0")" || exit 1
if [ "$(id -u)" -ne 0 ]; then exec sudo -E bash "$0" "$@"; fi
[ -f /etc/profile.d/pynq_venv.sh ] && source /etc/profile.d/pynq_venv.sh
if [ ! -f seizelut.bit ] || [ ! -f seizelut.hwh ]; then
    echo "seizelut.bit and seizelut.hwh are missing in $(pwd)."
    echo "Copy them from the PC (the kit's out/ folder after the Vivado build) into this folder, then run again."
    exit 1
fi
python3 -c "import pynq" 2>/dev/null || { echo "PYNQ not found: install Kria-PYNQ first (guide step B4)"; exit 1; }
mkdir -p results
LOG="results/console_$(date +%Y%m%d-%H%M%S).txt"
echo "SeizeLUT board tests; console copy in board/$LOG"
python3 run_tests.py "$@" 2>&1 | tee "$LOG"
echo
echo "Next: bash pack_results.sh   (puts everything to send back into ~/seizelut_results.zip)"
