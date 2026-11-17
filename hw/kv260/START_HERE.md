# SeizeLUT on the KV260: step by step, from zero (kit v6)

This guide takes you from an unopened KV260 to the whole project running on the board: the integer front end
**and** the classifier in the FPGA fabric, the self-test, the fault-injection campaign, and the live demo with the
board's own LEDs. No extra parts and no buzzer are needed. Follow the parts in order. Each step says what you should
see; if you see something else, stop and look at **Troubleshooting** at the end.

What runs where in kit v6:

| Part | Runs on |
|---|---|
| Raw EEG, ECG, EMG and motion samples (recorded patient data) | read from the micro-SD card by the ARM |
| Integer front end (filters, R-peaks, 38 features) | **FPGA fabric** (feature engine, no multiplier) |
| Classifier (146 comparators, 50 LUTs, score, 10-of-10 alarm) | **FPGA fabric** |
| Self-test, fault injection | **FPGA fabric** |
| Web dashboard, board LEDs | ARM (Linux) and your laptop's browser |

Time needed: about 3 hours the first time (most of it is waiting for installs and the Vivado build).

---

## Part 0. What to have and what to download

**Hardware**

| Item | Notes |
|---|---|
| Kria KV260 Vision AI Starter Kit | the board |
| 12 V power adapter for the KV260 | the one sold for the kit (barrel plug) |
| micro-SD card, 32 GB or larger | it will be erased |
| micro-SD card reader for the PC | built in or USB |
| Ethernet cable | board to router, or board to laptop |
| micro-USB cable | only needed if you have no monitor (serial console) |
| Monitor (HDMI or DisplayPort) and USB keyboard | optional; the easiest way to do the first login |
| Your Windows PC with Vivado | you already built kit v5 with Vivado 2026.1; the same installation is fine |

**Downloads (on the PC)**

| File | Where | Why |
|---|---|---|
| `SeizeLUT_KV260_kit_v6.zip` | sent to you in the chat | everything for this project |
| Ubuntu Desktop 22.04 LTS image for AMD Kria K26 (one file ending in `.img.xz`, a few GB) | ubuntu.com/download/amd, choose **Kria K26** and **Ubuntu Desktop 22.04 LTS** | the board's operating system. It must be **22.04**: PYNQ does not install on 24.04 |
| balenaEtcher | etcher.balena.io | writes the image to the micro-SD card |
| PuTTY (optional) | putty.org | serial console if you have no monitor |
| WinSCP (optional) | winscp.net | drag-and-drop file copy to the board (the `scp` command below does the same) |

Unzip the kit to a short path without spaces: **`C:\seizelut_kv260_v6`** (the guide uses this path).

---

## Part A. Build the bitstream on the PC (about 30-45 minutes, mostly waiting)

You did this for kit v5; kit v6 has a new core (front end in the fabric), so it must be built again.

**A1.** Start **Vivado 2026.1** (the normal Vivado window). At the bottom there is a **Tcl Console** with a text box.

**A2.** Type these three lines into the Tcl Console, one at a time, each followed by Enter. They are Vivado
commands, not PowerShell commands, so do not type them in PowerShell.
```
cd C:/seizelut_kv260_v6
set argv {}
source vivado/build_kv260.tcl
```
(Use forward slashes `/` in the path.) The build runs synthesis, implementation, the bitstream and four extra
out-of-context cost runs. It prints many lines starting with `SEIZELUT:`.

