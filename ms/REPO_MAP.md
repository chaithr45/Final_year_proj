# SeizeLUT repository map (Phase 0 inventory, 15 Nov 2026)

Written for the mixed-signal study (branch `FPGA`). Everything here was read from the repository or run in the
cloud session on 15 Nov 2026; nothing is quoted from memory.

## 1. Branches: where the real design lives

| Branch | State | Use it for |
|---|---|---|
| `claude/optimistic-heisenberg-ph0bvj` | **FCCM branch.** Frozen model, final test, KV260 kit v5, BIST, fault injection, paper. Tip `986c8ae` (15 Nov) | Read only. Never commit here from the mixed-signal work |
| `main` | Stale: PR #1 merged an early M4 state (`64bfab6`, DWN size sweep). No frozen model, no `hw/` | Nothing |
| `FPGA` | **Mixed-signal study.** Created from the FCCM tip `986c8ae`; adds only new files (`MS_SPEC.md`, `PREREG.md`, `LOG.md`, `LEARN.md`, `ms/`) and a short section in `CLAUDE.md` | All mixed-signal work |

To pick up later FCCM commits: `git fetch origin && git merge origin/claude/optimistic-heisenberg-ph0bvj` on `FPGA`.
New files never conflict; only `CLAUDE.md` might, and that is a two-line merge.

## 2. The frozen detector (what the mixed-signal study must not change)

| Item | Value | Source |
|---|---|---|
| Final model | `export/n4_distill_s0` (DWN distilled from LightGBM, seed 0, trained on all 96 training patients) | `export/n4_distill_s0/manifest.json` |
| Inputs | 38 of the 117 integer features (top 40 by LightGBM gain, 2 pruned as never read) | `thresholds.json` |
| Encoder | 146 thermometer comparators, `bit = feature > threshold` (signed integer) | `thresholds.json`, `hw/kv260/rtl/lutnet_classifier.v` |
| Network | 50 LUT6 in one layer: LUTs 0-24 vote background, 25-49 vote seizure | `head.json`, `luts.json`, `mapping.json` |
| Score and decision | score = popcount(seizure) - popcount(background), range -25..25; decision = score >= 9; alarm = 10 of the last 10 decisions; artefact gate none | `head.json` |
| Design frozen | 8 Nov 2026, 19:40 UTC (D39) | `results/decisions.md` |
| Inner-CV result of the recipe | event-F1 0.229, 0.9 FP/24 h (run `20261108-145504_n4_distill_s0`, out-of-fold over the 96 training patients) | D37 |
| Test result (29 patients, 5 seeds, scored once) | event-F1 0.248 +- 0.016, 0.8 FP/24 h, AUROC 0.883 | `results/tables/final_test.md` |
| Classifier cost | 398 LUTs, 454 FFs, 0 DSP, 0 BRAM, Fmax 467.7 MHz (Vivado 2026.1, out of context); 405 LUTs in Yosys | D41 bullet "Vivado 2026.1 build", `hw/kv260/measured/vivado_2026.1_kit_v5/` |
| Full KV260 design | 2,345 LUTs (2.0 %), 3,149 FFs, 9 BRAM tiles (BIST ROM), 0 DSP, timing met at 100 MHz (WNS +3.325 ns) | same |

Data facts used later: biopotentials at 256 Hz (EEG 2 ch behind the ear, ECG, EMG), chest ACC/GYR at 25 Hz;
883 seizures in the public release, **702 of them in the 96 training patients** (`results/audit/seizures.csv`);
8,714 h of training data, 31.4 M training windows (D41).

## 3. Where things live

### Integer front end (raw samples -> 117 features)
| What | File |
|---|---|
| Golden model (Python + numba), modes `int` and `float` | `src/features/golden.py` (`extract(signals, n_seconds, mode)`), kernels in `src/features/kernels.py`, biquads/log2 in `src/features/fixedpoint.py` |
| Feature list, widths, filter coefficients | `src/features/spec.py`, generated table `spec/fixed_point.md` |
| Input conversion | `golden.to_fixed`: physical units -> int16 at **0.25 uV/LSB** (biopotentials), 2^-12 g/LSB (motion), rounded and clipped (D16). **This is where the analog impairment emulator plugs in** |
| C port (batch and second-by-second streaming), bit-exact with the golden model on 431,960 windows | `hw/kv260/board/frontend/seizelut_fe.c`, `seizelut_fe_stream.c` |
| N10, front end in the fabric (FCCM work, in progress): microcoded feature engine, 2,323-instruction ROM, 930-word register file in block RAM; program bit-exact on 431,960 windows in the instruction-level C simulator; RTL not written yet | `src/hw/fe_engine.py`, `hw/kv260/sim/fe_isa_sim.c`, `scripts/verify_fe_engine.py`, `reports/PROGRESS.md` |

### Classifier
| What | File |
|---|---|
| DWN training code (pure PyTorch) | `src/models/dwn.py`, model registry `src/models/registry.py` |
| Inner CV and final training | `scripts/run_inner_cv.py`, `scripts/run_final.py`; config `configs/m5/n4_distill.yaml` |
| Export (thresholds, mapping, truth tables) and integer reference | `src/hw/export.py` (`load_export`, `golden_from_export`) |
| Verilog generator and the generated classifier | `src/hw/verilog.py`; `hw/kv260/rtl/lutnet_classifier.v` (with fault injection and debug taps), `lutnet_classifier_plain.v` |
| Post-processing and operating points | `src/eval/operating.py`, `src/models/postprocess.py` |
| Event scoring | `src/eval/szcore.py` (SzCORE), `src/eval/seizeit2.py` (dataset-paper metrics), `src/eval/stats.py` (Wilcoxon) |

