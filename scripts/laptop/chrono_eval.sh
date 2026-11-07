#!/usr/bin/env bash
# Test-patient predictions and scores of a trained ChronoNet run (reproduction of the published
# baseline; every test access is logged in the run directory).
#   scripts/laptop/chrono_eval.sh [config name]      default: chrononet_official
# Waits until no training of that config is running and a finished run (selected_epoch.json) exists, so it can be
# started while training is still running. Resumable: predictions already written are skipped,
# and a run that already has metrics.json is not scored again.
set -euo pipefail
cd "$(dirname "$0")/../.."
name=${1:-chrononet_official}
# newest finished run (an abandoned, never-trained run directory is ignored); wait while training runs
finished() { for d in $(ls -d results/runs/*_"$name"_s* 2>/dev/null | sort -r); do
  [ -f "$d/selected_epoch.json" ] && { echo "$d"; return; }; done; }
while pgrep -f "chrononet_train.py --config configs/baselines/$name.yaml" >/dev/null || [ -z "$(finished)" ]; do
  echo "$(date +%H:%M) waiting for $name training to finish"
  sleep 300
done
run=$(finished)
if [ -f "$run/metrics.json" ]; then
  echo "$run already scored"; exit 0
fi
echo "predicting and scoring $run"
python scripts/baselines/chrononet_predict.py --run "$run" --final-test --device cuda
python scripts/baselines/evaluate_predictions.py --run "$run" --final-test
