# SeizeLUT: test everything, step by step

This zip is the complete project for the board: the kit v6 hardware and software, the bitstream you built with
Vivado 2026.1 (already in `board/`, no rebuild needed), the board-run fix, the live demo with LEDs and buzzer, and
the doctor alert on the ESP32. Do the parts in order; each one says what you must see.

| Part | What | Needs | Time |
|---|---|---|---|
| 1 | Test on the laptop (no board) | WSL | 5 min |
| 2 | Copy the kit to the board | USB pen drive | 5 min |
| 3 | Board tests (all 9 steps) | board | 20 min |
| 4 | Demo: red LED and buzzer | board, breadboard | 5 min |
| 5 | Program the ESP32 | PC, Arduino IDE, iPhone | 20 min |
| 6 | Doctor alert on the iPhone | everything | 10 min |

---

## Part 1. Test on the laptop (no board)

1. Unzip `SeizeLUT_KV260_complete.zip` to `C:\` (you get `C:\seizelut_kv260_v6`). If an older
   `C:\seizelut_kv260_v6` exists, delete or rename it first.
2. PowerShell:
   ```
   wsl -d Ubuntu-24.04
   ```
   ```
   conda activate seizelut
   ```
   ```
   cd /mnt/c/seizelut_kv260_v6/board && python3 run_tests.py --backend emu --quick
   ```
   **Must see:** `[PASS]` for steps 1 to 9 and `ALL TESTS PASSED`.
3. Optional, the dashboard: `cd ../demo && bash rehearse_laptop.sh`, open `http://localhost:8080`, Ctrl+C to stop.

## Part 2. Copy the kit to the board (USB pen drive)

1. Copy `C:\seizelut_kv260_v6` to the pen drive. Plug the drive into the board.
2. On the board:
   ```
   lsblk
   ```
   (the drive is usually `sda1`)
   ```
   sudo mount /dev/sda1 /mnt
   ```
   ```
   rm -rf ~/seizelut_kv260_v6_old && mv ~/seizelut_kv260_v6 ~/seizelut_kv260_v6_old
   ```
   ```
   cp -r /mnt/seizelut_kv260_v6 ~/ && sudo umount /mnt
   ```
   The old folder (with your earlier results) is kept as `~/seizelut_kv260_v6_old`.

## Part 3. Board tests

```
cd ~/seizelut_kv260_v6/board && bash run_board_tests.sh --quick
```
**Must see:** `ALL TESTS PASSED`. Then the full campaign:
```
bash run_board_tests.sh
```
**Must see** (as in your first run): step 1 `version=3`; step 2 `ok=1024, errors=0`; step 4 `windows=431960,
mismatches_vs_golden=0`; step 8 `faults_injected=3592, hw_sw_mismatches=0`; step 9 `feature mismatches 0, output
mismatches 0+0` on all 3 recordings; `ALL TESTS PASSED`.

## Part 4. Demo: red LED and buzzer (board switched off while wiring)

| PMOD pin | Breadboard |
|---|---|
| B1 | 220 ohm -> red LED long leg; LED short leg -> GND rail |
| B2 | 1 kohm -> BC547 middle leg (B); right leg (E) -> GND rail; left leg (C) -> buzzer (-) |
| 3.3 V | buzzer (+) (do not forget this one) |
| GND | GND rail |

(BC547 flat face towards you, legs down: C, B, E from left to right. Pin 1 of the PMOD is A1; the two power pins
are at the other end of each row.)

Power on, then:
```
cd ~/seizelut_kv260_v6/demo && bash demo2_components.sh --autoplay --speed 4
```
**Must see:** the start-up text says `front end (feature engine) and classifier both in the fabric`; about half a
minute later the red LED turns on and the buzzer beeps. Ctrl+C stops.

## Part 5. Program the ESP32 (once, on the PC)

**iPhone:**
1. Settings > General > About > Name: a simple name without an apostrophe, for example `SaiPhone`.
2. Settings > Personal Hotspot: Allow Others to Join on, note the password, **Maximize Compatibility** on.
3. App Store: install **ntfy**; open it, tap **+**, subscribe to a long secret topic, for example
   `seizelut-sai-7c3f9a`; allow notifications.

