#!/usr/bin/env bash
# Phase 1, step 7 and 7b on all training hours (about 1-2 days on 4 CPUs; every step resumes after an interruption):
#   1. full-data confirmation of every subset limit and first failing level (confirm_full.py --jobs limits, seed 0);
#   2. the step-down rule (LOG L20): full_spec.py, then confirm_full.py --jobs stepdown, repeated until no family is
#      pending;
#   3. the combined spec point from the confirmed limits and its back-off (LOG L21): on the subset (5 seeds), then
#      on the full data (seed 0).
# Stops on the first error, including a clean run that does not reproduce the cached features or the CV result.
set -euo pipefail
cd "$(dirname "$0")/../.."
PY=${PY:-python}
WORKERS=${WORKERS:-4}
MODELS=$(ls -d cache/ms/cv_s0/checkpoints/*_n4_distill_s0 | head -1)
echo "== 1. full-data confirmation of the subset limits  $(date -u)"
$PY ms/py/confirm_full.py --models "$MODELS" --jobs limits --seeds 0 --workers "$WORKERS"
for round in 1 2 3 4 5 6 7 8 9 10; do
  echo "== 2. step-down round $round  $(date -u)"
  $PY ms/py/full_spec.py > cache/ms/full_spec.out; cat cache/ms/full_spec.out
  if grep -q "^0 families pending" cache/ms/full_spec.out; then break; fi
  $PY ms/py/confirm_full.py --models "$MODELS" --jobs stepdown --seeds 0 --workers "$WORKERS"
done
grep -q "^0 families pending" cache/ms/full_spec.out || { echo "step-down did not settle"; exit 1; }
echo "== 3a. combined spec point and back-off, subset  $(date -u)"
$PY ms/py/combined_backoff.py --models "$MODELS" --data subset --workers "$WORKERS"
echo "== 3b. combined spec point, full data  $(date -u)"
$PY ms/py/combined_backoff.py --models "$MODELS" --data full --workers "$WORKERS"
$PY ms/py/spec_table.py
echo "== done  $(date -u)"
