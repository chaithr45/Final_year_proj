#!/bin/bash
# Direct Ethernet cable laptop <-> KV260 (no router): give the board a fixed address 192.168.50.2.
# Run ON THE KV260:  sudo bash net_direct.sh      (lasts until the next reboot; the normal DHCP setup is untouched)
# On the laptop give the Ethernet adapter 192.168.50.1 / 255.255.255.0 (see DEMO.md), then open http://192.168.50.2:8080
if [ "$(id -u)" -ne 0 ]; then exec sudo bash "$0" "$@"; fi
IF=$(ip -o link show | awk -F': ' '{print $2}' | grep -E '^(eth|en)' | head -n 1)
[ -z "$IF" ] && { echo "no Ethernet interface found (ip link)"; exit 1; }
ip link set "$IF" up
ip addr add 192.168.50.2/24 dev "$IF" 2>/dev/null || echo "(192.168.50.2 already set on $IF)"
ip -4 addr show "$IF" | grep inet
echo "Board reachable at 192.168.50.2 on $IF. Test from the laptop:  ping 192.168.50.2"
