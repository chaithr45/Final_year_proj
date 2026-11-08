# Decisions log

Every method, its fold scores, the keep/drop decision and the reason (Section 6.6).
Negative results stay here. Infrastructure decisions are logged too, so every
deviation from the master prompt is traceable.

Format: `D<n> | milestone | decision | why | evidence`.

## M1: repository setup and data audit

| ID | Decision | Why | Evidence |
|---|---|---|---|
| D1 | Work on branch `claude/optimistic-heisenberg-ph0bvj`, not `phase1-software` | The coding session is restricted to that branch; rename or merge it as you prefer | — |
| D2 | Own NumPy EDF/EDF+ reader (`src/data/edf.py`) instead of pyEDFlib/MNE | Keeps the raw int16 samples and the exact gain for the integer pipeline; parses headers from bytes, so all 11,009 headers were audited by range request | Bit-exact against pyEDFlib on real and synthetic files (`tests/test_edf.py`) |
| D3 | Windows defined in seconds and mapped to samples per file | Every biopotential file is 256 Hz, not 250 Hz; motion is 25 Hz | `reports/data_audit.md` §1–2 |
| D4 | Inner folds stratified by seizure-count bin only; seed picked from 500 for even seizure totals (137–143 per fold) | Centre labels are not in the public release | `configs/folds_inner5.json` |
| D5 | `impd` (impedance-check) events treated as background, as in the official code; 10 malformed `impd` events (5 negative, 5 zero duration) logged, not used | Follows the baseline; malformed rows cannot be interpreted | `reports/data_audit.md` §2 |
| D6 | Secondary result on "seizures visible on the wearable" not computable | `channels` and `confidence` columns are n/a for all 883 seizures | `results/audit/seizures.csv` |
| D7 | Python 3.12 for the research environment | `szcore-evaluation`, current NumPy and XGBoost need ≥ 3.12 | `environment.yml` |
| D8 | M2 reproduces the official artefact gate as written (`rmsa = rmsa_f and rmsa_c` gives only the cross channel) | Needed to match the published Table 2; our own models get a design decision in M3 | `reports/data_audit.md` §6 |
| D9 | Cite dataset v1.1.0 (DOI 10.18112/openneuro.ds005873.v1.1.0), not v1.0.0 | v1.1.0 corrected the accelerometer data and is what the bucket serves | `CHANGES` |

## Open questions for the user

* Centre and adult/child labels per patient: ask the dataset authors (blocks stratification by centre, leave-one-centre-out, and Table 5 breakdowns).
* Paper target: EMBC 2027 (full papers reportedly due 24 Jan 2027) vs BioCAS 2027 (call not out). See `reports/literature_check.md`.

## M2: baseline reproduction

| ID | Decision | Why | Evidence |
|---|---|---|---|
| D10 | Two metric families kept apart: SeizeIT2-paper metrics (as published and corrected) and SzCORE | Different tolerances, merging, units (per hour vs per day) and averaging unit (recording vs subject) | `src/eval/seizeit2.py`, `src/eval/szcore.py` |
| D11 | Official metric code ported literally, with switches for two defects (multi-counted any-overlap TPs; RMS gate on channel 2 only) | Needed to reproduce Table 2, and to report corrected numbers next to it | Port identical to the original on 900 random cases |
| D12 | ChronoNet ported to PyTorch (129,122 parameters, as Keras) instead of running the TensorFlow code | One framework for all models; same architecture, init, BN, loss and schedule | `tests/test_baselines.py` |
| D13 | Two ChronoNet protocols: "official" (best epoch by val score on the validation = test patients, as the released code does) and "clean" (last epoch) | The released code selects the epoch on the test patients; we reproduce it but flag it | `configs/baselines/` |
| D14 | Test-set guard: any script touching sub-097..125 needs `--final-test` and logs the access | Honesty rule 10.4 | `src/eval/runlog.py` |
| D15 | SVM baseline pending the 42-feature definition | The dataset paper (now read, `reports/seizeit2_paper_notes.md`) gives the SVM protocol but defers the features to Vandecasteele et al., Epilepsia 2020 (doi 10.1111/epi.16470), which is not reachable from the coding environment; C and kernel scale are not stated | Question for the user: that paper's feature table |

