# SeizeLUT v2: research plan (branch `claude/seizelut-v2`)

Started 28 Nov 2026 at the user's request: "increase the accuracy ... the acc should cross 85 % ... the best possible
paper for submission and the best possible product for pitching".

## Targets (agreed with the user on 28 Nov)

1. **Seizures detected (any-overlap sensitivity) above 85 %** at a stated false-alarm limit; the full
   sensitivity / false-alarm curve is always reported, never only the best point.
2. **Event-F1 (SzCORE): the largest honest gain** over v1 (0.248 on test). 85 % event-F1 is not realistic; the best
   blind benchmark result is 43 %.

## Ground rules (unchanged from CLAUDE.md, plus the user's 28 Nov answers)

- All development on the 96 training patients with patient-wise 5-fold CV (`configs/folds_inner5.json`).
- The 29 test patients (sub-097..sub-125) were scored once in v1. v2 gets **one more final test**, after the v2 design
  is frozen and its operating points are pre-registered (`results/v2/prereg.json`); every access logged in
  `TEST_ACCESS.log`; reported as a second evaluation.
- No invented numbers; failed ideas are logged in `reports/v2/LOG.md`.
- Compute: cloud CPU (4 cores, 15 GB) until the user says the laptop GPU is free. Disk is tight (about 2 GB free).

## Why v1 stops at about 60 % (training CV) at 1 false alarm per hour

The window model sees 2 s of signal plus a 64-s baseline. Seizures last 2-962 s (median 33 s) and focal seizures
often change the signals only slightly, relative to that patient's own normal. Two cheap levers are untested:
context over minutes (how the score and the signals evolve) and normalisation to each patient's own baseline.

## Work packages

| WP | What | Data | Output |
|---|---|---|---|
| 0 | Harness: load out-of-fold (OOF) scores and labels of any v1 run; paper metric (any-overlap sensitivity vs FA/h) and SzCORE event-F1 curves; budgets 0.1, 0.5, 1, 2, 5, 10 FA/h | OOF | `scripts/v2/harness.py`, baseline table |
| 1 | Ensembles of v1 base models (LightGBM, CatBoost, XGBoost, DWN) | OOF | curves |
| 2 | **Context model (stage 2)**: stacked, patient-wise CV, on multi-scale summaries of base scores (rolling max / mean / quantiles over 10-600 s, past only = real-time mode; plus a delayed mode for logging) and of key signals (heart-rate rise, movement, EEG power) relative to the patient's own past | OOF + features | curves |
| 3 | **Patient-relative features**: causal per-recording baseline normalisation (running median / MAD over the past hour) for every feature; retrain LightGBM | features | new OOF |
| 4 | Seizure-type and duration breakdown; convulsive seizures separately | OOF | table |
| 5 | Hardware-feasible version: stage 2 as a small LUT network or quantised trees; cost estimate | models | cost |
| 6 | Freeze, pre-register operating points (training folds only), one final test | test | `results/v2/final_test.json` |
| 7 | Paper v2 (submission-ready) | all | `paper_v2/` |
| 8 | Product pitch v2 (deck + one-pager) | all | `pitch_v2/` |

Order: 0 -> 1 -> 2 -> 3 -> (2 again on 3's OOF) -> 4 -> 5 -> 6 -> 7, 8. Each step keeps only what beats the previous
best on training CV (paired Wilcoxon per patient where relevant).
