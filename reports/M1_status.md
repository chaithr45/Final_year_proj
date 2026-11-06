# M1 status report: repository setup and data audit

Template of Section 10.5. Branch `claude/optimistic-heisenberg-ph0bvj`.

## What was done

* Repository layout of Section 10.2; `environment.yml` (GPU machine, provisional torch/CUDA pin),
  `requirements-ci.txt` (pinned CPU set), `pyproject.toml` (`src/` importable as `seizelut`).
* **Data loader** (`src/data/`): NumPy EDF/EDF+ reader, bit-exact against pyEDFlib on real data;
  BIDS run discovery; `_events.tsv` parsing with seizure classes; montage handling; windows and
  labels on a seconds grid (2 s / 1 s, ≥ 50 % rule, training-only 0.5 s augmentation that never
  crosses a run); official split and patient-wise inner folds; signal-quality statistics.
* **Scripts**: `download_data.sh` (openneuro-py → aws → datalad, plus `--metadata`), `fetch_metadata.py`,
  `verify_data.py`, `audit_signals.py` (streams every EDF from S3, so no 126 GB copy is needed),
  `audit_data.py`, `make_folds.py`.
* **CI**: GitHub Actions runs 40 unit tests on a 1.1 MB synthetic BIDS fixture (never real data),
  and checks the fixture regenerates byte for byte.
* **Literature re-check** (Section 2): [`reports/literature_check.md`](literature_check.md).
* **Data audit**: [`reports/data_audit.md`](data_audit.md), tables in `results/audit/`.

## The numbers

| Quantity | Prompt | Audit |
|---|---|---|
| Patients (train / test) | 125 (96 / 29) | 125 (96 / 29) |
| EEG hours | ~11,640 | 11,626 |
| Seizures (train / test) | 886 (704 / 182) | **883 (702 / 181)** |
| Biopotential sampling rate | 250 Hz | **256 Hz in all 8,458 files** |
| Motion | 3-axis ACC + GYR, chest | 25 Hz; 8 channel layouts, 12 channels in 2,308 of 2,551 runs |
| Missing ECG/EMG, motion | ~3 % | 3.1 %, 3.9 % of EEG time |
| Positive rate | ~0.1 % | 0.123 % of EEG time |
| Female patients | 51 | 62 in participants.tsv |
| Inner folds | stratified by centre and seizure count | seizure count only; 137–143 seizures per fold |

Signal-level results (flat-lines, saturation, the official RMS artefact rule) are in
`reports/data_audit.md` §6; the coverage line there says how many of the 11,009 files were read.

## Decisions and why

See [`results/decisions.md`](../results/decisions.md) D1–D9. The most consequential ones:
* All windowing is in seconds; filters in M3 will be designed for 256 Hz.
* Folds cannot use centre; the centre/adult-child analyses are blocked.
* The visible-seizure secondary result is not computable.
* The official artefact gate effectively uses only the cross channel (a Python `and` on lists);
  M2 reproduces it for the baselines.

## Problems and risks

1. **No centre or age labels** in the public data: stratification, leave-one-centre-out and
   Table 5 breakdowns need them from the authors.
2. **The 13 µV RMS floor flags most windows of the same-side channel**; a naive artefact gate on both
   channels would discard most of the data. Needs a decision in M3.
3. **Compute**: the GPU machine is a laptop RTX 3060 (6 GB) on Windows; `torch-dwn` should be run
   under WSL2. Disk on that machine decides whether we store raw data or stream per subject.
4. **Timeline**: EMBC 2027 full papers are reportedly due 24 Jan 2027, before the 16-week plan ends.

## Plan for M2 (baseline reproduction, weeks 3–4)

* Run the official SVM and ChronoNet from `biomedepi/seizeit2` on the official split, inner folds
  for any tuning, test patients scored once.
* `src/eval/`: SzCORE event scoring through `timescoring`, plus the dataset paper's metrics
  (OVLP sensitivity, epoch false alarms/h, AUROC, AUPR); unit tests against `timescoring` on toy cases.
* Our numbers next to the published Table 2 (71.1 % / 11.0 FA/h; 84.2 % / 100.5 FA/h).

## Questions for you

1. Go-ahead for M2?
2. Did you email the authors for centre and adult/child labels? Until they answer, is stratifying folds by
   seizure count acceptable?
3. Target venue: compress the plan for EMBC 2027 (24 Jan) or aim for BioCAS 2027?
4. Free disk on your laptop (`Get-PSDrive C`), to choose between a full download and streaming.
5. Branch name: keep this branch, or should the PR be renamed `phase1-software`?
