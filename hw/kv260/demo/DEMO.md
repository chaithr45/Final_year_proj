# SeizeLUT live demo

A recorded patient's signals stream second by second into the KV260. The ARM processor filters them with the
integer front end (C code), the FPGA classifier decides "seizure or not" for every 2-second window, and the board's
LEDs (and, in Demo 2, a buzzer) react. Your laptop's browser shows every stage live: raw and filtered signals, the
38 features, the 146 comparator bits, the 50 LUTs voting, the score crossing the threshold, the 10-of-10 alarm rule,
and a running check that the FPGA's answer equals the software model's, bit for bit.

There are two versions:

| | What you need | What reacts on the board |
|---|---|---|
| **Demo 1 (today)** | the KV260 and an Ethernet cable | the board's own LEDs **DS35** (heartbeat) and **DS36** (decision / alarm); the laptop beeps on an alarm |
| **Demo 2 (after the parts arrive)** | the parts in `ORDER_NOW.md`, wired to the PMOD connector | 7 PMOD LEDs (score bar, decision, ALARM, heartbeat), a buzzer and a push button, driven directly by the FPGA fabric |

You can rehearse either one on the laptop alone (no board); the dashboard then says "software model (no FPGA)".

---

## 0. Rehearse on the laptop first (5 minutes, no board)

In **WSL Ubuntu** (the same place you run the laptop jobs):

```bash
cd /mnt/c/Users/<you>/Downloads/seizelut_kv260_v4/demo
```

```bash
conda activate seizelut
```

```bash
bash rehearse_laptop.sh
```

Then open **http://localhost:8080** in Chrome or Edge on Windows. `bash rehearse_laptop.sh 2` shows the Demo 2
board drawing. Without WSL: double-click `rehearse_laptop.bat` (needs Python with numpy on Windows).

Nothing needs compiling: the front end library is included for Windows, Linux x86-64 and the board's ARM (it is
compiled fresh when gcc is present).

---

## 1. Demo 1 on the KV260 (today, no extra parts)

### 1.1 Connect the laptop and the board

**Easiest: both on the same router.** Plug the board's Ethernet into your Wi-Fi router; the laptop stays on Wi-Fi.
The board gets an address by DHCP. To find it, run `hostname -I` in a terminal on the board (Jupyter at
`http://<board>:9090` → New → Terminal, or the USB serial console). `demo1_now.sh` also prints it.

**No router (for example in the lab): direct cable.** See section 4.

### 1.2 Copy the kit to the board

