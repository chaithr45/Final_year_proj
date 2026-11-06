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
| D15 | SVM baseline pending | The paper text (42 features) is needed; arXiv/Nature not reachable from the coding environment | Question for the user |

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
Method results and keep/drop decisions are appended below as runs finish.
