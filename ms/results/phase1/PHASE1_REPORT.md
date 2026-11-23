# SeizeLUT-MS Phase 1 report: a front-end specification derived from the detector

Status, 23 Nov 2026: the study on the training patients is finished and waits for your review. Test patients
(sub-097..sub-125) were not used at any point. Every number below is copied from a result file in
`ms/results/phase1/` (named in brackets); the PDF `phase1_results.pdf` shows the same numbers, read directly from
those files by `ms/py/results_pdf.py`, together with the full tables and figures.

## 1. The question

How good does the analog front end (amplifier, filters, ADC) of a wearable have to be for the frozen SeizeLUT
detector to keep its accuracy? "Good enough" is defined by the detector, not by a datasheet habit: an impairment
is acceptable when it changes the detector's result by less than retraining the same model with another random
seed does. The answer is a specification an analog designer can work to, and its power cost.

## 2. What was done, in order, and why each number can be defended

**2.1 The models that are scored.** The frozen detector `n4_distill_s0` was trained on all 96 training patients,
so scoring it on them would be in-sample. Instead each patient is scored by one of 5 fold models that never saw
that patient (out-of-fold), retrained with the frozen recipe and seed. Check: on clean data they reproduce the
committed cross-validation result exactly (equality test passes in every full-data run; `cv_frozen_op.json`,
`confirm_limits.json`). Clean result on all training hours: event-F1 0.2292, sensitivity 0.2675, 0.929 false
alarms per 24 h (per-patient means; `confirm_combined_901eeb9f.json`).

**2.2 What "tolerated" means (decision D-MS10, fixed before any sweep).** Seeds 1-4 of the same 5 folds were
trained as well, and the standard deviation of the clean result over the 5 seeds is the allowed change
(`deltas.json`):

| data | allowed F1 drop | allowed rise in false alarms | extra condition |
|---|---|---|---|
| subset (sweeps) | 0.0307 | 0.126 per 24 h | mean over 5 impairment seeds |
| all training hours (confirmation) | 0.0092 | 0.206 per 24 h | paired per-patient Wilcoxon p >= 0.05 |

Defence: a change smaller than "the same recipe with another seed" cannot be told apart from training noise, so
it is not a degradation that matters. The price: the limits are only known to about one grid step (a factor of
about 2), and the report says so.

**2.3 The impairment model.** Each impairment is applied to the raw int16 samples before the frozen feature front
end: ADC step q and clip level C (bits = ceil(log2(2C/q))), white and 1/f noise, gain error in both signs, DC
offset, slow drift, high- and low-pass corners, 50 Hz and 250 Hz mains. 12 families per biopotential (EEG, ECG,
EMG) and 4 for the chest motion sensor, 40 in all. The noise generator is the one the FPGA uses (xoroshiro128+,
Gaussian from a sum of 64 uniforms); a run with exact Gaussian noise gives the same verdict (`gauss_ab.json`). The
Verilog emulator matches the Python model with 0 mismatching words (`impair_rtl_check.json`,
`impair_rtl_axi_check.json`).

**2.4 One impairment at a time, on a subset.** 899 segments from the 96 training patients: every one of the 698
training seizures with 20 min before and 10 min after, plus 4 background hours per patient; 667.2 scored hours
(`subset.json`). Each family is swept from mild to severe with 5 impairment seeds; the limit is the most severe
level of the unbroken run of tolerated levels.

**2.5 Every limit re-tested on all training hours.** 2,072 recordings, 8,714.7 scored hours, 96 patients (one
impairment seed, LOG L18). A limit that fails there is moved one grid step milder at a time until it passes (rule
written before any such result, LOG L20). Outcome over the 40 families: 29 limits, 10 "beyond grid" (even the
most severe tested level passes), 1 with no tolerated level (the ECG low-pass corner); 10 limits had to be stepped
down (`spec_limits.json`).

**2.6 All impairments at once.** A real front end has all impairments together. With every family at its
one-at-a-time limit the detector fails clearly on the subset: F1 -0.0719 and -0.0848 for the two signs of gain
error, 2.3-2.8 times the allowed drop (`combined_verdict.json`). Each limit had been found with the whole error
budget to itself. So the families were backed off by a rule pinned before any back-off run (LOG L21): at each step
the family that flips the most detector comparator bits on its own moves one grid step milder; rank again; repeat.
It took 22 steps on the subset (5 seeds each), and the resulting point passed on all training hours with no
further step:

