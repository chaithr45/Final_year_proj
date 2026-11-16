#!/usr/bin/env bash
# Phase 1 step 5 (MS_SPEC.md 1.2): the subset sweeps, one modality at a time, 5 impairment seeds, with the
# seed-0 fold models (D-MS4). Run only after the D-MS10 deltas are written in MS_SPEC.md (deltas.json committed).
# Resumable: finished jobs are skipped. Then the limits table and one figure per modality.
set -euo pipefail
cd "$(dirname "$0")/../.."
PY=${PY:-python}
WORKERS=${WORKERS:-4}
test -s ms/results/phase1/deltas.json || { echo "deltas.json missing: run ms/py/run_phase1_deltas.sh first"; exit 1; }
git log --oneline -1 -- ms/results/phase1/deltas.json | grep -q . || { echo "deltas.json not committed yet"; exit 1; }
MODELS=$(ls -d cache/ms/cv_s0/checkpoints/*_n4_distill_s0 | head -1)
for g in ${GRIDS:-eeg ecg emg mov}; do
  $PY ms/py/sweep.py --models "$MODELS" --grid "$g" --seeds 0 1 2 3 4 --workers "$WORKERS" --batch 12
done
$PY ms/py/tolerance.py
for g in ${GRIDS:-eeg ecg emg mov}; do $PY ms/py/plot_tolerance.py "$g"; done
