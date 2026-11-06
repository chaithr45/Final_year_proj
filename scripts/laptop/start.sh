#!/usr/bin/env bash
# Start a long GPU-laptop job in its own tmux session; the window stays open afterwards so the
# last output (or an error) can be read with `tmux attach -t <name>`. Output is also in logs/<name>.log.
#   scripts/laptop/start.sh feat     feature extraction (streams from S3)
#   scripts/laptop/start.sh chrono   ChronoNet (official protocol): data, then training on the GPU
#   scripts/laptop/start.sh sweep    DWN sweep on the inner folds (after `feat` + verify)
set -euo pipefail
cd "$(dirname "$0")/../.."
mkdir -p logs
if [[ "${1:-}" == feat || "${1:-}" == chrono ]] && [[ ! -d data/raw/ds005873/sub-125 ]]; then
  echo "dataset metadata missing: run  python scripts/fetch_metadata.py  first (a few minutes, ~100 MB)"; exit 1
fi
case "${1:-}" in
  feat)   cmd="python scripts/extract_features.py --workers 6 && python scripts/verify_feature_cache.py" ;;
  chrono) cmd="python scripts/baselines/chrononet_data.py --config configs/baselines/chrononet_official.yaml --final-test && python scripts/baselines/chrononet_train.py --config configs/baselines/chrononet_official.yaml --device cuda" ;;
  sweep)  cmd="python scripts/make_dwn_sweep.py && scripts/run_queue.sh configs/m4/sweep/*.yaml" ;;
  *) echo "usage: $0 feat|chrono|sweep"; exit 2 ;;
esac
cat > "logs/$1.sh" <<INNER
source "\$HOME/miniforge3/etc/profile.d/conda.sh"
conda activate seizelut
cd "$(pwd)"
( $cmd ) 2>&1 | tee -a "logs/$1.log"
echo "=== $1 finished (exit \${PIPESTATUS[0]}) \$(date) ===" | tee -a "logs/$1.log"
exec bash
INNER
tmux new-session -d -s "$1" "bash --rcfile logs/$1.sh"
echo "started '$1': watch with  tmux attach -t $1   (leave with Ctrl+B then D);  log: logs/$1.log"