| combined point (step 22) | F1 change | false alarms per 24 h | Wilcoxon p | verdict |
|---|---|---|---|---|
| subset, gain error +, 5 seeds | -0.0286 | +0.118 | - | tolerated |
| subset, gain error -, 5 seeds | -0.0281 | +0.089 | - | tolerated |
| all training hours, gain error +, seed 0 | -0.0022 | +0.105 | 0.48 | tolerated |
| all training hours, gain error -, seed 0 | -0.0076 | +0.094 | 0.50 | tolerated |

(`combined_backoff.json`, `combined_backoff_full.json`, `confirm_combined_901eeb9f.json`). The per-step trace is
table 5b of the PDF.

Midway (after step 15) I suggested changing the ranking, on the hypothesis that the clip levels drove the
failure. You had not answered, nothing was changed, and the rule converged without touching any clip level, so
that hypothesis was wrong; it is recorded in LOG L21 and withdrawn.

## 3. The specification (the combined point; input-referred)

| | EEG (2 channels) | ECG (1 channel) | EMG (1 channel) |
|---|---|---|---|
| noise, 0.5-100 Hz | 1 uV rms (100 nV/sqrt(Hz)) | 4 uV rms | 2 uV rms |
| 1/f corner at 1 uV rms white | 3 Hz | 30 Hz | 30 Hz |
| ADC step q | 4 uV | 16 uV | 16 uV |
| input range (clip level C) | 2048 uV | 1024 uV | 1024 uV |
| ADC bits (ideal SNDR) | 10 (62.0 dB) | 7 (43.9 dB) | 7 (43.9 dB) |
| gain error | below 5 % (the mildest tested level was backed off) | +-50 % | +50 % / -20 % |
| DC offset (C = 8192 uV) | 0.6 C | 0.1 C | 0.6 C |
| drift (64 s time constant) | 10 uV rms | 100 uV rms | 100 uV rms |
| 50 Hz / 250 Hz mains | 1 uV / 1 uV | 10 uV / 1 uV | 1 uV / 10 uV |
| high-pass corner, at most | 0.1 Hz | 0.3 Hz | 0.5 Hz |
| low-pass corner, at least | 100 Hz | no tested corner tolerated (100 Hz fails) | 70 Hz |

Chest motion sensor (digital IMU): step 8 LSB, white noise 1 LSB rms, gain error +50 % / -10 %. Full table with
the one-at-a-time limit next to each value: `spec_table.md`, PDF section 9.

## 4. What it costs in power (`spec.json`)

| per channel | amplifier, NEF 2 | NEF 3 | NEF 5 | ADC, FOM-scaled (best) | ADC, lowest real low-rate design |
|---|---|---|---|---|---|
| EEG | 0.482 uW | 1.08 uW | 3.01 uW | 42-159 pW | 0.468 uW |
| ECG | 0.0301 uW | 0.0678 uW | 0.188 uW | 2.6-11.6 pW | 0.0027 uW |
| EMG | 0.120 uW | 0.271 uW | 0.753 uW | 2.6-11.6 pW | 0.0027 uW |
| all 4 channels | 1.11 uW | 2.51 uW | 6.97 uW | at most 341 pW | 0.941 uW |

How each column is computed, so you can redo it by hand:

- Amplifier: the noise-efficiency-factor definition solved for current, I = NEF^2 pi U_T 4kT BW / (2 v_n^2),
  P = I x VDD, with VDD 1.8 V, T 300 K, BW 99.5 Hz and v_n the noise spec. Example, EEG at NEF 2: 1 uV rms gives
  I = 0.268 uA and P = 0.482 uW. The current goes as 1/v_n^2, so halving the noise costs 4 times the power.
  **NEF 2, 3 and 5 are an assumed range, not values read from published amplifiers yet** (the papers are on your
  list).
- ADC, FOM-scaled: the best Walden and Schreier figures of merit of survey designs with the needed SNDR (up to
  +20 dB), scaled to 256 Hz. Optimistic: at 256 Hz static power dominates and FOMs do not scale down.