From WSL on the laptop (the board's user is `ubuntu`):

```bash
scp SeizeLUT_KV260_kit_v4.zip ubuntu@<board-ip>:~
```

On the board:

```bash
python3 -m zipfile -e SeizeLUT_KV260_kit_v4.zip ~
```

(Or upload the zip in Jupyter and unpack it the same way in a Jupyter terminal.)

### 1.3 Start it

On the board:

```bash
cd ~/seizelut_kv260_v4/demo && sudo bash demo1_now.sh
```

It prints `on the laptop open: http://<board-ip>:8080`. Open that on the laptop. Then:

1. Press **LED test** (or the `L` key): the board's DS35 and DS36 light one after the other, so you know where to
   look. DS35 is the LED that normally blinks a double "heartbeat" while Linux runs.
2. Press **Play**. DS35 now flashes once per window the classifier processes, DS36 lights while the classifier
   says "seizure-like", and during an alarm DS35 strobes fast and DS36 stays on.
3. `Ctrl+C` on the board stops the demo and gives both LEDs back to Linux.

Optional: `sudo bash demo1_now.sh --board-button` turns the board's **FWUEN** push button into the patient button.
Press it alone; **never together with RESET** (that combination starts the firmware recovery tool).

### 1.4 FPGA or software?

The **Classifier** chip at the top of the dashboard says which one runs:

* **software model (no FPGA)**: there is no bitstream on the board yet, so the classifier's software model runs on
  the ARM instead. Everything else is the same.
* **FPGA core · 100 MHz**: the classifier runs in the fabric. To get there, build the bitstream with Vivado
  (`../README.md`, part A), copy `out/seizelut.bit` and `out/seizelut.hwh` into the kit's `board/` folder and start
  `demo1_now.sh` again. The **FPGA = software** chip then counts the windows where the FPGA's score, decision, alarm,
  146 comparator bits and 50 LUT outputs are identical to the software model's (it should read N / N).

---

## 2. Demo 2 (after the parts arrive)

1. Wire the breadboard as in `ORDER_NOW.md` **with the board powered off**.
2. Power on, then on the board:

   ```bash
   cd ~/seizelut_kv260_v4/demo && sudo bash demo2_components.sh
   ```

   Demo 2 needs the bitstream (`board/seizelut.bit` + `.hwh`), because the fabric drives the PMOD pins directly.
3. Press **LED test**: A1, A2, A3, A4, B1, B2 (buzzer chirps), B3 light in turn, then all LEDs together. An LED that
   stays dark is usually the wrong way round (long leg towards the resistor and the FPGA pin).
4. The **push button** (B4) is the patient button: pressing it marks the moment on the timeline and starts
   playback if it was paused.
5. If the buzzer sounds all the time and goes quiet during the alarm, it is an active-low module: restart with
   `sudo bash demo2_components.sh --buzzer-active-low`. `--no-buzzer` silences it.

What the PMOD LEDs mean (driven by the FPGA itself, not by software):

| LED | Meaning |
|---|---|
| A1, A2, A3 (green, green, yellow) | score bar: the score is within 9, 6, 3 of the threshold |
| A4 (orange) | decision: this window looks like a seizure |
| B1 (red) | **ALARM**: 10 of the last 10 windows said seizure |
| B2 (buzzer) | beeps about 3 times a second during the alarm |
| B3 (blue/white) | heartbeat: toggles every time the FPGA finishes a window |

---

## 3. Script for showing it to ma'am (about 6 minutes)

1. **Choose input** (`I`). "These are real recordings from the SeizeIT2 wearable dataset, from patients the model
   never saw during training: two EEG electrodes behind the ear, ECG, EMG and motion."
2. Pick **Patient 1: seizure, all sensors**. The calibration screen streams the 10 minutes before the shown part
   through the whole chain, so the filters and the patient's baseline settle.
3. Press **Play** at **5×** (or real time if there is time). Point at:
   * the **data path** across the top: packets move from the sensors to the ARM front end and into the FPGA every
     second;
   * **Sensors**: grey is the raw signal, colour is the front end's integer filter output; white dots on the ECG are
     the R-peaks it detects, and the heart rate is next to it;
   * **Inside the FPGA**: each bar is a feature, each tick a comparator (a bright tick is a 1); the 50 LUTs vote
     red (seizure) or blue (background); score = red minus blue.
4. At 1:30 the pink band starts: the neurologist's seizure annotation (the detector never sees it). Watch the
   heart rate rise, the EMG burst, the LUT grid turn red, the score pass the threshold and the last-10 boxes fill.
   About 16 s after the onset: **SEIZURE ALARM**, the board LEDs strobe, the laptop beeps.
5. Let ma'am try it: **Choose input → Patient 2: seizure, needs the sensitive setting**. At **Strict** it stays
   silent; she switches **Operating point → Sensitive** (the threshold register in the FPGA changes at once) and
   presses **↺** to play it again: the alarm comes 12 s after the onset. "Lower threshold, more seizures caught,
   more false alarms: the trade-off every detector has."
6. **Patient 2: normal activity, moving**: no alarm, although the patient moves. Ma'am can press the **Patient
   button** (or the real button in Demo 2) to mark a moment.
7. **Patient 2: seizure, EEG only**: only the ear EEG was recorded; the missing sensors are handled by the
   missing-sensor rule, and the Sensitive setting still detects it.
8. Finish on the numbers: **core latency 3 clock cycles = 30 ns** at 100 MHz, the **FPGA = software N / N** check
   (bit-exact), and the round trip ARM → FPGA → ARM.

Keys: `space` play/pause, `1`-`5` speed (1×, 2×, 5×, 10×, 30×), `S` skip to 30 s before the seizure, `B` patient
button, `L` LED test, `I` choose input.

### What each recording shows (computed beforehand with the same code; the watched part starts 1:30 before the onset)

| Recording | Strict (frozen in the chip) | Balanced | Sensitive |
|---|---|---|---|
| Patient 1: seizure, all sensors (sub-098, 108 s seizure) | alarm 16 s after onset | 12 s | 10 s |
| Patient 2: seizure, needs the sensitive setting (sub-099, 137 s) | no alarm | 61 s | 12 s |
| Patient 2: seizure, EEG only (sub-099, 78 s) | no alarm | no alarm | 27 s |
| Patient 3: long seizure (sub-100, 172 s) | no alarm | no alarm | 60 s |
| Patient 2: normal activity, moving (6.5 min) | no alarm | no alarm | no alarm |

These come from the streaming front end run from each segment's first sample, followed by the software model, which
is the same thing the demo runs. In every case they match the full-recording results at the same windows. The
recordings are from held-out test patients whose results are already in the report. The strict setting has the
highest threshold of the three, so it raises the fewest false alarms and misses more seizures (three of these four);
that is why the operating point can be switched live.

---

## 4. Direct cable laptop ↔ board (no router)

1. **Board:** while the board is still reachable (on the router, or through the USB serial console), run

   ```bash
   cd ~/seizelut_kv260_v4/demo && sudo bash net_direct.sh
   ```

   It adds the fixed address **192.168.50.2** to the board's Ethernet port. It lasts until the next reboot and
   leaves the normal (DHCP) setup alone.
2. **Laptop (Windows):** Settings → Network & internet → Ethernet (your USB adapter if you use one) → IP assignment
   → Edit → Manual → IPv4 on → IP address **192.168.50.1**, subnet mask **255.255.255.0** (prefix 24), no gateway →
   Save. Or in an administrator command prompt (check the adapter's name with `netsh interface show interface`):

   ```bash
   netsh interface ipv4 set address name="Ethernet" static 192.168.50.1 255.255.255.0
   ```

3. Plug the cable between the laptop and the board, check with `ping 192.168.50.2`, start the demo and open
   **http://192.168.50.2:8080**.

Your laptop's Wi-Fi keeps working for the internet at the same time.

---

## 5. What is real, and what is replayed

* **Replayed:** the sensor signals. They are recorded samples (int16, exactly what the front end would receive),
  sent one second at a time as a wearable would send them. The **seizure band** is the neurologist's annotation,
  shown only for comparison.
* **Live:** everything after that. The integer front end runs on the board's ARM; it is bit-exact with the golden
  model (431,960 of 431,960 windows checked, `../results/frontend_stream_verification.json`). The classifier runs in
  the FPGA (or its software model, as the dashboard states). Every window is written to the core over AXI, and the
  result, the comparator bits and the LUT outputs are read back from the core's registers. The PMOD LEDs in Demo 2
  are driven by the fabric itself.
* **Calibration screen:** real processing of the 10 minutes before the shown part, paced at about 200× real time.

---

## 6. Troubleshooting

| Problem | Fix |
|---|---|
| The page does not open | Laptop and board on the same network? `ping <board-ip>`. Port 8080 taken: add `--port 8081` to the command and open that port |
| Classifier says "software model" on the board | No `board/seizelut.bit` + `.hwh` yet (section 1.4), or PYNQ missing: the scripts load `/etc/profile.d/pynq_venv.sh`; check that Kria-PYNQ is installed |
| `overlay fails to load` / PL busy | `sudo xmutil unloadapp`, then start again |
| `this bitstream has no demo registers` | The bitstream is from kit v3 or older: rebuild with this kit's `vivado/build.sh` |
| Board LEDs do not react | Run with `sudo`. The startup line says which LEDs it took (`board LEDs: heartbeat, vbus_det`). If your image names them differently, `ls /sys/class/leds` and pass `--leds <name1> <name2>` |
| No sound on the laptop | Click once anywhere on the page (browsers block sound until then) and check the 🔊 button |
| PMOD LED stays dark in the LED test | Turn the LED round; check the resistor and the GND wire |
| Buzzer inverted | `--buzzer-active-low` |
| Dashboard says "Reconnecting to the board" | The demo stopped or the cable is out; start it again, and the page reconnects by itself |
| Text too small on the projector | Browser zoom (`Ctrl` `+`); the layout adapts from 1280×720 upward |
