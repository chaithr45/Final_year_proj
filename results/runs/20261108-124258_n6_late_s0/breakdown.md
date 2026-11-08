# 20261108-124258_n6_late_s0: breakdown (inner folds, best-F1 operating point: gate none, k 10)

## Sensitivity by seizure type (alarm within [onset - 30 s, end + 60 s])

| Class | Seizures | Detected | Sensitivity |
|---|---|---|---|
| FIA | 289 | 17 | 0.059 |
| FA | 274 | 6 | 0.022 |
| focal_unknown_awareness | 101 | 1 | 0.010 |
| FBTC | 33 | 17 | 0.515 |
| unknown_onset | 1 | 0 | 0.000 |

## Missing modalities at test time (same operating point)

| Condition | Event-F1 | Sens | Prec | FP/24h | median dF1 vs intact | p |
|---|---|---|---|---|---|---|
| intact | 0.134 | 0.156 | 0.180 | 0.6 | - | - |
| no_ecg | 0.070 | 0.069 | 0.106 | 0.1 | +0.000 | 0.000883 |
| no_emg | 0.012 | 0.011 | 0.016 | 0.0 | +0.000 | 3.34e-05 |
| no_mov | 0.056 | 0.050 | 0.099 | 0.1 | +0.000 | 0.00119 |
| eeg_only | 0.000 | 0.000 | 0.000 | 0.0 | +0.000 | 5.47e-06 |
