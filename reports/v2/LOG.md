# SeizeLUT v2: work log (training patients only unless marked)

All numbers: patient-wise 5-fold CV on the 96 training patients, out-of-fold (OOF). "paper sens@X" = any-overlap
sensitivity (mean over recordings with a seizure) at <= X false-alarm events per hour (mean over recordings), alarm
on at most 5 % of the time, best of k in {1, 4, 10}. F1 = SzCORE event-F1 (mean over patients) at its best threshold,
k = 10. Source of every line: `results/v2/harness.json`.

## 28 Nov

- Harness (`scripts/v2/harness.py`) reproduces v1 exactly: final DWN F1 0.229, paper sens@10 0.742.
- v1 baselines:

| run | AUROC | F1 | sens@0.5 | sens@1 | sens@2 | sens@5 | sens@10 |
|---|---|---|---|---|---|---|---|
| DWN distilled (v1 final) | 0.851 | 0.229 | 0.301 | 0.402 | 0.470 | 0.641 | 0.742 |
| LightGBM | 0.870 | 0.292 | 0.246 | 0.297 | 0.593 | 0.758 | 0.832 |
| CatBoost | 0.863 | 0.286 | 0.232 | 0.277 | 0.337 | 0.713 | 0.815 |
| XGBoost | 0.867 | 0.277 | 0.194 | 0.215 | 0.275 | 0.750 | 0.818 |

- Started: context model, causal (`scripts/v2/context_model.py --mode causal`); patient-relative LightGBM base
  (`scripts/v2/base_model.py --feat rel`).
