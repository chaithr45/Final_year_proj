# SeizeLUT on the Kria KV260: build and test guide

This kit puts the final SeizeLUT seizure classifier (50 six-input LUTs, 146 threshold comparators, no multipliers)
into the FPGA fabric of the AMD Kria KV260 and proves on the board that the hardware gives **exactly** the same
result as the software for every one-second window of 10 recordings (431,960 windows). The board also reports the
hardware cost, the latency, the throughput, the seizures the FPGA itself detects, and the measured power.

**Live demo (new in kit v4):** `demo/DEMO.md`. Recorded patient signals stream second by second through the
board, and the laptop's browser shows every stage. Demo 1 needs no extra parts and uses the board's own LEDs.
Demo 2 adds PMOD LEDs, a buzzer and a button (parts list in `demo/ORDER_NOW.md`). You can rehearse both on the
laptop without the board.

Everything in the kit was verified before shipping (see `results/`): the register interface and the classifier
(v4, with the demo LEDs, button and debug taps) were simulated window by window on all 431,960 windows at two
programmable operating points (863,920 window checks, comparator bits and LUT outputs included) with zero
mismatches, the C front end reproduced all 117 golden features of all 10 recordings exactly (batch and the
second-by-second streaming version used by the demo), the build script was executed end to end with
stand-ins for the Vivado commands, and the board test software was run against an emulated core. What cannot be run without your PC and board is Vivado itself and the board; this
guide covers those two parts.

## Quick start (if you already have Vivado and PYNQ on the board)

```
# PC (kit folder):
vivado -mode batch -source vivado/build_kv260.tcl         # about 15-30 minutes
copy out\seizelut.bit and out\seizelut.hwh into board\    # same base name, both files
scp -r board ubuntu@<board-ip>:~/seizelut
# Board:
sudo -i
source /etc/profile.d/pynq_venv.sh
cd /home/ubuntu/seizelut && python3 run_tests.py
```
Expected end of the output: `ALL TESTS PASSED`. Send back `board/results/kv260_results_*.json` and `out/` (reports).

---

## What you need

| Item | Notes |
|---|---|
| Kria KV260 Vision AI Starter Kit | with its 12 V power adapter, the micro-SD card, an Ethernet cable and the micro-USB cable |
| A PC with Windows 10/11 or Ubuntu (or WSL) | 16 GB RAM recommended (8 GB works for this small design), about 60-100 GB free disk for Vivado |
| Vivado **2022.1 to 2025.2**, free *Standard* edition | the K26 device needs no licence in these versions; 2026.1 changed the licensing, so avoid it |
| A router or switch | the board and the PC on the same network (Ethernet) |

## Part A: build the bitstream on your PC

**A1. Install Vivado (once, about 1-2 hours).** Download the *AMD Unified Installer for FPGAs & Adaptive SoCs*
(version 2024.2 or 2025.2) from amd.com (free account). In the installer choose **Vivado** and then
**Vivado ML Standard**. In the device list keep only **Zynq UltraScale+ MPSoCs** (and **Kria SOMs** if it is listed
separately); this keeps the install small. Vitis is not needed.

**A2. Unzip the kit** to a short path without spaces, for example `C:\seizelut_kv260` (long or spaced paths can
break Vivado on Windows).

**A3. Build.** Choose one:

* Windows, easiest: open **Vivado 2025.2 Tcl Shell** (or your version) from the Start menu, then
  ```
  cd C:/seizelut_kv260
  vivado -mode batch -source vivado/build_kv260.tcl
  ```
* Windows, double-click `vivado\build.bat` (it looks for Vivado in `C:\Xilinx` and `C:\AMDDesignTools`).
* Linux or WSL: `bash vivado/build.sh`

Options: `-tclargs -jobs 8` (faster on 8 cores), `-noboard` (skip the KV260 board files), `-nooc` (skip the
extra timing run of the classifier alone).

**A4. Check the result.** The build ends with `SEIZELUT: build finished`. In `out/` you must find
`seizelut.bit`, `seizelut.hwh` and `build_summary.txt` containing `timing_met=1` and `done=1`. Then run
`python tools/parse_reports.py` (any Python 3) to collect the numbers into `out/build_results.json`.

