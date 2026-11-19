# Doctor alert with an ESP32: step by step

When the KV260 raises a seizure alarm (red LED and buzzer), the ESP32 on the same breadboard sends a push
notification to the doctor's iPhone and shows a live alarm page with five measured details:

| # | Detail | Measured from |
|---|---|---|
| 1 | Heart rate before the alarm and now (for example "72 -> 118 bpm (+64 %), fast") | ECG |
| 2 | Movement compared with before ("strong movement (x4.8 vs before)") | chest accelerometer |
| 3 | Muscle activity compared with before | EMG |
| 4 | Brain signal change, and whether slow or fast waves rose | the two EEG channels |
| 5 | Pattern hint: "motor pattern likely" when movement rose 2.6-fold or more, else "little movement" | movement |

The notification also shows the alarm duration, how many of the 25 "seizure" lookup tables voted, whether the
patient pressed the button, and which sensors are worn. An "alarm ended" message follows when the alarm has been
quiet for 30 s.

**What the pattern hint is worth:** on the training patients the 2.6-fold threshold was chosen on patients 1-48 and
then agreed with the doctors' motor / non-motor labels in 64 % of cases (balanced accuracy) on patients 49-96
(`results/tables/alert_signs.json`). It is a hint for the doctor, not a seizure type. All values are measurements,
not a diagnosis.

## 1. Parts and wiring (board switched off)

| From | To | Why |
|---|---|---|
| KV260 PMOD **B1** (the same pin as the red LED) | ESP32 **GPIO 27** | the FPGA's alarm signal, a backup that works without the board software |
| KV260 PMOD **B3** (optional) | ESP32 **GPIO 26** | heartbeat: shows the FPGA is running |
| KV260 PMOD **GND** | ESP32 **GND** | shared ground (required) |
| KV260 **USB port** | ESP32 **USB** (cable) | power for the ESP32 and the detail messages |

**Do not connect PMOD 3.3 V to the ESP32's 3V3 pin**: the ESP32 is powered by the USB cable. The red LED and the
buzzer stay as they are; GPIO 27 is simply a second wire from B1.

## 2. Prepare the iPhone (once)

1. Give the phone a simple name, without an apostrophe: **Settings > General > About > Name**, for example
   `SaiPhone`. The hotspot uses this name.
2. **Settings > Personal Hotspot**: turn on **Allow Others to Join**, note the **Wi-Fi Password**, and turn on
   **Maximize Compatibility**. The ESP32 only uses 2.4 GHz Wi-Fi, which this switch provides.
3. Install **ntfy** from the App Store. Open it, tap **+**, and subscribe to a topic: a long random name only you
   know, for example `seizelut-sai-7c3f9a`. Allow notifications when iOS asks. Anyone who knows the topic name can
   read the messages, so keep it secret and never put patient names in them (the kit only sends a bed name).

## 3. Program the ESP32 (once, on the PC)

1. Install the **Arduino IDE** (arduino.cc/en/software).
2. **File > Preferences > Additional boards manager URLs**: add
   `https://espressif.github.io/arduino-esp32/package_esp32_index.json`. Then **Tools > Board > Boards Manager**,
   search **esp32**, install **esp32 by Espressif Systems**.
3. Open `esp32/seizelut_alert/seizelut_alert.ino` from the kit. At the top, set:
   * `WIFI_SSID` = your phone's name from step 2.1 (exactly)
   * `WIFI_PASS` = the hotspot password
   * `NTFY_TOPIC` = the topic from step 2.3 (exactly)
   * `BED` = for example `"Bed 1"`
4. Plug the ESP32 into the PC. **Tools > Board > esp32 > ESP32 Dev Module**, **Tools > Port** = the new COM port.
   Click **Upload** (arrow). If it waits at `Connecting....`, hold the ESP32's **BOOT** button until it starts.
5. Check: keep the iPhone's Personal Hotspot screen open; within a few seconds the iPhone shows one connected device.
   **Tools > Serial Monitor** (115200 baud) prints `SeizeLUT alert ready, page: http://172.20.10.x`. Note that
   address.

## 4. Run it with the board

1. Plug the ESP32's USB cable into a **USB port of the KV260** (not the PC), with the wires from step 1.
2. On the board, check that it sees the ESP32:
   ```
   ls /dev/ttyUSB* /dev/ttyACM*
   ```
   One name must appear (for example `/dev/ttyUSB0`).
3. Send a test alarm (no patient data, clearly marked TEST):
   ```
   cd ~/seizelut_kv260_v6/demo && sudo bash -c 'source /etc/profile.d/pynq_venv.sh && python3 doctor_alert.py --bed "Bed 1"'
   ```
   The iPhone rings with "TEST seizure alarm - Bed 1", and 20 s later "TEST alarm ended".
4. Run the demo as before; it finds the ESP32 by itself (the start-up text says `doctor notification: ESP32 on
   /dev/ttyUSB0`):
   ```
   bash demo2_components.sh --autoplay --speed 4 --bed "Bed 1"
   ```
   When the alarm fires, the red LED and buzzer turn on and the iPhone gets the notification with the five
   details. Updates follow on the page every 15 s (on the phone at most once a minute), then "Alarm ended".
5. Live page: on the iPhone open Safari at `http://172.20.10.x` (the address from step 3.5). Tap **"Tap once to
   enable the alarm sound"**. The page turns red during an alarm and shows all details and an event list.

## Troubleshooting

| Symptom | Fix |
|---|---|
| ESP32 never joins the hotspot | Maximize Compatibility on; the phone name has no apostrophe and matches `WIFI_SSID` exactly; keep the Personal Hotspot screen open while the ESP32 starts |
| No notification, page works | the topic in ntfy and `NTFY_TOPIC` differ, or the hotspot has no mobile data; the page shows `last push: error ...` |
| `ls /dev/ttyUSB*` shows nothing on the board | try another USB cable (some are charge-only) or another USB port |
| Demo says `doctor notification: off` | the ESP32 is not plugged into the board, or run the demo with `--esp32 /dev/ttyUSB0` |
| Notification "SEIZURE ALARM (FPGA signal)" without details | the FPGA's alarm wire (B1) was on for 4 s but no message came over USB: check the USB cable; the backup did its job |
| Phone page not reachable | use the address the Serial Monitor printed; the phone and the ESP32 must be on the same hotspot |

Security note: for simplicity the ESP32 does not check ntfy's HTTPS certificate (`setInsecure()`); for real use,
add the certificate or use a private ntfy server.
