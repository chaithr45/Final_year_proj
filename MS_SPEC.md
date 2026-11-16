# SeizeLUT-MS: specification, decisions and status

**Goal.** Turn SeizeLUT into "a mixed-signal wearable seizure detector, co-designed from the comparator up to the
LUT network, with a measured analog front end", without touching the frozen detector, the test patients or the
FCCM work.

Companion files: `PREREG.md` (anything that touches test patients), `LOG.md` (problems and fixes), `LEARN.md`
(concepts for the interview), `ms/REPO_MAP.md` (what exists and where), `ms/setup/IIC_OSIC_TOOLS.md` (analog tools).

## Status

| Phase | Content | State |
|---|---|---|
| 0 | Inventory, planning files, analog tool setup | done on my side (15 Nov); **your container check pending** (`ms/setup/check_tools.sh`) |
| 1 | Detector-derived analog front-end specification | **started 16 Nov** (decisions D-MS4..D-MS10 settled: your go-ahead "do what you think is best") |
| 2 | Comparator design (SKY130) and offset tolerance on the FPGA | Feb-Mar 2027 |
| 3 | FPGA delta-sigma ADC, designed and measured | Mar-Apr 2027 |
| 4 | Measured analog chain into the detector | Apr-May 2027 |
| 5 | Write-up | May 2027 |

FCCM (17 Jan 2027) comes first. Phase 1 runs before then only where it does not take time from FCCM.

## Fixed inputs (do not change)

The frozen detector `export/n4_distill_s0`: 38 integer features, 146 thermometer comparators, 50 LUT6 (25 vote
background, 25 seizure), score = popcount difference, decision score >= 9, alarm 10 of 10. Inputs are int16 at
0.25 uV/LSB (EEG, ECG, EMG at 256 Hz) and 2^-12 g/LSB (chest ACC/GYR at 25 Hz). Details and sources:
`ms/REPO_MAP.md` §2.

## Decisions

Status: **decided** (in force), **proposed** (my recommendation, waiting for your OK), **open** (you choose).
On 16 Nov you answered the Phase 0 questions with "do what you think is best": every proposal below became
**decided** as proposed, and the two open items took my recommendation.

