# 20261107-125159_chrononet_official_s1: 778 recordings, 29 subjects

## SeizeIT2-paper metrics (threshold 0.5)

| | Sens OVLP (%) | FA/h | AUROC | AUPR | score |
|---|---|---|---|---|---|
| published (chrononet) | 84.2 | 100.5 | 0.7921 | 0.1042 | |
| ours, as published | 74.5 | 22.6 | 0.7412 | 0.0044 | -194.7 |
| ours, corrected | 65.4 | 15.2 | 0.7041 | 0.0043 | -135.9 |

FA/h here is the any-overlap false-alarm rate (FP events per hour); the epoch-based rate is 503.4 (as published). The paper does not say which one Table 2 uses.

AUROC/AUPR above pool every 1 s epoch of all recordings. Per recording, then the mean over the 90 recordings with a seizure: AUROC 0.6799, AUPR 0.1088 (as published); 0.6421, 0.0926 (corrected). The paper does not say which one either.

## SzCORE (official post-processing, threshold 0.5; not comparable with the table above)

| Sensitivity | Precision | F1 | FP/24h | sample F1 |
|---|---|---|---|---|
| 0.867 | 0.019 | 0.032 | 154.0 | 0.010 |