**A3.** It is finished when the console prints **`SEIZELUT: build finished`**. Check the folder
`C:\seizelut_kv260_v6\out\`. It must contain:
* `seizelut.bit` and `seizelut.hwh`
* `build_summary.txt`, which must contain the lines `timing_met=1` and `done=1`

**A4.** Copy **`out\seizelut.bit`** and **`out\seizelut.hwh`** into **`C:\seizelut_kv260_v6\board\`**. Keep both
names exactly as they are.

**A5.** Zip the whole `out` folder (right-click, *Send to*, *Compressed (zipped) folder*) and keep `out.zip`: you
will send it back with the board results.

*Optional, no board needed:* double-click `demo\rehearse_laptop.bat` to see the live dashboard on the laptop
(software model of the core) while you wait.

---

## Part B. Prepare the KV260 (once, about 1-1.5 hours)

**B1. Write Ubuntu to the micro-SD card.** Open balenaEtcher, *Flash from file*, choose the Ubuntu `.img.xz`
file, *Select target*, choose the micro-SD card (check the size so you do not erase another drive), *Flash*. Wait
until it says *Flash Complete* (10-20 minutes).

**B2. Connect the board** (power still off):
1. micro-SD card into the board's micro-SD slot (it clicks in).
2. Ethernet cable from the board's Ethernet port to:
   * **your router** (simplest: the board gets internet from it), or
   * **your laptop's Ethernet port** with internet sharing. On Windows: *Control Panel*, *Network and Sharing
     Center*, *Change adapter settings*, right-click **Wi-Fi**, *Properties*, *Sharing* tab, tick *Allow other network
     users to connect through this computer's Internet connection* and choose the Ethernet adapter. The board then
     gets an address 192.168.137.x.
3. Monitor (HDMI or DisplayPort) and USB keyboard, **or** the micro-USB cable from the board's micro-USB port
   (USB-UART) to the PC.

**B3. Power on.** Plug in the 12 V adapter. Fans and LEDs come on. The first boot takes a few minutes.
* With a monitor: wait for the Ubuntu login screen.
* With the serial cable: Windows shows new COM ports in *Device Manager*, *Ports (COM & LPT)*. Open PuTTY,
  *Serial*, one of the new COM ports, speed **115200**, *Open*, press Enter. If nothing appears, close it and try
  the next COM port.

**B4. First login.** User **`ubuntu`**, password **`ubuntu`**. Ubuntu asks you to change the password right away:
type the old one (`ubuntu`) and then a new one twice. Remember it.

**B5. Find the board's IP address.** In a terminal on the board (with a monitor: right-click the desktop, *Open
Terminal*), type:
```
hostname -I
```
Note the first address, for example `192.168.1.57` or `192.168.137.23`. The guide calls it `<board-ip>`.
From now on you can work from the PC: open **PowerShell** on the PC and type `ssh ubuntu@<board-ip>` (answer
`yes` the first time, then your new password). The board's terminal is now in the PowerShell window.

**B6. Check the internet on the board.**
```
ping -c 3 github.com
```
You must see 3 replies. If not, see Troubleshooting (internet).

**B7. Install PYNQ** (about 30-60 minutes; the board must stay powered and online):
```
git clone https://github.com/Xilinx/Kria-PYNQ.git
cd Kria-PYNQ/
sudo bash install.sh -b KV260
```
It ends without an error message and the prompt comes back. Then reboot the board:
```
sudo reboot
```
After a minute, connect again from PowerShell (`ssh ubuntu@<board-ip>`).

**B8. Check PYNQ.** In the PC's browser open `http://<board-ip>:9090/lab`. The JupyterLab page must open
(password `xilinx`). You do not need it further; it only proves PYNQ works.

---

## Part C. Copy the kit to the board (5 minutes)

In **PowerShell on the PC** (not in the ssh window):
```
scp -r C:\seizelut_kv260_v6 ubuntu@<board-ip>:~/
```
This copies the whole kit, including the `board\seizelut.bit` and `.hwh` you added in A4, to
`/home/ubuntu/seizelut_kv260_v6` on the board. (Or drag the folder across with WinSCP.)

---

## Part D. Run the tests on the board (about 15-20 minutes)

In the **ssh window** (the board):
```
cd ~/seizelut_kv260_v6/board
bash run_board_tests.sh --quick
```
This is a 2-3 minute smoke test. It asks for your password once (it needs root for the FPGA). Each step prints a
line starting with `[PASS]` or `[FAIL]`, and the last line must be **`ALL TESTS PASSED`**.

Then the full campaign:
```
bash run_board_tests.sh
```
What it checks (all in the real FPGA):

| Step | Check | Must give |
|---|---|---|
| 1 | bitstream loads; the core answers with its ID and version 3 | `version=3`, `id_ok=True` |
| 2 | built-in self-test: 1,024 golden vectors at one per clock, checked in hardware | 1024/1024, 0 errors |
| 3 | latency | 3 cycles (30 ns) |
| 4 | 431,960 one-second windows of 10 recordings through the classifier | 0 mismatches |
| 5 | seizures detected and false alarms from the FPGA's own alarms | numbers (no pass/fail) |
| 6 | power of the module (INA260 sensor) | watts (no pass/fail) |
| 7 | raw samples, front end in C on the ARM, classifier in the fabric | 0 mismatches |
| 8 | all 3,592 single faults injected, self-test after each | 0 hardware/software mismatches |
| 9 | **whole detector in the fabric:** raw samples, feature engine, classifier; every window's 38 features, score, decision and alarm | 0 mismatches, engine cycles per second |

