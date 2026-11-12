#!/bin/bash
# SeizeLUT live demo 2: PMOD LEDs, buzzer and push button wired as in ORDER_NOW.md.
# Run ON THE KV260 (Kria-PYNQ):   sudo bash demo2_components.sh
# Needs the FPGA bitstream (board/seizelut.bit + .hwh from the Vivado build): the PMOD pins are driven by the fabric.
# If your buzzer beeps all the time and stops during the alarm, run:  sudo bash demo2_components.sh --buzzer-active-low
cd "$(dirname "$0")" || exit 1
if [ "$(id -u)" -ne 0 ]; then exec sudo -E bash "$0" "$@"; fi
[ -f /etc/profile.d/pynq_venv.sh ] && source /etc/profile.d/pynq_venv.sh
if [ ! -f ../board/seizelut.bit ] || [ ! -f ../board/seizelut.hwh ]; then
  echo "board/seizelut.bit and board/seizelut.hwh are missing: build them with Vivado (vivado/build.sh) and copy"
  echo "them into the kit's board/ folder. Without the bitstream the PMOD LEDs cannot light (use demo1_now.sh)."
  exit 1
fi
PORT=8080
echo "------------------------------------------------------------------"
echo " SeizeLUT live demo 2 (PMOD LEDs, buzzer, button)"
for ip in $(hostname -I); do echo "   on the laptop open:  http://$ip:$PORT"; done
echo " First press 'LED test' in the browser: A1 A2 A3 A4 B1 B2 B3 light in turn."
echo "------------------------------------------------------------------"
exec python3 seizelut_demo.py --demo 2 --backend fpga --port $PORT "$@"
