# 20261108-155851_n46_distill_dropout_s0: breakdown (inner folds, best-F1 operating point: gate none, k 8)

## Sensitivity by seizure type (alarm within [onset - 30 s, end + 60 s])

| Class | Seizures | Detected | Sensitivity |
|---|---|---|---|
| FIA | 289 | 36 | 0.125 |
| FA | 274 | 33 | 0.120 |
| focal_unknown_awareness | 101 | 4 | 0.040 |
| FBTC | 33 | 23 | 0.697 |
| unknown_onset | 1 | 0 | 0.000 |

## Missing modalities at test time (same operating point)

| Condition | Event-F1 | Sens | Prec | FP/24h | median dF1 vs intact | p |
|---|---|---|---|---|---|---|
| intact | 0.195 | 0.251 | 0.248 | 1.4 | - | - |
| no_ecg | 0.124 | 0.138 | 0.167 | 0.8 | +0.000 | 0.0082 |
| no_emg | 0.168 | 0.246 | 0.216 | 1.8 | +0.000 | 0.0825 |
| no_mov | 0.181 | 0.292 | 0.208 | 2.9 | +0.000 | 0.563 |
| eeg_only | 0.131 | 0.161 | 0.151 | 0.9 | +0.000 | 0.00731 |
