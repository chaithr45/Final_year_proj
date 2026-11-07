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

Method results and keep/drop decisions are appended below as runs finish.

## Results log (inner CV on the 96 training patients only; no test patient has been scored)

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
