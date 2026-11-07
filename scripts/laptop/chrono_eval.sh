#!/usr/bin/env bash
# Test-patient predictions and scores of a trained ChronoNet run (reproduction of the published
# baseline; every test access is logged in the run directory).
#   scripts/laptop/chrono_eval.sh [config name]      default: chrononet_official
# Waits for the newest training run of that config to finish (selected_epoch.json), so it can be
# started while training is still running. Resumable: predictions already written are skipped,
# and a run that already has metrics.json is not scored again.
set -euo pipefail
cd "$(dirname "$0")/../.."
name=${1:-chrononet_official}
latest() { ls -d results/runs/*_"$name"_s* 2>/dev/null | sort | tail -1; }
while :; do
  run=$(latest)
  [ -n "$run" ] && [ -f "$run/selected_epoch.json" ] && break
  echo "$(date +%H:%M) waiting for $name training to finish (${run:-no run yet})"
  sleep 300
done
if [ -f "$run/metrics.json" ]; then
  echo "$run already scored"; exit 0
fi
echo "predicting and scoring $run"
python scripts/baselines/chrononet_predict.py --run "$run" --final-test --device cuda
python scripts/baselines/evaluate_predictions.py --run "$run" --final-test