Then pack the results:
```
bash pack_results.sh
```
and copy them to the PC (in **PowerShell on the PC**):
```
scp ubuntu@<board-ip>:~/seizelut_results.zip .
```
Send me **`seizelut_results.zip`** and **`out.zip`** (from A5). I will put the measured numbers into the paper
(the red `[board ...]` marks).

---

## Part E. Live demo with the board's LEDs (no buzzer)

In the **ssh window**:
```
cd ~/seizelut_kv260_v6/demo
bash demo1_now.sh
```
It prints a line `on the laptop open: http://<board-ip>:8080`. Open that address in the laptop's browser.

What you should see:
* the top of the dashboard says **front end + classifier in FPGA · 100 MHz**, and the orange box around the
  pipeline reads **FPGA fabric · feature engine + classifier · 100 MHz · no multiplier**;
* **FPGA = software: N / N windows identical** (green): every window, the fabric's features and result are checked
  against the C front end and the software model;
* the board's LEDs (press **LED test** first to see where they are): **DS35** flashes once per window, **DS36** lights
  while the classifier says "seizure-like"; during an alarm DS35 strobes fast and DS36 stays on;
* press **Seizure** to jump close to the seizure, and watch the score rise and the alarm fire.

Stop the demo with **Ctrl+C** (the LEDs go back to Linux). The presenter script for your guide is in
`demo/DEMO.md` (ignore the buzzer parts: they are for Demo 2 with parts).

To switch the board off: `sudo poweroff`, wait 30 seconds, then unplug.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| Vivado: `couldn't read file "vivado/build_kv260.tcl"` | the `cd` path is wrong: `cd C:/seizelut_kv260_v6` (forward slashes), then `set argv {}` and `source ...` again |
| PowerShell: `source : The term 'source' is not recognized` | those lines go into Vivado's **Tcl Console**, not PowerShell |
| Vivado: `IP xilinx.com:ip:zynq_ultra_ps_e is not in this Vivado installation` | the Zynq UltraScale+ devices are not installed: run the AMD installer again, *Add devices* |
| Build ends with `WARNING timing not met` | send me `out/timing_summary.rpt` |
| Board does not reach the Ubuntu login (black screen, or the serial console stops early) | older boards need a boot-firmware update for Ubuntu 22.04: AMD Kria wiki, "Kria K26 SOM", *Boot Firmware Updates* (hold the FWUEN button while powering on, then open the recovery page over Ethernet) |
| `hostname -I` prints nothing | the Ethernet cable or the sharing is not set up; with laptop sharing, untick and tick the sharing box again and reboot the board |
| `ping github.com` fails (internet) | with a router: check the cable; with laptop sharing: see the line above; at a college network that blocks devices, use a phone hotspot with a router, or ask me |
| PYNQ install stops at `apt-key ... keyserver` | run `sudo bash install.sh -b KV260` again; if it keeps failing, tell me |
| `ssh: connect to host ... timed out` | the IP changed after a reboot: look it up again with `hostname -I` on the board |
| Tests: `ModuleNotFoundError: pynq` | PYNQ is not installed (B7) or the board was not rebooted after it |
| Tests: overlay fails to load / PL busy | `sudo xmutil unloadapp`, then run again |
| Tests: `no seizelut IP in the overlay` | `seizelut.hwh` is missing next to `seizelut.bit` in `board/`, or renamed |
| Step 9 says `skipped ... version < 3` | the bitstream is from kit v5: build kit v6 (Part A) and copy the new `.bit` and `.hwh` |
| `fast C path unavailable` | harmless: the Python path is used (slower) |
| Demo page does not open | use the address the demo printed; the laptop and the board must be on the same network; try `http://<board-ip>:8080` again after 10 seconds |
| Anything else | send me the full console text (it is also saved in `board/results/console_*.txt`) |
