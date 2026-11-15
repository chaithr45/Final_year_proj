# SeizeLUT: progress and hand-off (read this first if you continue the work)

Last updated: 15 Nov 2026 (cloud session). Rules: `CLAUDE.md` (test patients, `--final-test`, no invented numbers,
branch `claude/optimistic-heisenberg-ph0bvj`, commit trailers, keep model names out of files). Every decision and
result: `results/decisions.md` (D1..D41 plus the dated bullets at the end).

## What the project is (one paragraph)
Patient-independent seizure detection on SeizeIT2 (125 patients; behind-the-ear EEG, ECG, EMG, motion) with a
LUT-native classifier: integer multiplier-free front end (117 features, C on the ARM, bit-exact with
`src/features/golden.py`), thermometer encoding (146 comparators on 38 features), a DWN of 50 LUT6, popcount score,
10-of-10 alarm. Final model `export/n4_distill_s0` (distilled from LightGBM). Hardware: Kria KV260 kit in `hw/kv260/`
(AXI4-Lite core, BIST, fault injection, demo). Main novelty for the paper: self-testing (exhaustive single-fault
analysis + coverage-selected BIST, N9).

## Status by workstream

| Workstream | State | Where |
|---|---|---|
| M1-M6 (data, models, final test) | done | `results/decisions.md`, `results/tables/` |
| Post-ictal two-stage detector (D40) | done; verifier synthesised 799 LUTs, cascade ~1,200 | `results/tables/paper_points_*`, `results/tables/verifier_hw.json`, `export/verifier_d96_s0/` |
| Self-testing N9 (D41) | done: 3,592 faults; 255 selected BIST vectors detect 100 % of decision-relevant faults; RTL fault injection verified on all faults (Verilator) | `scripts/fault_analysis.py`, `results/tables/fault_*.json`, `hw/kv260/board/fault_campaign.py` |
| KV260 kit v5 | done; built by the user with Vivado 2026.1 (timing met; DWN 398 LUT, 468 MHz) | `hw/kv260/`, `hw/kv260/measured/vivado_2026.1_kit_v5/`, `hw/kv260/dist/SeizeLUT_KV260_kit_v5.zip` |
| Live demo (Demo 1 board LEDs, Demo 2 PMOD parts) | done | `hw/kv260/demo/DEMO.md`, `ORDER_NOW.md` |
| Paper (6 pages, IEEE conf) | drafted; red `[board]` marks wait for the board run | `paper/main.tex`, `paper/tables/`, `paper/figures/` |
| **Board run** | **pending (user)**: `run_tests.py` on the KV260 with the v5 bitstream; send `board/results/kv260_results_*.json` | kit README part C |
| **N10 front end in the fabric** | **in progress** (see below) | `src/hw/fe_engine.py` and friends |
| Conferences | plan: EMBC 2027 (24 Jan 2027) or FCCM 2027 (17 Jan 2027), then BioCAS 2027 (~7 May) / NER (15 Mar) / AICAS (13 Apr) | chat answer of 15 Nov; verify dates |

## N10: integer front end in the FPGA fabric (current work)
Goal: the whole detector as multiplier-free hardware (front end + classifier), with a synthesised and verified cost.

Design: a microcoded feature engine (`src/hw/fe_engine.py` docstring): accumulator machine, one adder/shifter, register
file in block RAM (930 of 1,024 words), program ROM (2,323 instructions), events BIO (256 Hz sample), MOV (25 Hz),
SEC (end of second -> window w-1... features of the window that ended one second ago), FLUSH. Computes only the 38
features the classifier reads. Coefficients are CSD (<= 5 signed powers of two each), so no multiplier.

Done:
1. Generator `src/hw/fe_engine.py` (ISA, assembler, program, `write_images` -> `hw/kv260/rtl/fe/fe_rom.hex`,
   `fe_ram.hex`, `fe_engine.json`).
2. Instruction-level C simulator `hw/kv260/sim/fe_isa_sim.c`.
3. `scripts/verify_fe_engine.py`: **all 431,960 windows of the 10 exported recordings bit-exact** with the C front end
   (all 38 features). ~281k instructions per second of signal (BIO 1,090 per sample, MOV 47, SEC 992).
   Largest value 2^34 = the empty-slot constant BIG; real data < 2^31. Worst-case bound of the biquad accumulator
   ~2.4e11 (< 2^38), so a 40-bit datapath is safe for any input (plan: DW = 40, BIG = 2^30).
   `--tb` writes RTL testbench vectors to `hw/kv260/sim/fe_vectors/` (sub-097_run-10, sub-100_run-03).

Next steps (in order):
4. Set DW = 40 and BIG = 2^30 in `src/hw/fe_engine.py`; rerun `python scripts/verify_fe_engine.py --tb` (must stay
   bit-exact).
5. Write `hw/kv260/rtl/fe_engine.v` (FSM fetch/read/exec, 3 cycles per instruction; ROM/RAM via $readmemh of
   `rtl/fe/*.hex`; host write/read port when idle; start + entry; busy) and `hw/kv260/sim/tb_fe_engine.v` (reads
   `fe_vectors/<rec>.samples.hex`, drives events, compares FEAT_0..37 with `<rec>.feats.hex`). Run with Verilator
   (`--binary --timing`) on both recordings; expect 0 mismatches.
6. Cost: Yosys `synth_xilinx -family xcup` on fe_engine (LUT/FF/BRAM/DSP = 0), Fmax not needed (any clock >=
   ~0.85 MHz is real time at 3 cycles per instruction). Save `results/tables/fe_engine_hw.json`.
7. Optional (kit v6): put the engine in front of the classifier in `seizelut_axi.v` (ARM writes raw samples, fabric
   computes features and classifies), board test step for end-to-end in the fabric; Vivado OOC run of the engine.
8. Paper: add the result (whole detector LUT/BRAM, cycles per second, real-time clock) to the hardware section and
   the abstract; decisions.md entry (D42); README/kit docs; commit.

## How to resume quickly
```
cd /home/user/Final_year_proj
python scripts/verify_fe_engine.py --quick         # engine program vs C front end, 2 recordings, ~5 s
python scripts/verify_kv260_rtl.py --quick         # KV260 core + 3,592 fault cases (Verilator)
python -m pytest -q tests/test_kv260.py tests/test_hw.py
cd paper && latexmk -pdf main.tex                   # paper (6 pages)
```
Gotchas: `yowasp-yosys` runs sandboxed: give it relative paths and `cwd`; write reports with `tee -o file stat`.
The board kit zip is built with `python hw/kv260/tools/make_kit_zip.py --version vN` (dist/ is git-ignored).
Never run anything with `--final-test` without the user's go-ahead.

## Pending from the user
- Board run of kit v5 (results JSON) -> fill `[board]` marks in `paper/main.tex` (energy column of Table I,
  hardware section, KV260 implementation paragraph).
- Demo 2 parts (list in `hw/kv260/demo/ORDER_NOW.md`; plain buzzer needs a BC547 + 1 kohm, 1N4007 is fine as the diode).
