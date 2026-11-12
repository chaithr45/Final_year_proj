#!/bin/bash
# SeizeLUT live demo 1: no extra parts. Run ON THE KV260 (Kria-PYNQ):   sudo bash demo1_now.sh
# The board's own LEDs DS35 (heartbeat) and DS36 react; the laptop's browser shows everything.
# Uses the FPGA when board/seizelut.bit + .hwh exist (Vivado build), otherwise the software model of the core.
cd "$(dirname "$0")" || exit 1
if [ "$(id -u)" -ne 0 ]; then exec sudo -E bash "$0" "$@"; fi
[ -f /etc/profile.d/pynq_venv.sh ] && source /etc/profile.d/pynq_venv.sh
PORT=8080
echo "------------------------------------------------------------------"
echo " SeizeLUT live demo 1"
for ip in $(hostname -I); do echo "   on the laptop open:  http://$ip:$PORT"; done
echo " (Ctrl+C stops the demo and gives the LEDs back to Linux)"
echo "------------------------------------------------------------------"
exec python3 seizelut_demo.py --demo 1 --port $PORT "$@"
