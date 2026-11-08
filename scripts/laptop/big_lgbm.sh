#!/usr/bin/env bash
# The laptop's GPU share after D35 (replaces `sweep`, whose 21 configs use the mutual-information features
# that D34 replaced): finishes and checks the training feature cache (resumes: runs already cached are
# skipped), trains the large DWNs on the LightGBM-gain top 40 (sizes 500-2000, then the Section 6.1
# ablations at 500 LUTs), then the raw-EEG 1-D CNN and TCN, and sends the finished runs. Start it with
#   scripts/laptop/start.sh big
set -euo pipefail
cd "$(dirname "$0")/../.."
python scripts/extract_features.py --workers 3 --split train
python scripts/verify_feature_cache.py --split train
names=(
  dwn_L500_b8_lgbm40_e15bg10 dwn_L1000_b8_lgbm40_e15bg10 dwn_L2000_b8_lgbm40_e15bg10 dwn_L1000_b16_lgbm40_e15bg10
  dwn_L500_b8_lgbm40_e15bg10_n4 dwn_L500_b8_lgbm40_e15bg10_n5 dwn_L500_b8_lgbm40_e15bg10_t1
  dwn_L500_b8_lgbm40_e15bg10_t10 dwn_L500x100_b8_lgbm40_e15bg10
)
cfgs=()
for n in "${names[@]}"; do cfgs+=("configs/m4/$n.yaml"); done
scripts/run_queue.sh "${cfgs[@]}"
scripts/laptop/push_runs.sh || true
python scripts/run_inner_cv_raw.py --config configs/m4/raw_cnn_tcn.yaml --device cuda
scripts/laptop/push_runs.sh || true
