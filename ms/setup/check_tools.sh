#!/usr/bin/env bash
# SeizeLUT-MS Phase 0: check the analog tool chain inside IIC-OSIC-TOOLS.
# Run inside the container (terminal of the VNC desktop, or start_shell):
#     cd /foss/designs/Final_year_proj && bash ms/setup/check_tools.sh
# Checks: SKY130A selected; tool versions; ngspice + SKY130 models (DC, transient, Monte Carlo);
# Magic DRC and netgen LVS (xschem netlists the schematic) on a known-good inverter.
# Writes the console output to ms/setup/results/check_tools_<date>.txt (send that file back).
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
mkdir -p "$HERE/results"
OUT="$HERE/results/check_tools_$(date +%Y%m%d-%H%M%S).txt"
exec > >(tee "$OUT") 2>&1

FAIL=0
step() { echo; echo "== $*"; }
pass() { echo "   PASS  $*"; }
fail() { echo "   FAIL  $*"; FAIL=1; }

step "1. container and PDK"
echo "   host arch: $(uname -m)   image tag: ${IIC_OSIC_TOOLS_VERSION:-unknown}"
if command -v sak-pdk-script.sh >/dev/null; then
  # shellcheck source=/dev/null
  source sak-pdk-script.sh sky130A > /dev/null 2>&1
fi
echo "   PDK=${PDK:-unset}  PDK_ROOT=${PDK_ROOT:-unset}  STD_CELL_LIBRARY=${STD_CELL_LIBRARY:-unset}"
if [ "${PDK:-}" = "sky130A" ] && [ -f "${PDK_ROOT:-/nonexistent}/sky130A/libs.tech/ngspice/sky130.lib.spice" ]; then
  pass "sky130A selected and its ngspice models exist"
else
  fail "sky130A not selected (run: sak-pdk sky130A) or its models are missing"
fi
[ -f "${PDK_ROOT:-/x}/sky130A/SOURCES" ] && sed 's/^/   /' "$PDK_ROOT/sky130A/SOURCES" | head -3

step "2. tool versions"
for t in ngspice xschem magic netgen klayout; do
  p="$(command -v $t || true)"
  [ -n "$p" ] && echo "   $t: $p" || fail "$t not found"
done
echo "   ngspice: $(ngspice --version 2>/dev/null | grep -o 'ngspice-[0-9.]*' | head -1)"
echo "   klayout: $(klayout -v 2>/dev/null | head -1)"
echo "   magic:   $(echo 'puts [version]; quit -noprompt' > /tmp/mv.tcl; magic -dnull -noconsole /tmp/mv.tcl 2>/dev/null | grep -E '^[0-9]+\.[0-9]+' | head -1)"

step "3. ngspice + SKY130 smoke test (about 30-60 s)"
if bash "$REPO/ms/analog/smoke/run_smoke.sh"; then pass "ngspice smoke test"; else fail "ngspice smoke test"; fi

step "4. Magic DRC and netgen LVS of a known-good inverter (IIC-OSIC-TOOLS test 02)"
WORK="$(mktemp -d)"
if command -v sak-drc.sh >/dev/null && command -v sak-lvs.sh >/dev/null; then
  if sak-drc.sh -w "$WORK" -b "$HERE/layver_inv/inv.mag" > "$WORK/drc.log" 2>&1; then pass "DRC (Magic)"; else fail "DRC (Magic): see $WORK/drc.log"; tail -15 "$WORK/drc.log"; fi
  if sak-lvs.sh -w "$WORK" -s "$HERE/layver_inv/inv.sch" -l "$HERE/layver_inv/inv.mag" -c inv > "$WORK/lvs.log" 2>&1; then
    pass "LVS (xschem netlist vs Magic extraction, compared by netgen)"
  else
    fail "LVS: see $WORK/lvs.log"; tail -15 "$WORK/lvs.log"
  fi
else
  fail "sak-drc.sh / sak-lvs.sh not found (are you inside IIC-OSIC-TOOLS?)"
fi

echo
if [ $FAIL -eq 0 ]; then echo "ALL TOOL CHECKS PASSED"; else echo "SOME TOOL CHECKS FAILED"; fi
echo "log: $OUT"
exit $FAIL
