# 20261108-082813_dwn_L50_b8_lgbm40_e15bg10_s0: breakdown (inner folds, best-F1 operating point: gate none, k 10)

## Sensitivity by seizure type (alarm within [onset - 30 s, end + 60 s])

| Class | Seizures | Detected | Sensitivity |
|---|---|---|---|
| FIA | 289 | 50 | 0.173 |
| FA | 274 | 26 | 0.095 |
| focal_unknown_awareness | 101 | 8 | 0.079 |
| FBTC | 33 | 29 | 0.879 |
| unknown_onset | 1 | 0 | 0.000 |

## Missing modalities at test time (same operating point)

| Condition | Event-F1 | Sens | Prec | FP/24h | median dF1 vs intact | p |
|---|---|---|---|---|---|---|
| intact | 0.211 | 0.315 | 0.246 | 2.4 | - | - |
| no_ecg | 0.092 | 0.108 | 0.134 | 0.8 | +0.000 | 2.4e-05 |
| no_emg | 0.199 | 0.269 | 0.262 | 1.6 | +0.000 | 0.641 |
| no_mov | 0.136 | 0.248 | 0.153 | 5.2 | +0.000 | 0.00424 |
| eeg_only | 0.074 | 0.109 | 0.107 | 1.4 | -0.049 | 2.23e-06 |
