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

## M2+ method decisions

_(empty until M2)_
