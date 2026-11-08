# Tier-2 ablations against their own base (inner folds, per patient, best-F1 operating points)

Mean per-patient difference with a bootstrap 95 % interval (patients resampled) and the paired Wilcoxon p-value. A method is kept if p < 0.05 in its favour (Section 6.6).

| Config | Base | Event-F1 (diff vs base) | mean dF1 [95 % CI] | p (F1) | mean dFP/24h [95 % CI] | p (FP/24h) | d est. LUTs |
|---|---|---|---|---|---|---|---|
| n1_stack5_sel | dwn_L50_b8_lgbm40_e15bg10 | 0.217 (+0.006) | +0.006 [-0.041, +0.049] | 0.254 | -0.3 [-1.3, +0.5] | 0.805 | +478 |
| n1_stateful_sel | dwn_L50_b8_lgbm40_e15bg10 | 0.192 (-0.019) | -0.019 [-0.066, +0.026] | 0.662 | -1.3 [-3.0, -0.3] | 0.0127 | +8 |
| n5_mil | dwn_L50_b8_lgbm40_e15bg10 | 0.212 (+0.000) | +0.000 [-0.038, +0.037] | 0.907 | -0.6 [-2.3, +0.6] | 0.106 | -13 |
| n5_onset | dwn_L50_b8_lgbm40_e15bg10 | 0.191 (-0.021) | -0.021 [-0.058, +0.016] | 0.282 | -1.1 [-2.6, -0.0] | 0.0139 | -13 |
| n6_dropout | dwn_L50_b8_lgbm40_e15bg10 | 0.188 (-0.023) | -0.023 [-0.066, +0.019] | 0.233 | -0.5 [-1.9, +0.4] | 0.44 | -19 |
| n6_eeg_only | dwn_L50_b8_lgbm40_e15bg10 | 0.166 (-0.045) | -0.045 [-0.096, +0.003] | 0.0839 | +1.2 [-0.3, +2.5] | 0.00139 | +109 |
| n6_gated | dwn_L50_b8_lgbm40_e15bg10 | 0.201 (-0.010) | -0.010 [-0.062, +0.038] | 0.921 | -0.9 [-2.3, +0.0] | 0.113 | -32 |
| n6_late | dwn_L50_b8_lgbm40_e15bg10 | 0.134 (-0.077) | -0.077 [-0.125, -0.027] | 0.000631 | -1.9 [-3.6, -0.8] | 4.1e-09 | +173 |
