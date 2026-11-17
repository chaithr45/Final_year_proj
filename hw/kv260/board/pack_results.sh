#!/bin/bash
# Collect the board results to send back: ~/seizelut_results.zip (results JSON files and console logs).
# Run ON THE KV260:   bash pack_results.sh
cd "$(dirname "$0")" || exit 1
OUT="${SUDO_USER:+/home/$SUDO_USER}"; OUT="${OUT:-$HOME}/seizelut_results.zip"
if [ ! -d results ] || [ -z "$(ls -A results 2>/dev/null)" ]; then echo "no results yet: run bash run_board_tests.sh first"; exit 1; fi
python3 - "$OUT" <<'PY'
import sys, zipfile, glob, os
out = sys.argv[1]
with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
    for f in sorted(glob.glob("results/*")):
        z.write(f, "seizelut_results/" + os.path.basename(f))
    for f in ("seizelut_regs.json",):
        if os.path.exists(f):
            z.write(f, "seizelut_results/" + f)
print("written", out)
PY
ls -l "$OUT"
echo "Copy it to the PC (PowerShell on the PC):  scp ubuntu@<board-ip>:~/seizelut_results.zip ."