### KV260 kit, BIST and fault injection
| What | File |
|---|---|
| AXI4-Lite core: feature/commit/result registers, programmable operating point, BIST, debug read-back, fault-injection registers | `hw/kv260/rtl/seizelut_axi.v`, register map `hw/kv260/rtl/seizelut_regs.json` and `hw/kv260/README.md` |
| RTL generator for the kit (BIST ROM, vectors) | `src/hw/kv260.py`, `scripts/make_kv260_rtl.py` |
| BIST ROM | `hw/kv260/rtl/seizelut_bist_rom.v`: 1,024 vectors = 255 coverage-selected + 769 recorded windows; one pass 1,028 cycles = 10.3 us at 100 MHz |
| Fault model and coverage (software, training patients only) | `scripts/fault_analysis.py`, `scripts/make_fault_list.py`, `results/tables/fault_*.json` |
| Fault injection in RTL | `lutnet_classifier.v` inputs `fi_b0/fi_b1` (comparator stuck-at), `fi_l0/fi_l1` (LUT output stuck-at), `fi_tt/fi_addr` (truth-table bit flip). **Thresholds are constants in the RTL**: programmable threshold offsets (Phase 2) need new hardware |
| Board software | `hw/kv260/board/run_tests.py` (steps 1-8), `fault_campaign.py`, `seizelut_kv260.py` (driver), `seizelut_model.py` (software reference) |
| Simulation | `hw/kv260/sim/tb_seizelut_axi.v`, `scripts/verify_kv260_rtl.py` (Verilator) |
| Vivado build | `hw/kv260/vivado/build_kv260.tcl`; your measured reports in `hw/kv260/measured/vivado_2026.1_kit_v5/` |

## 4. How to reproduce the frozen results

| Result | Command | Needs | Checked on 15 Nov (cloud) |
|---|---|---|---|
| Unit tests (features, eval, kit) | `pytest -q tests/test_kv260.py tests/test_features.py tests/test_eval.py` | `pip install -r requirements-ci.txt && pip install -e . --no-deps`, Icarus/Verilator | **32 passed** |
| KV260 core through its registers + all 3,592 single faults (Verilator) | `python scripts/verify_kv260_rtl.py --quick` | Verilator >= 5 | **ALL PASS: 848 window checks, 3,592 fault cases** (15 s). Note: `--quick` overwrites the committed full-run `hw/kv260/results/simulation_verification.json`; restore it with `git checkout -- hw/kv260/results/` |
| Same on all 10 recordings (431,960 windows) | `python scripts/verify_kv260_rtl.py` | the 10 `.hex` vector files from `hw/kv260/tools/make_board_vectors.py --tb` | not run: only 1 recording's vectors are committed |
| Front-end engine program vs C front end | `python scripts/verify_fe_engine.py --quick` | raw inputs under `export/n4_distill_s0/vectors/<rec>/inputs/` | **not reproducible from git**: only `manifest.json` is committed. Regenerating the inputs reads test-patient recordings (`scripts/make_test_vectors.py`), so it was not run (ground rule 2) |
| Inner-CV result of the frozen recipe | `python scripts/run_inner_cv.py --config configs/m5/n4_distill.yaml` | training feature cache `cache/features/int/` (7 GB, from `scripts/extract_features.py`, streams 126 GB from S3) | not run; the committed out-of-fold metrics are in `results/runs/20261108-145504_n4_distill_s0/` |
| Final model and test scores | `scripts/run_final.py ... --final-test` | test access (already done, logged) | not to be re-run |
| Paper | `cd paper && latexmk -pdf main.tex` | LaTeX | not run |

What is **not** in this cloud container and must come from your laptop or S3: raw data (`data/`), the feature
cache (`cache/`), fold checkpoints (`checkpoints/`). The cloud container that trained the CV folds is gone, so the
five fold models of the frozen recipe have to be retrained for the tolerance study (Phase 1 decision D-MS4).

Measured speed of the golden integer front end (cloud, one core, warm numba, training recording sub-001 run-01,
all four modalities, 18.1 h of signal): **11.1 s, about 5,900x real time**. One pass over the 8,714 training hours is
therefore about 1.5 core-hours of compute; downloading the raw EDFs (about 100 GB) is the larger cost.

## 5. Differences between the kickoff brief and the repository

| Brief says | Repository says | Consequence |
|---|---|---|
| "on-chip BIST (255 vectors, 10.3 us)" | The 255 coverage-selected vectors detect 100 % of the 2,890 decision-relevant single faults (and all 3,142 observable ones); the ROM holds 1,024 vectors and a full pass is 1,028 cycles = **10.3 us**. 10.3 us is the 1,024-vector pass, not 255 vectors (those would be about 2.6 us) | Quote it as "255 selected vectors give 100 % coverage; the full 1,024-vector self-test takes 10.3 us at 100 MHz" |
| Coverage "detects 100 %" | Shown in software and in Verilator RTL simulation (all 3,592 faults injected through the registers). **Board run of kit v5 still pending** (`reports/PROGRESS.md`) | Say "verified in RTL simulation" until the board run is back |
| Front end into the fabric via "Vitis HLS from the bit-exact C, LUT-only, C/RTL co-simulation" | N10 is a hand-written microcoded feature engine generated by `src/hw/fe_engine.py`, with its register file in **block RAM** (930 words) and a program ROM; not HLS, not LUT-only | Not ours to change (FCCM work); the in-fabric impairment emulator should connect to whichever front end exists (Phase 1 decision D-MS6) |
| Measured board numbers | Vivado reports exist (your build); the board test (`run_tests.py`), measured power and energy per decision are pending | The Phase 1 power budget's digital term needs the board run; until then it uses Vivado's estimate, labelled as such |
| Work on branch `mixed-signal` | Your later message: branch `FPGA` | Using `FPGA` |
