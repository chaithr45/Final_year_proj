#!/usr/bin/env bash
# Run inner-CV configs one after another, logging each to results/queue_<date>.log.
#   scripts/run_queue.sh configs/m4/lgbm.yaml configs/m4/xgb.yaml ...
#   DEVICE=cpu scripts/run_queue.sh ...   overrides the configs' torch device
# Resumable: a config whose name already has a complete run (metrics.json, no in-progress
# .gitignore, not *_invalid) under results/runs/ is skipped, so the same command can be
# re-issued after a crash or container restart. FORCE=1 disables the skip.
set -uo pipefail
cd "$(dirname "$0")/.."
LOG=results/queue_$(date +%Y%m%d-%H%M%S).log
done_already() {
  local name d
  name=$(sed -n 's/^name:[[:space:]]*//p' "$1" | head -1)
  [ -n "$name" ] || return 1
  for d in results/runs/*_"${name}"_s*; do
    [ -d "$d" ] && [ -f "$d/metrics.json" ] && [ ! -e "$d/.gitignore" ] && [[ "$d" != *_invalid ]] && return 0
  done
  return 1
}
for cfg in "$@"; do
  if [ -z "${FORCE:-}" ] && done_already "$cfg"; then
    echo "=== $(date -Is) $cfg already complete, skipped" | tee -a "$LOG"; continue
  fi
  echo "=== $(date -Is) $cfg" | tee -a "$LOG"
  python scripts/run_inner_cv.py --config "$cfg" ${DEVICE:+--device "$DEVICE"} 2>&1 | grep -E "^(fold|RESULT|run dir|  fold|  MI|  hard)" | tee -a "$LOG"
done
echo "=== $(date -Is) queue done" | tee -a "$LOG"
