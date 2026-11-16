# SeizeLUT-MS fabric blocks and the "ms1" kit

Phase 1 step 8 (MS_SPEC.md D-MS6 (a)). Everything here is separate from the FCCM kit in `hw/kv260/`, which is only read.

| file | what | status |
|---|---|---|
| `rtl/ms_impair.v` | impairment emulator, one channel, multiplier-free | bit-exact with `ms/py/impair.py` in Verilator (`python ms/py/impair_rtl.py`) |
| `rtl/ms_impair_axi.v` | AXI4-Lite wrapper (register map in its header), 512-entry FIFOs | bit-exact through bus transactions (`python ms/py/impair_rtl.py --axi`) |
| `rtl/sin4096.hex` | sine table, generated (`python ms/fpga/make_board_files.py`) | |
| `synth_yosys.sh` | Yosys cost estimate | 5,117 LUTs, 5,950 FFs, 2 RAMB36 + 2 RAMB18, 0 DSP (wrapper + core) |
| `vivado/build_ms1.tcl`, `build_ms1.sh` | Vivado batch build of the ms1 kit: FCCM core (unchanged) + emulator on one AXI bus | **written, not yet run** (no Vivado in the cloud session) |
| `board/ms_impair_kv260.py` | board driver and self-test (PYNQ, /dev/mem or a register emulator) | tested against the register emulator only |
| `board/vectors/impair_cases.npz` | self-test vectors from the golden model (`python ms/fpga/make_board_files.py`) | |

## Your steps (hardware), when you have time after FCCM work

1. Build (Linux/WSL with Vivado, about the time of the FCCM build): `bash ms/fpga/vivado/build_ms1.sh -jobs 8`.
   Check in `ms/fpga/out/build_summary.txt`: `timing_met=1`, two address lines (seizelut_0 and ms_impair_0), and
   `ms_impair_sine_rom_bram_cells` greater than 0 (the sine table was found; if it is 0 the table is missing, and the
   self-test's mains cases will fail). The script ends with "FCCM files unchanged".
2. Copy `ms/fpga/out/ms1.bit`, `ms/fpga/out/ms1.hwh` and the folder `ms/fpga/board/` to the board, keeping
   `ms1.bit`/`ms1.hwh` in `../out/` relative to the driver (or pass `--bit <path>`).
3. On the board: `sudo python3 ms_impair_kv260.py selftest`. Expected: every case `mismatches 0`, clip counts equal,
   `drops 0`, the negative control with tens of thousands of mismatches, and "ALL BIT-EXACT". It writes
   `results/selftest_pynq_<time>.json`: send that file back (commit it under `ms/fpga/board/results/`).

No wiring is involved: the emulator works on samples the ARM writes over the bus.
