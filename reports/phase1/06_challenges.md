# Chapter 6. Challenges faced and how we overcame them

Every problem below is recorded with its evidence in the project's decision log (`results/decisions.md`, decision
numbers D1–D35 in brackets). Failed ideas are kept there as well.

## 6.1 Data

| Challenge | What happened | How we overcame it |
|---|---|---|
| The data did not match its documentation | The paper and our project brief say 250 Hz and 886 seizures; the files say 256 Hz and 883. Centre and age labels, needed for stratified splits, are not in the public release; seizure-visibility labels are empty. | A full audit of all 11,009 files before any modelling (Chapter 3). Every window and filter is defined in seconds and designed for 256 Hz; folds are stratified by seizure count; analyses the data cannot support were dropped and reported (D3, D4, D6). |
| 126 GB of data, a cloud machine with neither the disk nor a GPU | The dataset could not be stored where the code runs. | The audit and the feature extraction stream each file from the public S3 bucket, process it and delete it; only the 3.5 GB of integer features are kept. |
| Silent download truncation | Comparing integer and float features exposed one ECG file cut at 51,855 of 71,835 s. A new verifier then found 9 recordings silently truncated by incomplete network reads (one EEG file had 12 of 16,363 windows). | Downloads are checked against the expected size, the EDF header is checked against the file size, and every cached recording is verified against the audit durations. All 9 were re-extracted; the 3 model runs trained on the bad cache were marked invalid and re-run (D30). |
| A recording with an ECG lead but no detectable heartbeat | The feature extractor crashed on an empty beat list (3,250 s of data). | The recording is kept, its ECG features are set to 0 and a quality bit is raised (D28). |
| The official artefact rule does not suit behind-the-ear EEG | The 13 µV RMS floor flags 69 % of ordinary windows on one channel, because bte-EEG amplitudes are close to it. | For our models the artefact flags are input bits, and whether to gate alarms on them is chosen on the training folds (D21). |

## 6.2 Reproducing the published baseline

| Challenge | What happened | How we overcame it |
|---|---|---|
| ChronoNet did not reproduce | Our run detected 74.5 % of seizures against 84.2 % published, with 22.6 instead of 100.5 false alarms per hour. | We ported the official code literally (verified on 900 random cases), then checked the metric definitions: the published AUPR matches only when averaged per recording (0.109 vs 0.104), and the published false-alarm rate matches neither definition in the code. The gap is reported as measured, not tuned away. |
| The released code selects its model on the test patients | Its training loop picks the epoch with the best score on the same patients it is then evaluated on. | We reproduced it as published and also trained a "clean" version (last epoch, no test information), which is the honest reference for our final comparison (D13). |
| Defects in the released evaluation code | True positives can be counted more than once, and the artefact gate (`a and b` on two Python lists) silently uses only one channel. | Reproduced as written for the comparison with the paper; corrected numbers reported in a separate column (D8, D11). |
| The SVM baseline cannot be rebuilt yet | The dataset paper defers its 42 features to Vandecasteele et al. (Epilepsia 2020), which could not be retrieved from the coding environment. | Still open: we need that paper's feature table (D15). |

## 6.3 Hardware arithmetic

| Challenge | What happened | How we overcame it |
|---|---|---|
| Rounding noise in integer filters | With plain rounding, the 0.5 Hz high-pass filter had an error of 140 LSB standard deviation, larger than the signal (61 LSB). | Second-order error feedback of the discarded bits: error 0.7 LSB (D18). |
| Quantised coefficients moved the filter zeros | Rounding each coefficient independently moved the low-pass zeros away from Nyquist (stopband floor −55 dB). | Structure-preserving quantisation, b = b0·(1, ±2, 1), with coefficients as sums of powers of two (D19). |
| Heart rate without a divider | Heart rate needs 60/RR. | We use log2(RR) from integer R-peak timestamps: no division, no multiplication (D22). |
| Proving the integer pipeline costs nothing | Hardware arithmetic could lose accuracy silently. | A floating-point twin of every feature: median correlation 0.9965 and equal LightGBM AUROC (0.736 vs 0.735). |
| TreeLUT scores were not comparable across folds | Each fold's integer score had its own scale, so pooled thresholds were meaningless; 3-bit leaves could not represent the model. | Scores converted to a common unit; leaf width tuned on the folds (5 bits) (D29). |
| Verilog disagreed with the software | Thresholds outside a feature's bit width (e.g. 79 on a 2-bit presence feature) produced wrong comparator logic. | The generator now emits constant bits for such thresholds; the simulation agrees with the software on 100 % of test vectors. |

## 6.4 Compute and infrastructure

| Challenge | What happened | How we overcame it |
|---|---|---|
| No GPU in the cloud; a small GPU laptop | The cloud machine has 4 CPU cores; the laptop has a 6 GB GPU and 7.4 GB of RAM under WSL. The reference DWN library only runs on CUDA. | We re-implemented the DWN in pure PyTorch, identical to the library's CUDA kernel (unit-tested), so it runs on both. CPU jobs (small models, trees) run in the cloud; large networks and raw-EEG models run on the laptop GPU (D24, D27, D32). |
| Long runs interrupted | Container restarts lost the logic-gate network run after 3 of 5 folds; others were cut mid-fold. | Every run resumes at fold and epoch level; a queue skips finished runs and continues unfinished ones; a resumed run was checked to give identical metrics. |
| Out-of-memory kills | The stateful network's sequence sampler held 24 million windows in memory (13.9 GB of a 15 GB machine). | A new sampler reads each needed recording once and stores bits as bytes: same sequences, peak memory 3.1 GB. |
| Two machines, one code base | The laptop and the cloud must not overwrite each other's work. | One git branch; the laptop only sends finished results; written instructions for the laptop side; automatic tests on every change. |

## 6.5 Machine learning

| Challenge | What happened | How we overcame it |
|---|---|---|
| Seizures are 0.123 % of the time | Accuracy is meaningless; training on all windows teaches the model to never fire. | Event-based scoring (SzCORE) per patient; training on all seizure windows plus a fixed ratio of background windows; operating points chosen for a false-alarm budget. |
| Results must hold on unseen patients | Mixing a patient's windows between training and validation inflates results. | Patient-wise 5-fold cross-validation; feature selection and thresholds fitted inside each training fold only; the test patients are locked behind a flag and every access is logged (D14, D25, D26). |
| The network ignored the heart signal | The interpretability study showed that mutual-information selection kept about 34 EEG features and missed the heart-rate and muscle features. | Feature selection by LightGBM importance: event-F1 0.148 → 0.208, false alarms 7.0 → 2.3 per day (D34). |
| A confounded comparison | The stateful network had silently received all 117 features instead of the selected 40, so its apparent gain mixed two changes. | Found by checking the run's metadata. All models now share one training function; the run was repeated; the correction is logged next to the original claim. |
| Stacking past windows picked duplicate features | Ranking 585 stacked columns kept lagged copies of only 11–13 distinct features. | Rank on the current window, then keep every lag of the winners (D31). |

## 6.6 Still open

* **Focal seizures** are mostly missed (8–17 % detected at the best-F1 point), while tonic-clonic seizures are
  caught (88 %). The M5 extensions and the larger networks address this.
* **The gap to LightGBM** (event-F1 0.211 vs 0.292) is not closed yet.
* **Robustness to missing sensors:** without ECG, event-F1 falls from 0.211 to 0.092 (N6 addresses this).
* **SVM baseline** and **centre labels** depend on information outside the public release.
