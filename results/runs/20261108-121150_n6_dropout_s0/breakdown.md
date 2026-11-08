# 20261108-121150_n6_dropout_s0: breakdown (inner folds, best-F1 operating point: gate none, k 10)

## Sensitivity by seizure type (alarm within [onset - 30 s, end + 60 s])

| Class | Seizures | Detected | Sensitivity |
|---|---|---|---|
| FIA | 289 | 48 | 0.166 |
| FA | 274 | 23 | 0.084 |
| focal_unknown_awareness | 101 | 10 | 0.099 |
| FBTC | 33 | 25 | 0.758 |
| unknown_onset | 1 | 0 | 0.000 |

## Missing modalities at test time (same operating point)

| Condition | Event-F1 | Sens | Prec | FP/24h | median dF1 vs intact | p |
|---|---|---|---|---|---|---|
| intact | 0.188 | 0.275 | 0.233 | 1.9 | - | - |
| no_ecg | 0.172 | 0.215 | 0.229 | 1.2 | +0.000 | 0.59 |
| no_emg | 0.190 | 0.285 | 0.226 | 1.8 | +0.000 | 0.893 |
| no_mov | 0.192 | 0.292 | 0.237 | 2.7 | +0.000 | 0.873 |
| eeg_only | 0.112 | 0.149 | 0.133 | 1.1 | +0.000 | 0.0011 |
