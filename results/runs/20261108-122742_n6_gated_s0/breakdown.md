# 20261108-122742_n6_gated_s0: breakdown (inner folds, best-F1 operating point: gate none, k 10)

## Sensitivity by seizure type (alarm within [onset - 30 s, end + 60 s])

| Class | Seizures | Detected | Sensitivity |
|---|---|---|---|
| FIA | 289 | 44 | 0.152 |
| FA | 274 | 26 | 0.095 |
| focal_unknown_awareness | 101 | 6 | 0.059 |
| FBTC | 33 | 28 | 0.848 |
| unknown_onset | 1 | 0 | 0.000 |

## Missing modalities at test time (same operating point)

| Condition | Event-F1 | Sens | Prec | FP/24h | median dF1 vs intact | p |
|---|---|---|---|---|---|---|
| intact | 0.201 | 0.287 | 0.241 | 1.5 | - | - |
| no_ecg | 0.125 | 0.182 | 0.176 | 1.3 | +0.000 | 0.000721 |
| no_emg | 0.198 | 0.295 | 0.261 | 1.8 | +0.000 | 0.489 |
| no_mov | 0.196 | 0.362 | 0.210 | 4.7 | +0.000 | 0.585 |
| eeg_only | 0.129 | 0.223 | 0.143 | 3.2 | +0.000 | 0.00388 |
