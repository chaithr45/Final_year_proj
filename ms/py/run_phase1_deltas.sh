#!/usr/bin/env bash
# Phase 1 step 1, second half (MS_SPEC.md D-MS10): the seed spread of the clean result, measured before any sweep.
# Needs the 5 retrained CV runs (bash ms/py/run_phase1_folds.sh). For each seed: clean subset run with that seed's
# fold models (ms/results/phase1/sweeps/clean_models_s<seed>.jsonl); then the frozen-point metrics on all training
# hours (cv_frozen_op.py) and both spreads (deltas.py -> ms/results/phase1/deltas.json).
set -euo pipefail
cd "$(dirname "$0")/../.."
PY=${PY:-python}
WORKERS=${WORKERS:-4}
for s in 0 1 2 3 4; do
  run=$(ls -d cache/ms/cv_s$s/checkpoints/*_n4_distill_s$s | head -1)
  out=ms/results/phase1/sweeps/clean_models_s$s.jsonl
  if [ -s "$out" ]; then echo "seed $s clean subset done"; continue; fi
  $PY ms/py/sweep.py --models "$run" --grid clean --workers "$WORKERS" --out "$out"
done
$PY ms/py/cv_frozen_op.py cache/ms/cv_s0 cache/ms/cv_s1 cache/ms/cv_s2 cache/ms/cv_s3 cache/ms/cv_s4
$PY ms/py/deltas.py
