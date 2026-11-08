#!/usr/bin/env bash
# The laptop's share of the Section 6.1 DWN sweep (decision D32): the 21 configs with >= 500 LUTs
# except dwn_L500_b8_learn and dwn_L500_b16_learn, which run on the cloud. Builds the feature cache
# of the 96 training patients first (the inner folds never read the test patients; streams from S3,
# resumable: runs already cached are skipped), checks it against the M1 audit, then trains on the
# GPU, most informative configs first. Start it with
#   scripts/laptop/start.sh sweep
set -euo pipefail
cd "$(dirname "$0")/../.."
python scripts/extract_features.py --workers 3 --split train
python scripts/verify_feature_cache.py --split train
python scripts/make_dwn_sweep.py
names=(
  dwn_L1000_b8_learn dwn_L1000_b16_learn dwn_L2000_b8_learn dwn_L2000_b16_learn
  dwn_L500_b8_learn_n4 dwn_L500_b8_learn_n5 dwn_L500_b8_learn_t1 dwn_L500_b8_learn_t10 dwn_L500x100_b8_learn
  dwn_L500_b8_rando dwn_L500_b16_rando dwn_L1000_b8_rando dwn_L1000_b16_rando dwn_L2000_b8_rando dwn_L2000_b16_rando
  dwn_L500_b4_learn dwn_L500_b4_rando dwn_L1000_b4_learn dwn_L1000_b4_rando dwn_L2000_b4_learn dwn_L2000_b4_rando
)
cfgs=()
for n in "${names[@]}"; do cfgs+=("configs/m4/sweep/$n.yaml"); done
scripts/run_queue.sh "${cfgs[@]}"
