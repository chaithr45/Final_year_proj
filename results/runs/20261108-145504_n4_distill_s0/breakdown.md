# 20261108-145504_n4_distill_s0: breakdown (inner folds, best-F1 operating point: gate none, k 10)

## Sensitivity by seizure type (alarm within [onset - 30 s, end + 60 s])

| Class | Seizures | Detected | Sensitivity |
|---|---|---|---|
| FIA | 289 | 38 | 0.131 |
| FA | 274 | 29 | 0.106 |
| focal_unknown_awareness | 101 | 4 | 0.040 |
| FBTC | 33 | 26 | 0.788 |
| unknown_onset | 1 | 0 | 0.000 |

## Missing modalities at test time (same operating point)

| Condition | Event-F1 | Sens | Prec | FP/24h | median dF1 vs intact | p |
|---|---|---|---|---|---|---|
| intact | 0.229 | 0.267 | 0.303 | 0.9 | - | - |
| no_ecg | 0.055 | 0.057 | 0.084 | 0.2 | +0.000 | 6.35e-07 |
| no_emg | 0.189 | 0.206 | 0.254 | 0.7 | +0.000 | 0.0474 |
| no_mov | 0.150 | 0.252 | 0.188 | 4.7 | +0.000 | 0.00431 |
| eeg_only | 0.082 | 0.098 | 0.111 | 0.4 | +0.000 | 1.28e-05 |
