# Tier-2 ablations against their own base (inner folds, per patient, best-F1 operating points)

Mean per-patient difference with a bootstrap 95 % interval (patients resampled) and the paired Wilcoxon p-value. A method is kept if p < 0.05 in its favour (Section 6.6).

| Config | Base | Event-F1 (diff vs base) | mean dF1 [95 % CI] | p (F1) | mean dFP/24h [95 % CI] | p (FP/24h) | d est. LUTs |
|---|---|---|---|---|---|---|---|
| n1_stack5_sel | dwn_L50_b8_lgbm40_e15bg10 | 0.217 (+0.006) | +0.006 [-0.041, +0.049] | 0.254 | -0.3 [-1.3, +0.5] | 0.805 | +478 |
| n1_stateful_sel | dwn_L50_b8_lgbm40_e15bg10 | 0.192 (-0.019) | -0.019 [-0.066, +0.026] | 0.662 | -1.3 [-3.0, -0.3] | 0.0127 | +8 |
