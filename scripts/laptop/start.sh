#!/usr/bin/env bash
# Start a long GPU-laptop job in its own tmux session; the window stays open afterwards so the
# last output (or an error) can be read with `tmux attach -t <name>`. Output is also in logs/<name>.log.
#   scripts/laptop/start.sh feat     feature extraction (streams from S3)
#   scripts/laptop/start.sh chrono   ChronoNet (official protocol): data, then training on the GPU
#   scripts/laptop/start.sh night    metadata fetch (resumable, retried once), then the whole chrono job
#   scripts/laptop/start.sh sweep    DWN sweep on the inner folds (after `feat` + verify)
# Every step resumes: re-running the same command after an interruption (window closed, laptop
# asleep or restarted) continues where it stopped instead of starting over.
set -euo pipefail
cd "$(dirname "$0")/../.."
mkdir -p logs
if [[ "${1:-}" == feat || "${1:-}" == chrono ]] && [[ ! -d data/raw/ds005873/sub-125 ]]; then
  echo "dataset metadata missing: run  python scripts/fetch_metadata.py  first (a few minutes, ~100 MB)"; exit 1
fi
case "${1:-}" in
  feat)   cmd="python scripts/extract_features.py --workers 6 && python scripts/verify_feature_cache.py" ;;
  chrono) cmd="python scripts/baselines/chrononet_data.py --config configs/baselines/chrononet_official.yaml --final-test && python scripts/baselines/chrononet_train.py --config configs/baselines/chrononet_official.yaml --device cuda --resume auto" ;;
  night)  cmd="(python scripts/fetch_metadata.py || python scripts/fetch_metadata.py) && python scripts/baselines/chrononet_data.py --config configs/baselines/chrononet_official.yaml --final-test && python scripts/baselines/chrononet_train.py --config configs/baselines/chrononet_official.yaml --device cuda --resume auto" ;;
  sweep)  cmd="python scripts/make_dwn_sweep.py && scripts/run_queue.sh configs/m4/sweep/*.yaml" ;;
  *) echo "usage: $0 feat|chrono|night|sweep"; exit 2 ;;
esac
# A session of the same name whose job has ended (only its shell is left) is replaced; a running one is kept.
if tmux has-session -t "$1" 2>/dev/null; then
  if [[ "$(tmux list-panes -t "$1" -F '#{pane_current_command}' | head -1)" == bash ]]; then
    tmux kill-session -t "$1"
  else
    echo "'$1' is still running: watch with  tmux attach -t $1   or  tail -n 3 logs/$1.log"; exit 0
  fi
fi
# The job is retried (every step resumes) up to 10 times if it stops with an error.
cat > "logs/$1.sh" <<INNER
source "\$HOME/miniforge3/etc/profile.d/conda.sh"
conda activate seizelut
cd "$(pwd)"
for attempt in 1 2 3 4 5 6 7 8 9 10; do
  ( $cmd ) 2>&1 | tee -a "logs/$1.log"
  rc=\${PIPESTATUS[0]}
  echo "=== $1 finished (exit \$rc) \$(date) ===" | tee -a "logs/$1.log"
  [ "\$rc" -eq 0 ] && break
  echo "=== retrying in 60 s (attempt \$attempt of 10) ===" | tee -a "logs/$1.log"
  sleep 60
done
exec bash
INNER
tmux new-session -d -s "$1" "bash --rcfile logs/$1.sh"
echo "started '$1': watch with  tmux attach -t $1   (leave with Ctrl+B then D);  log: logs/$1.log"