What the script builds: the Zynq UltraScale+ processing system with its `M_AXI_HPM0_LPD` port at 100 MHz
(the same choice as AMD's official KV260 PYNQ overlay), a reset block, an AXI interconnect and the SeizeLUT core
at address 0x8000_0000. It writes the bitstream, the PYNQ hardware handoff (`.hwh`), utilisation reports of
the whole design, the SeizeLUT core and the classifier alone, timing and power reports, and a second
out-of-context run of the classifier at 400 MHz to measure its maximum clock frequency.

If the board files are not installed, the script tries the Xilinx board store and otherwise continues with the
bare XCK26 part; both work for PYNQ.

## Part B: prepare the KV260 (once, about 1 hour)

**B1. Ubuntu image.** Download **Ubuntu Desktop 22.04 LTS for AMD Kria K26** from
`ubuntu.com/download/amd` (Kria-PYNQ needs 22.04, not 24.04) and write it to the micro-SD card with
Raspberry Pi Imager or balenaEtcher.

**B2. Boot firmware.** Older kits need the 2022.1 (or newer, not 1.04) boot firmware before Ubuntu 22.04 boots.
If the board does not reach the Ubuntu login, update it as described on the AMD Kria wiki ("Kria K26 SOM",
section *Boot Firmware Updates*): either the *Boot Image Recovery Tool* (hold the FWUEN button while powering
on, then open the recovery page in a browser over Ethernet), or from a running Linux with
`sudo xmutil bootfw_update -i <BOOT.BIN>`.

**B3. First boot.** Insert the card, connect Ethernet and power. Log in on the screen or over the serial port
(micro-USB, 115200 baud) as `ubuntu` / `ubuntu` and set a new password. Note the IP address: `hostname -I`.

**B4. Install PYNQ (about 25 minutes, needs internet on the board).**
```
git clone https://github.com/Xilinx/Kria-PYNQ.git
cd Kria-PYNQ/
sudo bash install.sh -b KV260
```
If the script stops at `apt-key ... keyserver`, run it again; if it keeps failing, that step only adds a
GStreamer package source that SeizeLUT does not need, so comment out the two lines starting with `apt-key adv`
and `echo "deb http://ppa.launchpad.net/ubuntu-xilinx` in `install.sh` and run it again.

**B5. Check PYNQ.** Open `http://<board-ip>:9090/lab` in a browser (password `xilinx`).

## Part C: run the tests on the board (about 10 minutes)

**C1. Copy the files.** Put `out/seizelut.bit` and `out/seizelut.hwh` into the `board/` folder (keep both
names), then copy the folder to the board:
* Windows PowerShell: `scp -r board ubuntu@<board-ip>:~/seizelut`
* or drag and drop with WinSCP, or upload in JupyterLab.

**C2. Run.** Over SSH (`ssh ubuntu@<board-ip>`) or a terminal in JupyterLab:
```
sudo -i
source /etc/profile.d/pynq_venv.sh
cd /home/ubuntu/seizelut
python3 run_tests.py --quick     # 1-minute smoke test (3 short recordings)
python3 run_tests.py             # full campaign: 10 recordings, metrics, power (a few minutes)
```
Alternatively open `seizelut/SeizeLUT_KV260.ipynb` in JupyterLab and choose *Run All*: it also plots the FPGA's
score and alarms around a seizure.

**C3. Send the results back.** `board/results/kv260_results_<time>_pynq.json` (everything the board measured)
and the `out/` folder from the PC (`build_results.json` and the `.rpt` files). In the project repository they go
to `hw/kv260/measured/`; `tools/` there turns them into the paper's hardware table.

## What the board test checks

| Step | Check | Pass when |
|---|---|---|
| 1 identity | overlay loads, ID `0x534C5554`, INFO (38 features, 50 LUTs, latency 3), register read/write | all match |
| 2 BIST | 1,024 golden vectors from on-chip memory streamed at one window per clock, compared **in hardware** | 1,024 / 1,024, 0 errors, ~1,028 cycles |
| 3 latency | clock cycles from COMMIT to RESULT | 3 cycles (30 ns at 100 MHz) |
| 4 replay | all 431,960 windows written over AXI; score, decision and alarm compared with the golden vectors and with the software model, at the frozen operating point and at the programmable one | 0 mismatches, counters agree |
| 5 detection | seizures detected and false alarms from the FPGA's own alarms (the dataset paper's definitions) | reported (no pass/fail) |
| 6 power | SOM power from the on-board INA260 monitor: overlay idle vs. the classifier running continuously | reported |
| 7 end to end | raw EEG/ECG/EMG/motion samples of 3 recordings -> integer front end in C on the ARM (all 117 features compared with the golden model) -> classifier in the fabric -> alarms compared with the golden model | 0 feature and 0 output mismatches; reports the front end's speed (x real time) |

Numbers the board must reproduce (they come from the simulation of the same RTL): BIST 1,024/1,024 in 1,028
cycles; latency 3 cycles; 0 mismatches on 431,960 windows; frozen operating point: 1 of 19 seizures, 0 false
alarms in 120 hours; programmable point (threshold 2, k 10): 3 of 19 seizures, 25 false alarms; end to end: 0
mismatches on the 3 raw recordings.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Vivado: `IP xilinx.com:ip:zynq_ultra_ps_e is not in this Vivado installation` | the Zynq UltraScale+ device family was not installed: re-run the installer, *Add devices* |
| Vivado: `validate_bd_design` errors | send `out/vivado_build.log`; try `-noboard` |
| Build ends with `WARNING timing not met` | send `out/timing_summary.rpt` (not expected: the design needs ~3 ns of logic per 10 ns) |
| Board: `ModuleNotFoundError: pynq` | run `source /etc/profile.d/pynq_venv.sh` first, as root |
| Board: `Permission denied` on `/dev/mem` | run as root (`sudo -i`) |
| Board: overlay fails to load / PL busy | `sudo xmutil unloadapp`, then run again |
| Board: `no seizelut IP in the overlay` | the `.hwh` is missing or has another base name than the `.bit` |
| Board: `fast C path unavailable` | harmless; the Python path is used (slower). `sudo apt install gcc` enables the fast path |
| Board: step 7 fails with `FileNotFoundError: gcc` | `sudo apt install gcc`, then run again (the front end is compiled on the board) |
| Board: `no hwmon power sensor found` | read the power by hand with `sudo xmutil platformstats -p` while the test runs |
| Anything else | send the full console output and the results JSON |

