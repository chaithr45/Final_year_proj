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
- Causal context model (`v2_ctx_causal_s0`): AUROC 0.868, **F1 0.332** (v1 LightGBM 0.292), paper sens@0.5 0.251,
  @1 0.321, @2 0.567, @5 0.730, @10 0.807. Better F1 and low-budget sensitivity; worse than LightGBM at 5-10 FA/h.
  Top features: lgbm 10-s past mean, EEG theta 10 s vs past 5 min, xgb 10-s mean, dwn/cat relative to the past 30 min.
- LightGBM at 10 FA/h: the 5 % alarm-time cap binds (0.844 at 9.9 FA/h with 5.2 % on; 0.852 at 10.9 FA/h).
- WP4 breakdown, LightGBM at its 10 FA/h point (pooled over seizures, 698): FBTC 33/33, FIA 0.789, FA 0.672,
  seizures >= 60 s 0.947, 20-60 s 0.842, < 20 s 0.432; awake 0.828, asleep 0.596.
- Harness: optional device refractory period (`gap`): after an alarm fires, alarm runs starting within `gap` s join
  that alarm event; detection still needs a raw alarm second inside the seizure (no gap filling).
- Refractory sweep, LightGBM (paper sens at 0.1/0.5/1/2/5/10 FA/h): gap 0: .167/.246/.297/.593/.758/.832;
  30 s: .177/.246/.308/.632/.788/.832; 60 s: .177/.254/.323/.677/.807/.832; 120 s: .189/.279/.555/.677/.832/.832;
  300 s: .195/.345/.593/.758/.832/.832. The 5 % alarm-time cap fixes the ceiling at 0.832.
- **Patient-relative LightGBM base (`v2_base_rel_s0`, 252 features): AUROC 0.887** (best so far; v1 LightGBM 0.870),
  F1 0.326, paper sens@0.1 0.310, @0.5 0.423, @1 0.488, @2 0.578, @5 0.700, @10 0.832. Large gain at <= 1 FA/h.
- Refractory sweep, context model (causal): 30 s .164/.257/.371/.618/.739/.807; 60 s .171/.280/.433/.618/.764/.807;
  120 s .171/.321/.496/.642/.792/.807; 300 s .207/.390/.532/.672/.807/.807.
- Refractory sweep, patient-relative base: 60 s .316/.457/.523/.608/.763/.832; 120 s .316/.473/.549/.637/.810/.832;
  300 s **.336/.488/.568/.678/.832/.832** (best at <= 2 FA/h of all runs so far).
- Started: context model stacked on rel + v1 bases (`ctx_rel`); blend LightGBM + rel (log-odds mean) at gap 120.
- **Blend LightGBM + rel (equal log-odds mean, no fitting), refractory 120 s: AUROC 0.890, F1 0.363** (best so far;
  v1 LightGBM 0.292), paper sens .274/.420/.506/.674/**.841**/.841 at 0.1/0.5/1/2/5/10 FA/h. Best 5 FA/h point yet.
  Same blend, refractory 300 s: .305/.455/.574/.749/.841/.841 (5 % alarm-time cap binds at 0.841).
- Failed: context model stacked on rel + v1 bases (`v2_ctx_rel_s0`): AUROC 0.867, F1 0.341, paper sens
  .175/.303/.394/.563/.717/.797 (gap 0). Below the plain blend on every measure; stacking with a trained stage 2
  loses ranking quality (AUROC 0.867 < 0.887 of its own best input). Dropped.
- Blend lgbm 1 + rel 2 + cat 0.5 + xgb 0.5, refractory 300 s: AUROC 0.890, F1 0.364, paper sens
  .305/.460/.587/.746/.837/.837. Same as the two-model blend within noise; the extra members add nothing.
- Started: larger patient-relative LightGBM (seed 1, 900 trees, 127 leaves, lr 0.04) as a second blend member.
- Larger patient-relative LightGBM (`v2_base_rel_big_s1`): AUROC 0.886, F1 0.352, paper sens (gap 0)
  .305/.421/.484/.560/.715/.816. Higher F1 than the default size (0.326), similar curve.
- Blend lgbm + rel + rel_big (equal), refractory 300 s: AUROC 0.892, F1 0.363, paper sens
  .325/.468/.573/.729/.844/.844. Within noise of the two-model blend.
- Alarm-time cap (blend lgbm+rel, refractory 300 s; the 5 % cap is our own guard, not part of the paper metric):
  best sens within 5 FA/h is 0.838 (cap 5 %), **0.860 (cap 6 %: k 10, 4.05 FA/h, alarm on 5.5 % of the time)**,
  0.885 (cap 8 %: k 10, 4.72 FA/h, 7.8 % on), 0.894 (cap 10 %, k 4, 5.08 FA/h, 8.8 % on). At <= 2 FA/h the cap
  does not bind (0.750 at 2 FA/h). So 85 % within 5 FA/h is reached only if the alarm may be on 5.5 % of the time.
- WP4 breakdown, blend lgbm+rel at its 5 FA/h point (refractory 300 s; pooled over 698 seizures): all 0.755
  (LightGBM at 10 FA/h: 0.729), FBTC 33/33, FIA 0.792, FA 0.726, focal unknown awareness 0.653; >= 60 s 0.947,
  20-60 s 0.825, < 20 s 0.514 (was 0.432); awake 0.826, asleep 0.656 (was 0.596).
