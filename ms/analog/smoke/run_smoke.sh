#!/usr/bin/env bash
# SeizeLUT-MS Phase 0: SKY130 + ngspice smoke test.
#   Inside IIC-OSIC-TOOLS:  bash ms/analog/smoke/run_smoke.sh
#   Elsewhere:              PDK_ROOT=/path/to/pdks bash ms/analog/smoke/run_smoke.sh
# Runs smoke_nominal.spice (tt corner) and smoke_mc.spice (tt_mm, 40 mismatch samples), compares the
# numbers with expected.json and ends with "SMOKE TEST PASSED" or "SMOKE TEST FAILED".
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
PDK="${PDK:-sky130A}"
: "${PDK_ROOT:?PDK_ROOT is not set (inside IIC-OSIC-TOOLS it is set automatically)}"
NGS="$PDK_ROOT/$PDK/libs.tech/ngspice"
[ -f "$NGS/sky130.lib.spice" ] || { echo "missing $NGS/sky130.lib.spice (is $PDK installed? try: sak-pdk sky130A)"; exit 1; }
command -v ngspice >/dev/null || { echo "ngspice not found"; exit 1; }

RUN="$(mktemp -d)"
trap 'rm -rf "$RUN"' EXIT
cp "$NGS/spinit" "$RUN/.spiceinit"          # the PDK's recommended ngspice settings
run() {  # run <netlist> <corner>
  { echo "* wrapper"; echo ".lib $NGS/sky130.lib.spice $2"; cat "$HERE/$1"; } > "$RUN/$1"
  ( cd "$RUN" && ngspice -b "$1" > "$1.log" 2>&1 ) || { tail -30 "$RUN/$1.log"; echo "SMOKE TEST FAILED (ngspice error in $1)"; exit 1; }
  cat "$RUN/$1.log" >> "$RUN/all.log"
}
START=$(date +%s)
run smoke_nominal.spice tt
run smoke_mc.spice tt_mm
echo "ngspice: $(ngspice --version 2>/dev/null | grep -o 'ngspice-[0-9.]*' | head -1)   PDK: $PDK_ROOT/$PDK   ($(( $(date +%s) - START )) s)"
python3 - "$RUN/all.log" "$HERE/expected.json" <<'PY'
import json, statistics, sys
got, mc = {}, []
for line in open(sys.argv[1]):
    p = line.split()
    if len(p) == 3 and p[0] == "RESULT":
        got[p[1]] = float(p[2])
    elif len(p) == 3 and p[0] == "MC":
        mc.append(float(p[2]))
if mc:
    got["mc_samples"] = len(mc)
    got["mc_dvgs_mean_mV"] = statistics.fmean(mc)
    got["mc_dvgs_std_mV"] = statistics.stdev(mc)
exp = json.load(open(sys.argv[2]))
ok = True
for name, e in exp["checks"].items():
    if name not in got:
        print(f"  {name:24s} MISSING"); ok = False; continue
    v, lo, hi = got[name], e["min"], e["max"]
    good = lo <= v <= hi
    ok &= good
    print(f"  {name:24s} {v:10.4g}   expected {lo:g} .. {hi:g} {e.get('unit', '')}   {'ok' if good else 'OUT OF RANGE'}")
print("SMOKE TEST PASSED" if ok else "SMOKE TEST FAILED")
sys.exit(0 if ok else 1)
PY
