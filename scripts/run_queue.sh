#!/usr/bin/env bash
# Run inner-CV configs one after another, logging each to results/queue_<date>.log.
#   scripts/run_queue.sh configs/m4/lgbm.yaml configs/m4/xgb.yaml ...
set -uo pipefail
cd "$(dirname "$0")/.."
LOG=results/queue_$(date +%Y%m%d-%H%M%S).log
for cfg in "$@"; do
  echo "=== $(date -Is) $cfg" | tee -a "$LOG"
  python scripts/run_inner_cv.py --config "$cfg" 2>&1 | grep -E "^(fold|RESULT|run dir|  fold|  MI|  hard)" | tee -a "$LOG"
done
echo "=== $(date -Is) queue done" | tee -a "$LOG"
