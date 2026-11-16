#!/usr/bin/env bash
# Phase 1 step 1 (MS_SPEC.md D-MS4): retrain the frozen recipe's 5 inner-fold models for seeds 0..4.
# Needs the complete training feature cache (python scripts/extract_features.py --split train).
# Outputs (git-ignored, large): cache/ms/cv_s<seed>/{results/runs,cache/oof,checkpoints}/...
# Then: python ms/py/cv_frozen_op.py cache/ms/cv_s0 ... cache/ms/cv_s4
set -euo pipefail
cd "$(dirname "$0")/../.."
PY=${PY:-python}
$PY scripts/verify_feature_cache.py --split train        # aborts the chain if any cached run disagrees with the audit
for s in ${SEEDS:-0 1 2 3 4}; do
  out=cache/ms/cv_s$s
  if ls $out/results/runs/*/metrics.json >/dev/null 2>&1; then echo "seed $s done"; continue; fi
  $PY scripts/run_inner_cv.py --config configs/m5/n4_distill.yaml --seed $s --device cpu --out $out
done