**Arduino IDE** (arduino.cc/en/software):
1. File > Preferences > Additional boards manager URLs:
   `https://espressif.github.io/arduino-esp32/package_esp32_index.json`
2. Tools > Board > Boards Manager: install **esp32 by Espressif Systems**.
3. Open `C:\seizelut_kv260_v6\esp32\seizelut_alert\seizelut_alert.ino`. Edit the lines at the top:
   `WIFI_SSID` (phone name), `WIFI_PASS` (hotspot password), `NTFY_TOPIC` (your topic), `BED`, `CALL_NUMBER`
   (nurse station or emergency number), `PLAN` (the patient's emergency plan, from the treating doctor).
4. Plug the ESP32 into the PC. Tools > Board > esp32 > **ESP32 Dev Module**; Tools > Port: the new COM port.
   Upload. If it hangs at `Connecting...`, hold the ESP32's **BOOT** button until it starts writing.
5. With the iPhone's Personal Hotspot screen open, Tools > Serial Monitor (115200): it prints
   `SeizeLUT alert ready, page: http://172.20.10.x`. Write that address down.

If the Arduino IDE shows a compile error, send me the red text.

## Part 6. Doctor alert on the iPhone

**Wiring** (board off), in addition to Part 4:

| From | To |
|---|---|
| PMOD B1 (same pin as the red LED) | ESP32 GPIO 27 |
| PMOD B3 (optional) | ESP32 GPIO 26 |
| PMOD GND | ESP32 GND |
| KV260 USB port | ESP32 USB (cable) |

Do **not** connect PMOD 3.3 V to the ESP32.

1. Power on the board, keep the iPhone hotspot on. On the board:
   ```
   ls /dev/ttyUSB* /dev/ttyACM*
   ```
   **Must see** one name, for example `/dev/ttyUSB0`.
2. Test alarm (made-up data, marked TEST):
   ```
   cd ~/seizelut_kv260_v6/demo && sudo bash -c 'source /etc/profile.d/pynq_venv.sh && python3 doctor_alert.py --bed "Bed 1"'
   ```
   **Must see** on the iPhone: "TEST SEIZURE Bed 1" with "GO TO BED 1 NOW: PROTECT FROM INJURY". Tap the
   notification's **On my way** button: the board prints `ACK received`. After 15 s "TEST EMERGENCY ... over 5 min",
   then "TEST seizure stopped".
3. Live page: on the iPhone, Safari, `http://172.20.10.x` (Part 5.5). Tap "Tap once to enable the alarm sound".
4. The real demo with everything:
   ```
   bash demo2_components.sh --autoplay --speed 4 --bed "Bed 1"
   ```
   **Must see:** the start-up text says `doctor notification: ESP32 on /dev/ttyUSB0`; at the alarm the red LED and
   buzzer turn on, the iPhone rings with "SEIZURE Bed 1", the page turns red with the instruction and the four
   tiles; about 30 s after the alarm stops: "Seizure stopped".

## What to send me

* Part 3: `bash pack_results.sh` and the `seizelut_results.zip` (only if something differs from your first run).
* Part 6: a screenshot of the iPhone notification and of the page; a photo or video of the LED and buzzer.
* Any `FAIL`, error message or Arduino compile error: the full text.

## If something goes wrong

| Symptom | Fix |
|---|---|
| `No module named 'numpy'` in WSL | `conda activate seizelut`, or `pip install numpy` |
| `soft reset not visible` on the board | you are running the old kit: redo Part 2 |
| Red LED always on, buzzer silent | the wires are on the wrong end of the PMOD connector: B1 is at the opposite end from 3.3 V and GND |
| Buzzer silent, LED fine | buzzer (+) not on 3.3 V, or the BC547 legs swapped |
| ESP32 does not join the hotspot | Maximize Compatibility on, phone name without an apostrophe and equal to `WIFI_SSID`, hotspot screen open |
| No `/dev/ttyUSB*` on the board | another USB cable (some only charge) or another USB port |
| Notification without details ("FPGA signal") | the ESP32 saw the alarm wire but no message over USB: check the USB cable to the board |
| Page not reachable | use the exact address from the Serial Monitor; phone and ESP32 on the same hotspot |