| ID | Decision | Status | Why |
|---|---|---|---|
| D-MS1 | All mixed-signal work on branch `FPGA`, created from the FCCM branch tip `986c8ae`. Only new files are added, plus a short section in `CLAUDE.md`. FCCM commits come in with `git merge origin/claude/optimistic-heisenberg-ph0bvj` | decided (your message, 15 Nov) | The frozen model, kit and fault injection exist only on the FCCM branch (`main` is stale). Branching from its tip gives us the design without changing it |
| D-MS2 | Layout: the four planning files at the repo root; code, netlists and results under `ms/` (`ms/analog/`, `ms/fpga/`, `ms/py/`, `ms/results/`). One script per figure or table | decided | Keeps FCCM files untouched and makes merges trivial |
| D-MS3 | Analog tools: IIC-OSIC-TOOLS release 2026.10 (ngspice-47, Magic 8.3.685, netgen 1.5.324, KLayout 0.30.12) with SKY130A from open_pdks `1689ac3f`. Cloud reference simulations use the same PDK commit with ngspice-42 | decided | Free, runs on both of your machines, and the PDK is pinned, so simulations are reproducible |
| D-MS4 | Models for the tolerance study: **retrain the 5 inner-fold models of the frozen recipe** (`configs/m5/n4_distill.yaml`, seed 0) so every training patient is scored by a model that never saw it. First check that they reproduce the committed out-of-fold result of run `20261108-145504_n4_distill_s0` (event-F1 0.229, 0.9 FP/24 h). Then train seeds 1-4 of the same folds to measure the run-to-run spread | decided (16 Nov) | The frozen `n4_distill_s0` was trained on all 96 training patients, so scoring it on them is in-sample and flatters the clean baseline. The fold checkpoints of the original CV run were in a cloud container that no longer exists |
| D-MS5 | Sweep data: (1) a **sweep subset** of the 96 training patients, fixed before any sweep: every training seizure (702) with 20 min before onset and 10 min after offset, plus 4 random background hours per patient (seeded draw, at least 30 min from any seizure; 1-h blocks, or whole recordings of >= 10 min where a patient's files are shorter than 1 h, amended 16 Nov before any sweep, LOG L13). Every segment gets 10 min of warm-up for the 64 s baselines, and warm-up windows are not scored. (2) Each tolerance limit is **confirmed on all 8,714 training hours** at the limit and one step beyond | decided (16 Nov) | The golden front end runs about 5,900x real time per core (measured), so compute is fine. Moving about 100 GB of raw EDF from S3 for every sweep point is not. The subset is roughly 10 % of the data and can be cached as int16. Subset numbers are used for curves; full-data numbers are used for the spec |
| D-MS6 | Where the in-fabric impairment emulator sits | decided (16 Nov): build and verify standalone, integrate as (a), move to (b) when N10 RTL exists | (a) Now, kit "ms1" (separate bitstream; FCCM kit untouched): ARM writes raw samples, the fabric impairs them, the ARM front end (C) computes features, and the fabric classifier decides. Works with today's kit. Register traffic limits speed to roughly the subset size per sweep point. (b) Later, after N10's feature-engine RTL exists: raw -> impairment -> feature engine -> classifier, all in the fabric. This is the stronger "board runs the sweep" story but depends on FCCM work. **Recommendation:** build and verify the block standalone now, integrate as (a), and move to (b) when N10 lands |
| D-MS7 | Noise generator in the fabric: a multiplier-free design. Uniform bits from xoroshiro128+ (constants 24, 16, 37; identical to the `randomgen` reference over 100,000 outputs); Gaussian via the sum of **64** uniform 12-bit values (amended 16 Nov from 16, see LOG L12: the exact distribution of a 16-sum has only 41 % of the Gaussian tail beyond 4 sigma; a 64-sum has 83 %, max CDF error 4.3e-4), accumulated serially (one adder; 16 generator steps per sample); amplitude set by a shift plus a 4-term signed-power-of-two mantissa; 1/f noise via the Voss-McCartney method (octave-rate random rows, adders only). The Python model uses the same integer algorithm, so the board and Python produce identical sequences for the same seed | decided (16 Nov) | Matches SeizeLUT's no-multiplier story and makes bit-exact checking possible. The 64-sum is not exactly Gaussian (support +-13.9 sigma; tail beyond 4 sigma 83 % and beyond 5 sigma 62 % of Gaussian; computed exactly by convolution). This is tested and reported, and one noise level is also run with an exact Gaussian to show the difference does not matter for the detector (A/B, step 5). Fall-back if it does: an inverse-CDF table |
| D-MS8 | ADC model parameterised by **input-referred LSB q** and **input-referred clip level C**, not by "bits" alone; bits = log2(2C/q). Today's pipeline is q = 0.25 uV, C = 8.19 mV (16 bits) | decided (16 Nov) | "8 bits" means nothing without a full scale. A real front end chooses gain (which sets C) and ADC bits separately. This makes the amplifier-gain/ADC trade visible |
| D-MS9 | Sampling-rate sweep | decided (16 Nov): (ii), with (i) as an appendix only if time allows | The frozen front end is fixed at 256 Hz. A lower ADC rate only makes sense with interpolation back to 256 Hz, which is a different system. Options: (i) Python only, sample-and-hold to fs then re-interpolate, flagged approximate; (ii) drop it and study anti-alias filtering at 256 Hz instead (mains harmonics fold into the band; see below). **Recommendation: (ii)**, plus (i) as a short appendix if time allows |
| D-MS10 | Definition of "tolerated" (below) | decided (16 Nov); the two deltas are measured and written below **before the first sweep** | Brief, Phase 1 |

### D-MS10 (decided 16 Nov) Definition of "tolerated"

An impairment level is **tolerated** by the frozen detector if, scored out-of-fold on the 96 training patients
with the frozen recipe's fold models (D-MS4), at the frozen operating point (score >= 9, 10 of 10, no gate), and
averaged over 5 impairment seeds:

1. event-F1 (SzCORE) is not below the clean value by more than **delta_F1 = sigma_seed(F1)**, and
2. false alarms per 24 h are not above the clean value by more than **delta_FA = sigma_seed(FP/24 h)**,

where sigma_seed is the standard deviation across 5 training seeds of the clean out-of-fold result. It is measured
first and written here before any sweep. Floors: delta_F1 >= 0.005, delta_FA >= 0.1 per 24 h, so the definition never
demands a difference smaller than the scoring resolution. A level is tolerated on the full training set (D-MS5 (2)) when, in
addition, the paired per-patient Wilcoxon test of impaired vs clean event-F1 is not significant (p >= 0.05). The
**tolerance limit** of a parameter is the worst tested level that is tolerated, with all other impairments at
their clean values.

Two details settled 16 Nov before any sweep result existed (LOG L15):
- sigma_seed is measured on the same data each test uses: the **subset** spread (clean subset run of each seed's fold
  models) for the subset tolerance curves, the **full** spread (all training hours, out-of-fold) for the full-data
  confirmations. Both are written below. Command: `python ms/py/deltas.py` -> `ms/results/phase1/deltas.json`.
- "Worst tested level that is tolerated" means: the most severe level of the unbroken run of tolerated levels that
  starts at the mildest level. A tolerated level after a failing one is reported as non-monotonic and does not
  extend the limit. If every level is tolerated, the limit is "beyond the grid" (the worst tested level is a lower
  bound). Command: `python ms/py/tolerance.py` -> `ms/results/phase1/tolerance.json`, `tolerance_table.md`.

Measured values (written before the first sweep):

| data | seeds | F1 mean +- sd | FP/24 h mean +- sd | delta_F1 | delta_FA |
|---|---|---|---|---|---|
| subset (curves) | pending | | | | |
| full (confirmation) | pending | | | | |

## Phase 1 plan: detector-derived front-end specification

Question: what is the cheapest analog front end (amplifier + ADC) the frozen detector can live with?

### 1.1 Impairment model (identical in Python and in the fabric)

All arithmetic is integer on the 0.25 uV/LSB input grid, with 4 extra fractional bits inside the block. Order
follows the physical chain, electrode to ADC:

```
x  (recorded signal, int16 at 0.25 uV)
 + mains(t)       50 Hz plus harmonics; harmonics above 128 Hz enter at their aliased frequency, scaled by the
                  anti-alias filter's attenuation at the true frequency
 + offset + drift DC offset (uV) and a slow ramp (uV/s) or random walk
 + n_white + n_1/f  input-referred amplifier noise (D-MS7), set as density (nV/sqrt(Hz)) and reported also as
                  uV rms over the modality's band
 * (1 + eps)      gain error (shift-add, CSD)
 -> H_AFE(z)      front-end bandwidth: high-pass corner and anti-alias low-pass corner (biquads, shift-add)
 -> clip(+-C)     input-referred clip level (D-MS8)
 -> quantise(q)   input-referred LSB (D-MS8), round to nearest
 -> int16 at 0.25 uV/LSB into the unchanged golden front end
```

Mains aliasing, computed: at 256 Hz sampling, the 150, 200, 250, 300 and 350 Hz harmonics appear at 106, 56,
**6**, 44 and 94 Hz. The 5th harmonic lands at 6 Hz, inside the 4-8 Hz theta band. 7 of the detector's 38
features read that band (`eeg_theta_mean/max/absdiff`, `eeg_ch1_theta`, `eeg_ch2_theta`, two `_ctx` versions),
and they feed 30 of the 146 comparators (counted from `thresholds.json`). The front end's 50 Hz notch does not
remove a 6 Hz tone. The anti-alias filter must, so the 250 Hz attenuation becomes a derived spec.

Honesty note for the write-up: the recordings already contain the original wearable's noise, filtering and mains.
Every sweep measures tolerance to **additional** impairment on top of that. The original device's ADC
resolution and noise are not documented in the repository; the EDF storage scale (about 0.02 uV/LSB for EEG,
`results/audit/signal_channels.csv`) is the file format's scale, not a measured ADC spec. Phase 1 estimates the
recordings' own noise floor from their quietest segments and states it.

Measured on all 899 subset segments (`python ms/py/signal_levels.py` -> `ms/results/phase1/signal_levels.json`;
0.5-100 Hz, 1-s blocks; motion 0.5-12 Hz):

| modality | channels | typical level: median of per-channel median RMS (IQR) | quietest second: median of per-channel 1st percentile |
|---|---|---|---|
| EEG | 1,796 | 13.1 uV (8.9-19.9) | 7.0 uV |
| ECG | 871 | 53.5 uV (36.2-74.9) | 30.9 uV |
| EMG | 871 | 17.7 uV (10.9-39.2) | 9.9 uV |
| motion | 4,806 | 3.2 LSB (2.0-6.4) | 1.1 LSB |

The quietest-second column is an upper bound on each recording's own noise floor (it still holds some signal).
So an added white noise of, say, 1 uV rms on EEG sits below a floor that is already about 7 uV in the median
channel; added noise adds in power, so 1 uV on 7 uV raises the floor by about 1 %. Expect the EEG noise limit to land
at several uV, and read it as "additional noise the detector tolerates on top of the SeizeIT2 device's own".

### 1.2 Steps (one command each; all on training patients)

Progress (16 Nov): step 2 done: `python ms/py/make_subset.py` -> `ms/results/phase1/subset.json`: 96 patients,
899 segments, all 698 training seizure intervals (702 annotations; 5 overlapping ones in sub-055 run-01 merge into
one, as in the pipeline), 389 h of background, 667 h scored, 792 h processed with warm-up. Three patients have
little or no seizure-free background (sub-087 0.4 h, sub-090 and sub-091 none: almost every recording holds a
seizure). Step 3 done: `ms/py/impair.py`, 14 tests (`pytest -q ms/py/tests`). Step 1 waits for the training
feature cache (extraction running). Step 8, first part done: the RTL emulator `ms/fpga/rtl/ms_impair.v` (one channel) is bit-exact with
`impair.py` on 11 configurations x 70,000 samples, with a negative control (`python ms/py/impair_rtl.py` ->
`ms/results/phase1/impair_rtl_check.json`). Yosys (`synth_xilinx -family xcup`): 4,713 LUTs, 5,731 FFs, 2 RAMB36
(sine table), 0 DSP per channel (`ms/results/phase1/impair_rtl_yosys.txt`); the 80 configuration words and the
64-bit state dominate, so there is room to shrink it if several channels are needed. AXI4-Lite wrapper
`ms/fpga/rtl/ms_impair_axi.v` (register map in its header; 512-entry input and output FIFOs) is bit-exact with
`impair.py` through real bus transactions on the same 11 configurations x 70,000 samples, negative control caught,
no dropped samples (`python ms/py/impair_rtl.py --axi` -> `ms/results/phase1/impair_rtl_axi_check.json`). Yosys:
5,117 LUTs, 5,950 FFs, 2 RAMB36 + 2 RAMB18, 0 DSP (`bash ms/fpga/synth_yosys.sh` ->
`ms/results/phase1/ms_impair_axi_yosys.txt`). One instance serves all channels in turn: the ARM loads a channel's
configuration (its own seeds), streams that channel, then the next. Not yet done: Vivado block design of the "ms1"
kit, ARM driver, board build.

1. Retrain the 5 fold models (D-MS4, seed 0) and check them against run `20261108-145504_n4_distill_s0`.
   Train seeds 1-4 and record sigma_seed in D-MS10.
2. Build the sweep subset (D-MS5): segment list committed to `ms/results/phase1/subset.json` before any sweep;
   cache the raw int16 inputs.
3. Python impairment model `ms/py/impair.py` with unit tests, including the noise-generator distribution tests.
4. Clean run of the subset through the unimpaired model, which must equal the cached clean features
   bit-for-bit. That proves the pipeline before any impairment.
5. Sweeps, one modality at a time (EEG 2 ch together; ECG; EMG; motion), one parameter at a time, 5 impairment seeds:

   | Parameter | Levels (EEG; other modalities scaled to their signal size) |
   |---|---|
   | LSB q | 0.25, 0.5, 1, 2, 4, 8, 16, 32, 64, 128, 256 uV (16 down to 6 bits at C = 8.19 mV) |
   | clip level C | 8.19, 4, 2, 1, 0.5 mV |
   | white noise | 0, 0.25, 0.5, 1, 2, 4, 8 uV rms in 0.5-100 Hz |
   | 1/f corner at a fixed white level | 0.1, 1, 10, 30 Hz |
   | gain error | 1, 2, 5, 10, 20, 50 % |
   | DC offset (as fraction of C) / drift | 0, 0.1, 0.3, 0.6, 0.9 / 0, 1, 10, 100 uV/s |
   | mains 50 Hz (+ harmonics) | 0, 1, 10, 100, 1,000 uV |
   | anti-alias corner and order | 128 Hz/1st order down to 40 Hz/2nd order; HP corner 0.05-1 Hz |

6. Mechanism table: for each impairment, how far each of the 38 features moves (in LSBs) and how many of the 146
   comparator bits flip. This links Phase 1 to Phase 2.
7. Full-data confirmation at each limit (D-MS5 (2)), then the front-end spec table
   (`python ms/py/confirm_full.py --models <seed-0 fold models>`, `python ms/py/spec_table.py`).
   7b (added 16 Nov, before any sweep result). **Combined spec point.** Each limit is measured with every other
   impairment clean, and tolerances measured one at a time need not add up. The spec point (all impairments of all
   modalities at their limits at once) is run on the subset and on the full training set with the same D-MS10 test.
   If it fails, the limits that move the features most (mechanism table, step 6) are backed off one grid step at a
   time, most-moving first, until the combined point passes. The spec table reports the combined point.
8. In-fabric emulator: Verilog block plus Python golden model, Verilator word-for-word check, then board runs of the
   subset at selected points (D-MS6).

### 1.3 From tolerances to power

| Block | Model | Inputs (each read from its source, cited) |
|---|---|---|
| Amplifier, per channel | NEF definition solved for current: I = NEF^2 * pi * U_T * 4kT * BW / (2 * v_ni^2), P = I * VDD. Current scales as 1/noise^2 | NEF and VDD of published biopotential amplifiers, each read from its paper |
| ADC, per channel | P = FOM_W * 2^ENOB * f_snyq, or P = (f_snyq/2) * 10^((SNDR - FOM_S)/10). Definitions as computed in the survey's own cells: FOM_W = (P/f_snyq) / 2^((SNDR - 1.76)/6.02); FOM_S = SNDR + 10 log10(f_snyq/2/P); f_snyq = f_s/OSR | Murmann ADC Performance Survey 1997-2026 (rev. 20260801, read 15 Nov). Caveat: survey designs run far faster than 256 S/s, where static power dominates, so we also report the energy per sample of the lowest-rate designs as a floor |
| Digital | front end + LUT network energy per decision | Board measurement of kit v5 (pending). Until then Vivado's estimate, labelled as an estimate |

Deliverables: tolerance curves (one figure per modality), the front-end spec table, and the electrode-to-alarm power
budget figure compared with published wearable EEG front ends (each value read from its paper).

## Phase 2-4 notes collected during the inventory

- **Phase 2 needs new RTL.** The 146 comparisons in `lutnet_classifier.v` compare against constants. Per-comparator
  offsets mean comparing against programmable values (146 registers and comparators against variables), which
  costs LUTs. It goes into a separate MS build, never into the FCCM kit.
- **Phase 2, scale of a comparator offset.** Most compared features are log2 values with 3 fractional bits: one
  feature LSB is a factor of 2^(1/8), about 9 % (0.75 dB) in the underlying signal sum. Translating a threshold offset in
  feature LSBs into an analog comparator offset depends on what the analog comparator would see. That mapping is
  part of the Phase 2 hand analysis, and the write-up must say it is a model, not an analog implementation (brief).
- **Gain error, expected effect (to be tested, not assumed).** A gain error eps shifts every log2 feature by
  log2(1+eps): about 0.5 feature LSB at eps = 4.4 %. The `_ctx` features subtract a 64 s running baseline and
  should cancel a constant gain error.
- **Phase 2 board runs** use the frozen hardware model, which is in-sample on training patients. Their purpose is to show
  that the board equals the Python model bit for bit; the tolerance numbers come from the out-of-fold Python runs.

## Verified references (read or checked on 15 Nov 2026)

- M. J. M. Pelgrom, A. C. J. Duinmaijer, A. P. G. Welbers, "Matching properties of MOS transistors," IEEE J.
  Solid-State Circuits, vol. 24, no. 5, pp. 1433-1439, Oct. 1989, doi:10.1109/JSSC.1989.572629 (IEEE record).
- M. S. J. Steyaert, W. M. C. Sansen, "A micropower low-noise monolithic instrumentation amplifier for medical
  purposes," IEEE J. Solid-State Circuits, vol. 22, no. 6, pp. 1163-1168, Dec. 1987. One later source lists a third
  author (Zhongyuan); the author list is to be confirmed on IEEE Xplore before citing. NEF definition confirmed in
  secondary sources only so far.
- R. H. Walden, "Analog-to-digital converter survey and analysis," IEEE J. Sel. Areas Commun., vol. 17, no. 4,
  pp. 539-550, Apr. 1999, doi:10.1109/49.761034.
- B. Murmann, "ADC Performance Survey 1997-2026," https://github.com/bmurmann/ADC-survey (cloned 15 Nov 2026,
  commit `00b4b85`; FOM formulas read from the spreadsheet cells).
- IIC-OSIC-TOOLS, https://github.com/iic-jku/IIC-OSIC-TOOLS (commit `f15ef6a`, release 2026.10).

## Open questions for you

1. (answered 16 Nov) Decisions D-MS4..D-MS10: as recommended.
2. (answered 16 Nov) D-MS6 and D-MS9: as recommended.
3. Does your laptop still hold the training feature cache (`cache/features/int/`, about 7 GB) and/or the raw
   SeizeIT2 EDFs? If yes, Phase 1 can run there, or I can run it in the cloud from S3.
4. Which machine runs IIC-OSIC-TOOLS, and the result of `ms/setup/check_tools.sh`.
5. Kit v5 board run: once you have it, the measured energy per decision goes into the Phase 1 power budget.
