# 20261107-204035_chrononet_clean_s1: 778 recordings, 29 subjects

## SeizeIT2-paper metrics (threshold 0.5)

| | Sens OVLP (%) | FA/h | AUROC | AUPR | score |
|---|---|---|---|---|---|
| published (chrononet) | 84.2 | 100.5 | 0.7921 | 0.1042 | |
| ours, as published | 67.1 | 11.9 | 0.7455 | 0.0048 | -73.0 |
| ours, corrected | 62.2 | 8.7 | 0.7051 | 0.0047 | -45.5 |

FA/h here is the any-overlap false-alarm rate (FP events per hour); the epoch-based rate is 256.8 (as published). The paper does not say which one Table 2 uses.

AUROC/AUPR above pool every 1 s epoch of all recordings. Per recording, then the mean over the 90 recordings with a seizure: AUROC 0.6817, AUPR 0.1106 (as published); 0.6425, 0.0923 (corrected). The paper does not say which one either.

## SzCORE (official post-processing, threshold 0.5; not comparable with the table above)

| Sensitivity | Precision | F1 | FP/24h | sample F1 |
|---|---|---|---|---|
| 0.790 | 0.015 | 0.027 | 106.3 | 0.016 |