- ADC, lowest real low-rate design: the lowest power of any design in the survey with at least the needed SNDR
  and a Nyquist rate of at most 20 kHz (EEG: ISSCC 2021, 6 kHz, 86.7 dB; ECG and EMG: ISSCC 2017, 1 kHz,
  48.3 dB), at its own rate. A realistic floor.
- Digital part (feature front end and LUT network): not measured yet (board measurement on your list).

## 5. Four findings to be able to explain

1. **Single-impairment limits do not add up.** With everything present the EEG noise must go from 4 to 1 uV rms
   (16 times the amplifier current at the same NEF) and the EEG ADC from 7 to 10 bits; summed over the 4 channels
   at NEF 3, the amplifiers go from 0.424 uW (one-at-a-time noise limits) to 2.51 uW. A front end specified one
   impairment at a time would fail (2.6). This is the main argument for detector-aware co-design.
2. **Mains pick-up drives the EEG front end.** 1 uV of 50 Hz passes on all hours, 10 uV fails, so common-mode
   rejection or a notch matters more than the noise floor alone.
3. **ECG must not be low-passed** at any tested corner (100 Hz already fails), so the detector seems to use the
   ECG's high-frequency content (not checked further).
4. **The amplifier, not the ADC, sets the analog power if the FOM scaling held**; against real low-rate ADCs the
   two are of the same order (2.51 uW vs 0.941 uW at NEF 3).

## 6. Limits of these results (say them before a reviewer does)

- **Weak detector.** Per patient it finds about a quarter of the seizures (sensitivity 0.2675). A detector with
  little to lose may tolerate more, so the spec may be looser than a better detector needs.
- **Resolution.** The threshold is one seed-to-seed standard deviation; limits hold to about one grid step.
- **Sufficient, not minimal.** The greedy back-off finds one passing point; another order could find a cheaper
  one. The subset test was the stricter one here (F1 change about -0.03 on the subset against -0.002 to -0.008 on
  all hours), and the two EEG gain-error steps did not improve the result at the next step, so "below 5 %" is what
  the rule produced, not something the data show is needed. Wording for the write-up: "a front end meeting this
  spec is tolerated", not "the detector needs exactly this".
- **Pooled events move more for one sign.** The test uses per-patient means. Pooled over all events, F1 falls
  from 0.1890 to 0.1735 with the positive gain error (and is 0.1899 with the negative one).
- **One impairment seed on all hours** (LOG L18): random-noise verdicts close to the threshold are flagged
  "marginal" in PDF section 8c; extra seeds for them are an optional, report-only run.
- **No circuit yet.** Power comes from formulas and survey figures of merit. Phases 2-4 replace that with a
  designed comparator, an FPGA delta-sigma ADC and a measured chain.

## 7. Regenerating every number

```bash
bash ms/py/run_phase1_confirm.sh
```

runs the full-data confirmation, the step-down rounds, the back-off on the subset and on all hours, and
`spec_table.py`. It needs the seed-0 fold models and the feature caches of steps 2.1 and 2.4, and it resumes after
an interruption; here it took several days of wall-clock time on 4 CPUs, the subset back-off alone 13 h
(10:38-23:47 UTC on 22 Nov). Single steps:
`python ms/py/full_spec.py` (spec_limits.json), `python ms/py/combined_backoff.py --models <seed-0 fold models>
[--data full]`, `python ms/py/spec_table.py` (spec.json, spec_table.md), `python3 ms/py/results_pdf.py` (the PDF).
The subset sweeps and cross-checks have their own scripts in `ms/py/` (see `ms/REPO_MAP.md`).

## 8. What I need from you

1. Your review of this report and the PDF; whether to merge this branch into `FPGA`.
2. Optional, report only: extra impairment seeds for the EMG full-data verdicts nearest the threshold (about
   3-4 h; verdicts unchanged either way). Yes or no.
3. Your hardware items, when FCCM allows: the analog container check (`ms/setup/check_tools.sh`), the ms1 kit
   build and board self-test (I check the wiring and procedure with you first), the board energy of the digital
   part, and the PDFs of the amplifier papers so the assumed NEF range can be replaced by read values.