## Kit contents

| Path | Content |
|---|---|
| `rtl/` | `seizelut_axi.v` (AXI4-Lite core, BIST, programmable operating point), `lutnet_classifier.v` (the classifier, generated from the trained model), `seizelut_bist_rom.v` (self-test vectors), `seizelut_regs.json` (register map), `baselines/` (TreeLUT and logic-gate-network classifiers for the cost comparison; synthesised out of context by the build) |
| `vivado/` | `build_kv260.tcl` (one-step build), `build.bat`, `build.sh`, `kv260_pmod.xdc` (PMOD pins for the demo LEDs, buzzer and button) |
| `demo/` | live demo: `DEMO.md` (guide and presenter script), `ORDER_NOW.md` (parts and wiring for Demo 2), `demo1_now.sh`, `demo2_components.sh`, `rehearse_laptop.sh` / `.bat`, `net_direct.sh`, `seizelut_demo.py` (server, Python standard library + numpy), `board_io.py` (board LEDs and button), `web/` (dashboard), `segments/` (5 recorded inputs) |
| `board/` | `run_tests.py` (test campaign), `seizelut_kv260.py` (driver), `seizelut_model.py` (software reference), `fastio.c` (fast register streaming), `SeizeLUT_KV260.ipynb`, `model/` (trained model), `vectors/` (features of 10 recordings), `raw/` (raw samples of 3 recordings), `frontend/` (integer front end in C: `seizelut_fe.c` batch and `seizelut_fe_stream.c` second by second, both bit-exact with the golden model; `prebuilt/` libraries for the board's ARM, Linux x86-64 and Windows, used when there is no gcc) |
| `sim/` | `tb_seizelut_axi.v` and `run_sim.sh` (Icarus Verilog), one bundled recording |
| `tools/` | `parse_reports.py` (Vivado reports to JSON), `make_board_vectors.py` and `make_frontend_header.py` (regenerate vectors and the front end's constants, need the repository) |
| `results/` | verification already done: `simulation_verification.json`, `frontend_c_verification.json`, `yosys_synthesis.json`, `hw_synthesis_yosys.json` (all three classifiers), `board_campaign_emulated.json` |

## Register map (base address from the `.hwh`, normally 0x8000_0000)

| Offset | Name | Access | Meaning |
|---|---|---|---|
| 0x000 | ID | R | 0x534C5554 |
| 0x004 | INFO | R | latency, LUTs, features, version |
| 0x008 | CTRL | W | bit0 soft reset, bit1 clear counters, bit2 BIST start, bit3 BIST loop |
| 0x00C | STATUS | R | bit0 result valid, bit1 BIST busy, bit2 BIST done, bit3 BIST pass |
| 0x010 | COMMIT | W | artefact flags in bits 1:0; classifies the feature registers |
| 0x014 | RESULT | R | score [7:0], decision [8], alarm [9], decision2 [10], alarm2 [11], valid [15], count [31:16] |
| 0x018-0x024 | NWIN, NDEC, NALARM, LATENCY | R | counters, latency in cycles |
| 0x028 / 0x02C | CYCLES / SCRATCH | R / RW | cycle counter, test register |
| 0x030-0x044 | BIST_N, BIST_OK, BIST_ERR, BIST_CYC, BIST_RUNS, BIST_FIRSTERR | R | self-test results |
| 0x048 / 0x04C | OP_THR / OP_K | RW | programmable decision threshold and k |
| 0x050 / 0x054 | NDEC2 / NALARM2 | R | counters of the programmable path |
| 0x058 | IO_CTRL | RW | bit0 PMOD LEDs automatic (1) or manual, bit1 LEDs follow the programmable path, bit2 buzzer enable, bit3 buzzer active-low |
| 0x05C | IO_MANUAL | RW | PMOD outputs in manual mode (bits 6:0 = A1 A2 A3 A4 B1 B2 B3) |
| 0x060 | BTN | R | PMOD button: pressed [0], number of presses [31:16] (debounced) |
| 0x064 | IO_STATE | R | the seven PMOD output pins as driven |
| 0x070-0x080 | DBG_BITS0-4 | R | the 146 comparator bits of the last window |
| 0x084-0x088 | DBG_LUTS0-1 | R | the 50 LUT outputs of the last window (0-24 background, 25-49 seizure) |
| 0x100 + 4i | FEAT i | RW | features 2i (bits 15:0) and 2i+1 (bits 31:16), int16 |
