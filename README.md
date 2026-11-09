# LUT-native multimodal seizure detection on SeizeIT2 (Phase 1, software)

B.Tech final-year project, NIT Warangal. Research question: can a LUT-native neural network
(a weightless network whose neurons are FPGA lookup tables), fed by integer features from
behind-the-ear EEG, ECG, EMG and motion, detect focal seizures in unseen patients as well as the
official SeizeIT2 baselines, with no multipliers in the classifier and a budget of a few thousand LUTs?

Phase 1 (this repository) is software only and ends with a hardware-ready handoff package.
Phase 2 (FPGA build) has its own prompt.

## Status

| Milestone | State |
|---|---|
| M1 repository setup and data audit | done: [`reports/data_audit.md`](reports/data_audit.md), [`reports/M1_status.md`](reports/M1_status.md) |
| M2 baseline reproduction | ChronoNet scored on the test patients. Official protocol: **not reproduced** (sensitivity 74.5% vs 84.2% published, AUROC 0.741 vs 0.792; AUPR matches only when averaged per recording: 0.109 vs 0.104). Clean variant (last epoch, no test information): sensitivity 67.1%, 11.9 FA/h, AUROC 0.746; it is the ChronoNet row for M6. Details in `results/decisions.md`. SVM waits for the 42-feature table of Vandecasteele et al. 2020 |
| M3 golden integer features + float twin | done: 117 features, [`spec/fixed_point.md`](spec/fixed_point.md); integer vs float LightGBM AUROC 0.736 vs 0.735 ([`results/m3/int_float_gap.md`](results/m3/int_float_gap.md)) |
| M4 Tier-1 comparison (inner folds) | in progress: LR, LightGBM, XGBoost, CatBoost, RF, TreeLUT, DWN, LGN, INT8 MLP done ([`results/tables/inner_cv.md`](results/tables/inner_cv.md), Pareto plot [`results/figures/pareto_inner_cv.png`](results/figures/pareto_inner_cv.png)); DWN size sweep: the <= 200-LUT grid done on the MI features; 500-2000 LUTs and the Section 6.1 ablations re-run on the D34 features on the GPU laptop (D35), with the raw-EEG 1-D CNN and TCN (`scripts/run_inner_cv_raw.py`); LogicNets-style network, GRU and LGN on the D34 features queued on the cloud |
| M5 Tier-2 (N1–N7) | done (D39, design frozen 8 Nov): adopted LightGBM-gain feature selection (D34), distillation from LightGBM (D37, final network: false alarms 2.4 → 0.9 per day) and modality dropout as the missing-sensor-robust variant (D36); not adopted: stateful/stacked memory, per-patient adaptation, five losses, hard negatives, four encoders, gated and late fusion ([`results/tables/m5_ablation.md`](results/tables/m5_ablation.md), [`results/decisions.md`](results/decisions.md)) |
| M6 final test | done (11 models): 29 held-out patients, 5 seeds, scored once. Final DWN (≈900 LUTs, no multipliers): event-F1 0.248 ± 0.016, 0.8 false alarms per day; clean ChronoNet 0.027 / 106 (per-patient p = 0.027); TreeLUT 0.233; random forest 0.246; CatBoost 0.254; logic-gate network 0.191; LightGBM 0.308 ([`results/tables/final_test.md`](results/tables/final_test.md)) |
| M7 hardware handoff | done for the final DWN: [`export/n4_distill_s0`](export/n4_distill_s0) (thresholds, mapping, truth tables, head, generated Verilog); the Verilog matches the software on all 431,960 windows of 10 test recordings (`verilog_check.json`) |
| M8 paper | 4-page draft with the final results ([`paper/main.pdf`](paper/main.pdf)); Phase I report in the NITW format ([`reports/phase1_nitw/out/`](reports/phase1_nitw/out/)) |

Key audit facts that differ from the original plan: biopotentials are **256 Hz** (not 250 Hz),
**883** seizures (not 886), no centre/age labels in the public release, no visibility labels.

## Environment

Research machine (GPU; Linux or WSL2 on Windows):

```bash
conda env create -f environment.yml
conda activate seizelut
```

Check the `torch`/CUDA pin in `environment.yml` against `nvidia-smi` first. `torch-dwn` needs CUDA.

CPU-only (tests, data audit), Python ≥ 3.12:

```bash
pip install -r requirements-ci.txt && pip install -e . --no-deps
```

The code lives in `src/` and is imported as `seizelut` (e.g. `from seizelut.data.bids import discover_runs`).

## Data

SeizeIT2, OpenNeuro [ds005873](https://openneuro.org/datasets/ds005873) v1.1.0, CC0,
DOI [10.18112/openneuro.ds005873.v1.1.0](https://doi.org/10.18112/openneuro.ds005873.v1.1.0);
Bhagubai et al., *Scientific Data* 2025. 125 patients, 11,009 EDF files, 125.9 GB.
Nothing under `data/`, `cache/` or `checkpoints/` is committed.

```bash
# metadata only (~200 MB): sidecars, events, EDF headers -- enough for the audit tables
scripts/download_data.sh --metadata

# full dataset (needs ~250 GB free): tries openneuro-py, then aws s3 sync, then datalad
scripts/download_data.sh

# check a local copy against the committed audit
python scripts/verify_data.py              # add --metadata-only for a metadata tree
```

Download route used for the M1 audit: public S3 bucket over HTTPS (`scripts/fetch_metadata.py`
for metadata; `scripts/audit_signals.py --stream` streams each EDF, measures it and deletes it,
so the full signal audit needs no local copy).

## Reproduce

| Output | Command |
|---|---|
| Data audit report, tables, figures | `python scripts/fetch_metadata.py && python scripts/audit_signals.py --stream && python scripts/audit_data.py` |
| Inner 5-fold split of the 96 training patients | `python scripts/make_folds.py` → `configs/folds_inner5.json` |
| Synthetic CI fixture | `python tests/fixtures/make_synthetic_bids.py` |
| Unit tests | `pytest` |

## Protocol in one paragraph

Official split: train `sub-001`–`sub-096`, test `sub-097`–`sub-125` (the official "validation" set;
there is no separate test split). All tuning happens with 5-fold patient-wise cross-validation inside the
training patients (`configs/folds_inner5.json`); test patients are scored once per final model in M6.
2 s windows, 1 s hop, a window is "seizure" if ≥ 50 % overlaps an annotation; seizure windows get
extra 0.5 s-hop copies in training only. Primary metric: SzCORE event scoring.

## Layout

```
configs/      dataset.yaml, folds_inner5.json, one YAML per experiment
scripts/      download, verify, audit, one script per table and figure
src/data/     EDF reader, BIDS loader, montage, windows, labels, splits, signal quality
src/features/ golden fixed-point features + float twin (M3)
src/models/   DWN, N1-N7, baselines, fusion, post-processing (M2, M4, M5)
src/eval/     SzCORE scoring, dataset-paper metrics, statistics (M2)
src/hw/       exporter, cost estimator, Verilog generator (M7)
spec/         fixed_point.md and Phase 2 interface notes
export/       exported models (small JSON)
tests/        unit tests and the synthetic BIDS fixture
results/      audit tables, runs/<id>/, decisions.md, tables/, figures/
reports/      data audit, literature check, milestone status reports
paper/        IEEEtran draft (M8)
```

## Citation and ethics

Cite the dataset DOI above and Bhagubai et al. 2025. Original approvals: UZ Leuven ethics committee
S63631; data sharing S67350.
