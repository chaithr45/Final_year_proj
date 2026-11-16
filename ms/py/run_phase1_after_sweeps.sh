#!/usr/bin/env bash
# Phase 1, the short steps after the four subset grids (run_phase1_sweeps.sh): the generator A/B (LOG L17) and the
# combined spec point on the subset (step 7b). About 1 h with 4 workers. Stops before the full-data confirmation
# (about 30 h, step 7), which is started by hand once both results have been read.
set -euo pipefail
cd "$(dirname "$0")/../.."
PY=${PY:-python}
WORKERS=${WORKERS:-4}
test -s ms/results/phase1/tolerance.json || { echo "tolerance.json missing: run ms/py/run_phase1_sweeps.sh first"; exit 1; }
MODELS=$(ls -d cache/ms/cv_s0/checkpoints/*_n4_distill_s0 | head -1)
echo "== generator A/B"
$PY ms/py/sweep.py --models "$MODELS" --grid gauss_ab --seeds 0 1 2 3 4 --workers "$WORKERS" --batch 12
$PY ms/py/gauss_ab.py
echo "== combined spec point (subset)"
$PY ms/py/combined.py
$PY ms/py/sweep.py --models "$MODELS" --grid combined --seeds 0 1 2 3 4 --workers "$WORKERS" --batch 12
$PY ms/py/combined.py --evaluate
echo "== done"