### M2 results (published baseline on the official test patients: reproduction only, every access logged in the run's `TEST_ACCESS.log`)

* **chrononet_official** (run `20261107-125159_chrononet_official_s1`, seed 1, epoch chosen by the val score on blocks
  around the test patients' seizures, as the released code does; 778 recordings, 29 patients). The rule picked
  epoch 8 of 300 (val score 94.9; it is 93-95 over the first 13 epochs and 84-86 from epoch 50 on).

  | | Sens OVLP (%) | FA/h (any-overlap) | AUROC (pooled) | AUPR (pooled) |
  |---|---|---|---|---|
  | published (Table 2) | 84.2 | 100.5 | 0.7921 | 0.1042 |
  | ours, as published | 74.5 | 22.6 | 0.7412 | 0.0044 |
  | ours, corrected | 65.4 | 15.2 | 0.7041 | 0.0043 |

  Epoch-based FA rate 503.4/h (as published); official score -194.7 (as published), -135.9 (corrected). SzCORE at
  threshold 0.5 on the baseline's own post-processing: sens 0.867, precision 0.019, F1 0.032, 154.0 FP/24 h, sample
  F1 0.010. These are test-patient numbers and are not comparable with the inner-CV results log below; our models
  meet this baseline only at M6, on the same 29 patients.

  **Not reproduced.** Sensitivity is 9.7 points lower and AUROC 0.051 lower; AUPR is 24 times lower; the published
  FA/h (100.5) lies between our any-overlap rate (22.6) and our epoch-based rate (503.4), so it matches neither
  definition. Seizure time is 0.123% of all EEG time (M1 audit), so our pooled AUPR is about 3-4 times chance, while
  0.104 would be about 85 times chance; with the FA/h mismatch this points first at metric definitions the paper does
  not state. Next: (1) AUROC/AUPR per recording, then the mean over recordings with a seizure (added to
  `evaluate_predictions.py`; this run is re-scored from its saved predictions, no retraining); (2) the clean run
  (last epoch, no selection on test patients) for the leak-free number; (3) untested candidate causes: one seed
  (the paper's seed count is not stated), the Keras-to-PyTorch port (D12), and the dataset version (OpenNeuro
  ds005873 today vs. the paper's copy; the files hold 883 seizures, 181 in the test split, against the 886 and
  182 the paper reports; this sentence first had the two counts swapped, corrected 8 Nov).
  The baseline is reported as measured, with the published numbers beside it and this gap stated.
* **Per-recording AUROC/AUPR** (the official run re-scored from its saved predictions on 8 Nov, no retraining): mean
  over the 90 test recordings with a seizure, AUROC 0.680 and AUPR 0.109 as published (0.642 and 0.093 corrected).
  The per-recording AUPR is within 0.005 of the published 0.1042, which is consistent with Table 2's AUPR being a
  per-recording mean; AUROC fits neither reading (0.680 per recording, 0.741 pooled, 0.792 published). What remains
  unexplained: sensitivity (74.5 vs 84.2), AUROC, and the FA/h definition.
* **chrononet_clean** (run `20261107-204035_chrononet_clean_s1`, same seed and training data, last of 300 epochs; no
  test-patient information used in training, test access = predictions and scoring only):

  | | Sens OVLP (%) | FA/h (any-overlap) | AUROC (pooled) | AUPR (pooled) |
  |---|---|---|---|---|
  | ours, as published | 67.1 | 11.9 | 0.7455 | 0.0048 |
  | ours, corrected | 62.2 | 8.7 | 0.7051 | 0.0047 |

  Epoch-based FA rate 256.8/h; official score -73.0 (as published), -45.5 (corrected). SzCORE at threshold 0.5: sens
  0.790, precision 0.015, F1 0.027, 106.3 FP/24 h, sample F1 0.016. Per recording (90 recordings with a seizure):
  AUROC 0.682, AUPR 0.111 as published (0.643 and 0.092 corrected), again close to the published AUPR. Against the official run: 7.4 points less sensitivity for about half the false
  alarms (11.9 vs 22.6 per hour any-overlap, 257 vs 503 epoch-based) and slightly higher pooled AUROC and AUPR. The
  official selection score (100 x event sensitivity - 0.4 x false-positive fraction on seizure blocks) rewards
  over-prediction and chose an early epoch. **Decision: chrononet_clean is the ChronoNet row our models are compared
  with at M6** (it used no test information); the official run is reported only as the reproduction of the
  published protocol.

## M3: integer feature pipeline

| ID | Decision | Why | Evidence |
|---|---|---|---|
| D16 | Inputs: int16 at 0.25 uV/LSB (biopotentials), 2^-12 unit/LSB (motion), converted by the replay software | Max |signal| in the data is 6,665 uV; 0.1 uV/LSB would saturate | `spec/fixed_point.md` |
| D17 | 2 s windows = two 1 s block accumulators (512 samples at 256 Hz, means are shifts) | Hardware-friendly, causal | `src/features/golden.py` |
| D18 | Biquads with second-order error feedback | Plain rounding gave an error std of 140 LSB on the 0.5 Hz high-pass (signal std 61); error feedback 0.7 LSB | `tests/test_features.py` |
| D19 | Structure-preserving coefficient quantisation (b = b0 (1, +/-2, 1)) | Independent rounding moved the low-pass zeros off Nyquist (stopband floor -55 dB) | `spec/fixed_point.md` §2 |
| D20 | Artefact flag = MAV of the official 0.5-60 Hz + notch signal against RMS limits x sqrt(2/pi) | No squares or square roots; agrees with the float RMS rule on 99.6 % / 93.5 % of windows (sub-001 run-01) | M3 check |
| D21 | Artefact flags are features, and the post-processing gate (none / both / any) is chosen on the inner folds | The official 13 uV floor flags 69 % of windows on the same-side channel | `src/eval/operating.py` |
| D22 | ECG heart rate as log2(mean RR) from integer R-peak timestamps; no division | Multiplier/divider-free | `src/features/golden.py` |
| D23 | Training-only 0.5 s-hop seizure augmentation deferred | The cache is on a 1 s block grid; augmentation needs a second extraction at 0.5 s blocks; to be ablated in M5 | - |

## M4/M5: model comparison (inner folds only)

| ID | Decision | Why | Evidence |
|---|---|---|---|
| D24 | Own pure-PyTorch DWN instead of torch-dwn | torch-dwn's EFD operator is CUDA-only (no CPU, hard on Windows); ours matches its CUDA kernel exactly | `tests/test_dwn.py` |
| D25 | Feature selection by mutual information inside each fold's training patients | Avoids leaking validation patients into the ranking | `scripts/run_inner_cv.py` |
| D26 | Operating points chosen on pooled out-of-fold predictions of the 96 training patients | Thresholds are fixed before any test-set scoring | `src/eval/operating.py` |
| D27 | Large DWN sweeps (Section 6.1 grid) run on the user's GPU; CPU runs use top-40 features and <= 200 LUTs | 4-core CPU: ~4 min per million windows per epoch at 200 LUTs with learnable mapping | `reports/LAPTOP_RUNBOOK.md` |
| D28 | A run whose ECG lead is present but yields no detected R-peak (sub-089 run-01, 3,250 s) is kept; its ECG features are 0 and flagged `quality_bad` every window | The extractor crashed on an empty beat list; dropping the run would silently remove training data | `src/features/golden.py` |
| D29 | TreeLUT scores are reported in logit units (integer leaf sum / leaf scale + offset; the hardware compares the integer sum with the matching integer threshold); run `20261106-180609_treelut_s0` is marked invalid and re-run as `treelut_w3/4/5` | Each fold's integer sum had its own scale and offset, so pooled out-of-fold AUROC (0.601) and the shared threshold were meaningless. On a 30/10-patient check the 8-bit-leaf integer score matched float XGBoost (AUROC 0.886 vs 0.885); 3-bit leaves lost 0.04-0.09, 4-5 bits recovered it, so `w_tree` is tuned on the inner folds | `src/models/registry.py` |
| D30 | Downloads are checked against Content-Length, extraction refuses EDFs whose size disagrees with the header, and `scripts/verify_feature_cache.py` checks every cached run against the M1 audit durations; the first LGBM, LR and partial XGB runs are marked `_invalid` and re-run | The float-twin comparison exposed sub-020 run-01 with ECG cut at 51,855 of 71,835 s. The verifier then found 9 runs (7 training, 2 test) silently truncated by short S3 reads, two of them in EEG (sub-078 run-30 had 12 of 16,363 windows). All 9 were re-extracted; all 2,850 runs now agree with the audit. 51 runs whose only motion sensor is the head (EEG) module have no motion features by design (chest module only) | `src/data/remote.py`, `scripts/extract_features.py`, `scripts/verify_feature_cache.py` |
| D31 | For stacked (multi-window) inputs, mutual information ranks the base features on the current window and every lag of the top 40 is kept (`features: {mi_top: 40, mi_on: base}`); `n1_stack5` is kept in the log as the failed variant | Ranking the 585 stacked columns directly chose lagged copies of only 11 to 13 distinct features per fold, fewer than the 40 the single-window DWN sees, and `n1_stack5` fell to AUROC 0.750 / F1 0.103 against 0.821 / 0.167. The hardware cost model counts one comparator set per stacked column, an over-estimate when lags share comparators through a delay line | `scripts/run_inner_cv.py`, `configs/m5/n1_stack5_base.yaml`, run `20261107-010416_n1_stack5_s0` |
| D32 | The Section 6.1 sweep is split: the cloud CPU runs the <= 200-LUT grid plus `dwn_L500_b8_learn` and `dwn_L500_b16_learn`; the laptop GPU runs the other 21 configs (>= 500 LUTs), most informative first | On the 4-core cloud a 200-LUT config takes about 2.1 h and time grows roughly linearly with LUTs, so the 23 configs with >= 500 LUTs would need about a week there (D27 already assigns them to the GPU). The whole grid still runs; nothing is pruned | `scripts/laptop/sweep_big.sh` |
| D33 | Base DWN for M5: 50 LUT6 in one layer, 8-bit thermometer, learnable mapping, MI top-40 features (`configs/m4/sweep/dwn_L50_b8_learn.yaml`, about 880 estimated LUTs). Rule: the smallest size whose per-patient event-F1 is not significantly below the best <= 200-LUT config (paired Wilcoxon, p >= 0.05), at the bits and mapping the sweep favours | Among the five best <= 200-LUT configs (pooled F1 0.135-0.167) no pair differs per patient (p 0.15-0.97); 8 bits beat 4 (F1 p = 0.009 at 50 LUTs; FP/24 h lower at 50 and 100 LUTs, p < 1e-10) and 16 bits add false alarms over 8 without F1 gain (p < 1e-4); learnable mapping has fewer false alarms than random in 7 of 8 pairs (p < 0.01). A 50-LUT run takes about 30 min on the 4-core cloud against about 1.6-2 h at 200 LUTs, which makes the 18 Tier-2 variants feasible. If the >= 500-LUT runs (laptop) beat it per patient, the kept methods are re-run at that size | `results/tables/inner_cv.md`, `results/tables/inner_cv_tests.md` |
| D34 | Feature selection for the DWN family: top 40 by the gain importance of a LightGBM trained on each training set's windows (`features: {rank_by: lgbm, top: 40}`), replacing single-feature mutual information. The base DWN for M5 becomes dwn_L50_b8_lgbm40 (or its recipe variant, if that wins) | Same size and encoder: event-F1 0.208 vs 0.148, per-patient mean +0.060 [95 % CI +0.001, +0.119], p = 0.047; FP/24 h 2.3 vs 7.0 (median -0.9, p = 8e-07); AUROC 0.839 vs 0.819, AUPR 0.019 vs 0.009, sens 0.537 vs 0.476 at <= 1 FA/h; 963 vs 883 estimated LUTs. MI picked ~34 EEG features and missed the heart-rate and EMG features (N7). No test patient involved; ranking uses the training fold only | runs `dwn_L50_b8_lgbm40`, `dwn_L50_b8_learn` |
| D35 | The laptop's 21 large-DWN configs on the MI features (D32) are replaced by 9 configs on the D34 features with the base recipe (15 epochs, background ratio 10): 500, 1000 and 2000 LUTs at 8 bits, 1000 LUTs at 16 bits, and the Section 6.1 ablations at 500 LUTs (4- and 5-input LUTs, tau 1 and 10, two layers 500 + 100); laptop job `big`, followed by the raw-EEG CNN and TCN. The cloud drops `dwn_L500_b8_learn` and `dwn_L500_b16_learn` (MI) and runs LGN last | D34 changed the model that goes to M6 (event-F1 0.211 vs 0.148 at the same 50 LUTs), so size and ablation results on the MI features would not transfer to it. The <= 200-LUT MI grid already answers the mapping question (learnable beat random in 8 of 9 size/bit pairs) and 4 bits was the weakest at every size. Roughly a tenth of the GPU time of the old list, so M6 can start about a day earlier. The 21 MI configs stay runnable (`scripts/laptop/start.sh sweep`) if the paper needs the full MI grid | `scripts/laptop/big_lgbm.sh`, `configs/m4/dwn_L*_lgbm40_e15bg10*.yaml` |

Method results and keep/drop decisions are appended below as runs finish.

## Results log (inner CV on the 96 training patients only; none of our models has been scored on a test patient)

* **M3 int vs float twin** (10 training patients, `results/m3/int_float_gap.md`): median feature correlation 0.9965 (min 0.889,
  extrema-count features), artefact flags agree 99.7 %, LightGBM leave-patients-out AUROC int 0.736 vs float 0.735. Integer
  front end **kept**: no measurable accuracy cost.
* **lgbm** (Tier-1 reference): window AUROC 0.870; best-F1 operating point (no gate, k = 10) event-F1 0.292, sensitivity 0.327,
  precision 0.348, 3.6 FP/24 h; sensitivity 0.594 at <= 1 false alarm per hour.
* **lr**: AUROC 0.806, event-F1 0.105. Linear models are far behind trees on these features.

* **xgb**: AUROC 0.867, event-F1 0.277 (sens 0.286, 3.4 FP/24 h); vs lgbm per-patient F1 p = 0.54, FP/24 h p = 0.0005.
  Est. 47.9k LUTs.
* **TreeLUT leaf width** (D29): w3 AUROC 0.671 / F1 0.135, w4 0.794 / 0.197, w5 0.857 / 0.266 at about 6.4k estimated LUTs
  (1,073 comparators). **Keep w5** as the TreeLUT entry; w3 (the paper's default) is dropped here: 3-bit leaves cannot
  represent this boosting ensemble. w5 vs lgbm: F1 p = 0.38 (n.s.), FP/24 h p = 0.015.
* **catboost**: AUROC 0.863, event-F1 0.286 (sens 0.337, 3.0 FP/24 h, gate both).
* **rf**: AUROC 0.852, event-F1 0.198 (sens 0.216, 0.5 FP/24 h).
* **dwn_l200_b8_mi40** (first LUT-native run, CPU size: 200 LUT6, 8 thresholds, top-40 MI features): AUROC 0.821,
  event-F1 0.167 (sens 0.291, 3.5 FP/24 h, gate both), sens 0.490 at <= 1 FA/h; **1,782 estimated LUTs**
  (200 network + 1,361 encoder + 209 popcount + 12 post-processing), 0 multipliers. Below TreeLUT w5 (F1 0.266 at 6.4k LUTs)
  and lgbm; the size sweep (Section 6.1 grid) decides whether larger DWNs close the gap.
* **mlp_int8** (INT8 quantisation-aware MLP, the multiplier-based reference): AUROC 0.830, event-F1 0.147 (sens 0.225,
  7.8 FP/24 h); 9,600 multiplications per window. The 1.8k-LUT DWN (F1 0.167, 0 multipliers) is at least as good.
* **lgn_mi40** (difflogic-style logic-gate network): the first attempt was lost to a container restart after 3 of 5 folds
  (about 45 min per fold on CPU; no metrics were written, the incomplete directory was deleted). Re-queued after N1;
  A second restart then cut `n1_stack5` at fold 4 of 5. `scripts/run_queue.sh` now skips configs that already have a complete run and continues an unfinished one with `run_inner_cv.py --resume`, which reloads every fold whose out-of-fold scores were fully written (marker `_fold_<k>.json`) instead of retraining it; an interrupted-then-resumed dry run gave metrics identical to an uninterrupted one. Each fold is seeded by `seed + k` and trained only on its own training folds, so a resumed run is the same experiment.
* **n1_stack5** (N1, DWN 200 LUT6 on the last 5 windows, MI top-40 over the 585 stacked columns): AUROC 0.750,
  event-F1 0.103 (sens 0.171, 2.7 FP/24 h, gate any), sens 0.441 at <= 1 FA/h; about 1.6k LUTs. **Drop**: worse than
  the single-window DWN because the selection kept only about 11 distinct features (D31); re-run as `n1_stack5_base`.
* **n1_stateful_s16** (N1 stateful LUT network, 16 state bits): fold 1 was killed by the out-of-memory killer at
  02:47 UTC, most likely because a dry-run test of `n1_stack5_base` was running alongside it on the same 15 GB machine;
  fold 0 (2,873 estimated LUTs, 16 flip-flops) is kept and the run resumes from fold 1. Dry-run tests are no longer run
  next to the queue. A third container restart (about 06:45 UTC) interrupted `lgn_mi40` after fold 1; it resumed from fold 2.
* **lgn_mi40** result (resumed twice, fold- and epoch-level; 4,000 two-input gates, top-40 MI features): AUROC 0.843,
  event-F1 0.171 (sens 0.330, prec 0.197, 4.9 FP/24 h, gate both), sens 0.540 at <= 1 FA/h; vs lgbm per-patient F1
  p = 3e-05, FP/24 h p = 1e-09; vs dwn_l200 per-patient F1 p = 0.92. **7,491 estimated LUTs** (4,000 network as an upper bound of one LUT per gate, 1,479 encoder,
  2,000 popcount, 12 post-processing), 0 multipliers. Slightly above the 1.8k-LUT DWN (AUROC 0.821, F1 0.167) at about four
  times the estimated cost, and below TreeLUT w5 (F1 0.266) at a similar cost. **Keep** as the Tier-1 logic-gate reference
  row; no further LGN tuning is queued. The DWN size sweep decides the LUT-native entry.
* **n1_stack5_base** (N1 re-run with D31: MI ranked on the t-0 block, every lag of the top 40 kept; DWN 200 LUT6 on the
  last 5 windows): AUROC 0.836, event-F1 0.164 (sens 0.460, prec 0.147, 10.8 FP/24 h, gate both), sens 0.583 at <= 1 FA/h;
  about 3.8k estimated LUTs (637 comparators). vs the single-window dwn_l200: per-patient F1 p = 0.70 (no difference),
  FP/24 h at the best-F1 point +2.9 (p = 1e-14), AUROC +0.015 and sens at <= 1 FA/h 0.583 vs 0.490. **Not adopted**: no
  event-F1 gain at about twice the cost. The higher sensitivity at <= 1 FA/h is noted; stacking is revisited on the base
  DWN size that the sweep picks.
* **n1_stateful_s16** fold 2 was killed by the out-of-memory killer at about 14:59 UTC with nothing else running
  (python anon-rss 13.9 GB of the 15 GB machine); folds 0 and 1 are complete (about 2.9k estimated LUTs, 16 flip-flops).
  Cause: the sequence sampler held every training run's full feature matrix in memory (about 24 M windows for 77
  patients). Fixed in 049e3bc (start points drawn from the labels, each needed run read once, uint8 bits, grouped
  validation scoring); a test checks the new sampler gives the same draws, order and values as the old one. Fold 2
  resumed at 16:23 UTC drew the same 19,980 sequences (3,374 with seizure) with a peak of 3.1 GB instead of 13.9 GB.
* **n1_stateful_s16** result (N1 stateful LUT network: 200 vote LUT6 + 16 state bits fed back each second, trained on
  60 s sequences; folds 2-4 after the memory fix): AUROC 0.834, event-F1 0.198 (sens 0.320, prec 0.213, 2.9 FP/24 h,
  no gate), sens 0.593 at <= 1 FA/h; about 2.9k estimated LUTs (450 comparators) + 16 flip-flops, 0 multipliers.
  vs the single-window dwn_l200 (1.8k LUTs): pooled F1 +0.031, FP/24 h -0.6, sens at <= 1 FA/h +0.10, AUROC +0.013, but
  per-patient F1 p = 0.17 and FP/24 h p = 0.26 (not significant). vs lgbm: F1 p = 3e-04. **Kept, provisionally**, as the
  N1 candidate: the best LUT-native model so far on every pooled metric at about 1.2k extra LUTs, but not yet shown
  better per patient. It is re-run on the base DWN size the sweep picks, before N1 is closed; still below TreeLUT w5
  (F1 0.266 at 6.4k LUTs).
* **Correction (8 Nov): n1_stateful_s16 used all 117 features**, not the MI top 40 its config names. The CV runner
  applied the per-fold mutual-information selection only to window models; sequence models received every column
  (the run's `metrics.json` has `n_features` 117, and its log has no "MI top" line). Its comparison with dwn_l200
  (top 40) therefore mixes the state bits with a different feature set, and the "kept provisionally" decision above
  rests on a confounded comparison. Fixed: sequence models (N1, GRU) now get the same per-fold MI selection, drawn
  from the fold's training windows; window models are unchanged (same code, same seeds). N1 is re-run with the fix
  on the base DWN size before it is decided.
* **DWN size sweep, <= 200 LUTs** (16 of the 18 configs of the grid at 50/100/200 LUTs x 4/8/16 bits x learnable/random
  mapping; single seed each). Best pooled event-F1: dwn_l200_b8_mi40 0.167 (1,745 LUTs; the earlier, shorter training),
  dwn_L200_b16_learn 0.163 (2,281), dwn_L50_b8_learn 0.148 (883), dwn_L100_b16_learn 0.140 (1,653), dwn_L50_b16_learn
  0.135 (1,066); these five do not differ per patient (paired Wilcoxon on event-F1, p 0.15-0.97, median difference 0).
  Size alone does not raise F1 between 50 and 200 LUTs on these features. 4-bit encoders are the weakest (F1 0.068-0.093);
  random mapping costs more LUTs (more comparators) and raises false alarms. Decision D33: base = dwn_L50_b8_learn.
  Window AUROC stays at 0.81-0.83 for every config, below the tree models (0.85-0.87).
* **dwn_L200_b8_learn** (the D33 check): AUROC 0.822, event-F1 0.124, 5.3 FP/24 h, sens 0.534 at <= 1 FA/h, 1,652
  estimated LUTs. Against the 50-LUT base: per-patient F1 p = 0.38 (no difference), FP/24 h median -0.2 (p = 0.014).
  D33 stands. Against dwn_l200_b8_mi40 (same size, earlier recipe: 15 epochs, batch 2048, background ratio 10):
  F1 p = 0.047 in favour of the earlier recipe, so the training recipe may matter as much as size; checked at 50 LUTs
  by dwn_L50_b8_e15bg10 before the Tier-2 runs.
* **N7 on the base DWN** (dwn_L50_b8_learn, best-F1 operating point; `n7_interpretability.json` in the run folder,
  `results/figures/n7_feature_usage.png`): 195 true and 2,950 false alarms over the 96 training patients' out-of-fold
  predictions. The first-layer LUTs read almost the same features during true and false alarms (e.g. eeg_ll_max 0.278
  vs 0.278 of its LUTs firing; eeg_beta_mean 0.80 vs 0.72; mov_acc_jerk 1.42 vs 1.26), i.e. the false alarms look like
  seizures to the network. Its true-alarm feature usage correlates moderately with LightGBM's mean |SHAP|
  (Spearman 0.41, p = 0.007, 42 features). **Finding:** the per-fold MI top 40 is about 34 EEG features + the 4
  presence bits and misses what the trees rely on: SHAP #1 ecg_log_rr was selected in 2 of 5 folds, #4 ecg_log_masrd
  and #6 ecg_log_rr_ctx in none, no EMG feature in any fold. Single-feature MI under-rates features that matter in
  combination or relative to a baseline (heart rate). Next: dwn_L50_b8_lgbm40 (top 40 by LightGBM gain on each
  fold's training windows) runs first; if it beats the base per patient, the base changes before the Tier-2 runs.
* **N3 label-free per-patient adaptation** on the base DWN (`n3_adaptation.json` in the dwn_L50_b8_learn run folder;
  thresholds re-fitted on each validation patient's first H hours, network unchanged, every variant scored against
  the unadapted model on exactly the same data after the window, operating point re-chosen for both). H = 1 h: no
  adaptation F1 0.144 / 6.8 FP/24 h; re-fitted quantiles 0.094 / 11.9 (per-patient F1 p = 0.06); per-feature offset
  0.106 / 10.2 (p = 0.30); streaming integer tracker 0.057 / 39.5 (p = 0.003, worse). The same ordering at H = 2 h
  (none 0.150 / 6.2) and H = 4 h (none 0.140 / 6.2). Seizures inside the adaptation window: 6, 20 and 36 of about
  690. **Not adopted**: no variant lowers the false-alarm rate; every one raises it. The network was trained on
  thresholds placed at population quantiles, and moving them per patient changes which bits fire for background as
  much as for seizures. Revisited only if the base's feature set changes (dwn_L50_b8_lgbm40).
* **dwn_L50_b8_lgbm40** (base DWN, features ranked per fold by LightGBM gain): AUROC 0.839, AUPR 0.019, event-F1 0.208
  (sens 0.275, prec 0.284, 2.3 FP/24 h, no gate, k 10), sens 0.537 at <= 1 FA/h, 963 estimated LUTs, 0 multipliers.
  Against the MI base: per-patient F1 +0.060 [+0.001, +0.119], p = 0.047; FP/24 h p = 8e-07. Against LightGBM:
  per-patient F1 p = 0.004 (still below). **Adopted (D34)**: best LUT-native result so far, under 1k estimated LUTs.
  The selected features now include ecg_log_rr, ecg_log_rr_ctx, ecg_log_masrd, EMG and motion features in every fold.
  The M5 configs are regenerated on this base; the recipe check dwn_L50_b8_lgbm40_e15bg10 decides the training recipe.
* **dwn_L50_b8_lgbm40_e15bg10** (the D34 base with the earlier recipe: 15 epochs, batch 2048, background ratio 10):
  AUROC 0.840, AUPR 0.021, event-F1 0.211, 2.4 FP/24 h, sens 0.581 at <= 1 FA/h, 964 estimated LUTs. Against the
  30-epoch / ratio-20 recipe: per-patient F1 +0.003 [-0.037, +0.045], p = 0.88; FP/24 h p = 0.11. Equal results at about
  a quarter of the training time, so **the M5 base is dwn_L50_b8_lgbm40_e15bg10**; the 18 Tier-2 configs are
  regenerated on it and run first on the cloud, followed by LGN, LogicNets-style and GRU on the same features and a
  size check at this base (100 and 200 LUTs).
* **Breakdown of the M5 base** (dwn_L50_b8_lgbm40_e15bg10, `breakdown.md` in its run folder; inner folds, its own best-F1
  operating point). Sensitivity by seizure type (alarm within onset - 30 s .. end + 60 s): FBTC 0.879 (29 of 33),
  FIA 0.173 (50/289), FA 0.095 (26/274), focal with unknown awareness 0.079 (8/101). Missing modalities at test time
  (features and present bits zeroed, operating point unchanged): no ECG F1 0.092 (from 0.211; per-patient p = 2e-05),
  no motion 0.136 (p = 0.004; FP/24 h 5.2 from 2.4), no EMG 0.199 (p = 0.64), EEG only 0.074 (p = 2e-06). The base
  relies on ECG and motion and is not robust to losing either: the baseline N6 (modality dropout, gated and late
  fusion) is measured against. Tonic-clonic seizures are detected; focal seizures on behind-the-ear EEG mostly not.
* **n1_stateful_sel** (N1: 16 state bits fed back each second, on the D34 base and its features): AUROC 0.861, AUPR
  0.028, event-F1 0.192 (sens 0.223, prec 0.239, 1.1 FP/24 h, gate both, k 10), sens 0.594 at <= 1 FA/h; median
  estimated LUTs +8 over the base, plus 16 flip-flops. Against the base: per-patient F1 -0.019 [-0.066, +0.026],
  p = 0.66; FP/24 h -1.3 [-3.0, -0.3], p = 0.013; AUROC +0.021, sens at <= 1 FA/h +0.013. **Not adopted** (event-F1, the
  primary metric, is not better): its best-F1 point trades sensitivity (0.22 vs 0.32) for fewer false alarms. The
  higher AUROC and the significant false-alarm reduction are kept in view for the combination run after M5.
