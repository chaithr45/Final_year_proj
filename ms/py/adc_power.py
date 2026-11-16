#!/usr/bin/env python3
"""ADC power per channel at a required SNDR, from B. Murmann's ADC Performance Survey 1997-2026 (MS_SPEC.md 1.3).

Source: data/external/ADC-survey/xls/ADCsurvey_rev20260801.xlsx (bash ms/py/fetch_adc_survey.sh: pinned commit and
SHA-256), sheets ISSCC and VLSI. All design values are the survey's own cells: SNDR_plot, P, fsnyq, FOMW_hf/FOMS_hf
(the _lf column where the _hf one is empty). Survey definitions: FOM_W = P / (fsnyq * 2^ENOB), ENOB =
(SNDR - 1.76)/6.02; FOM_S = SNDR + 10 log10(fsnyq / 2 / P).

For a required SNDR and our Nyquist rate (fs = 256 S/s for EEG/ECG/EMG, so fsnyq = 256 Hz):
  * walden:   P = best FOM_W times 2^ENOB * fsnyq;
  * schreier: P = (fsnyq/2) * 10^((SNDR - best FOM_S)/10);
    both over designs of similar resolution (required <= SNDR < required + 20 dB): a FOM does not transfer across
    tens of dB (FOM_S grows with SNDR, so the best FOM_S of a 120 dB design would flatter a 50 dB requirement);
  * low-rate floor: the smallest absolute P among designs with fsnyq <= 20 kHz and SNDR >= required. At a few
    hundred S/s static power (bias, leakage, references) dominates, so FOM scaling down to 256 Hz is optimistic;
    this column is what a real low-rate design has actually achieved, at its own (higher) rate.
The FOM rows are envelopes (best designs), not typical designs; the median is reported beside them.

Usage: python ms/py/adc_power.py [--sndr 40 50 60 70 80] [--fsnyq 256]  -> ms/results/phase1/adc_survey_power.json
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
XLSX = REPO / "data/external/ADC-survey/xls/ADCsurvey_rev20260801.xlsx"
LOWRATE_MAX_HZ = 20e3
SIMILAR_DB = 20.0        # FOM population: designs with required <= SNDR < required + 20 dB


def _num(v):
    return float(v) if isinstance(v, (int, float)) and not (isinstance(v, float) and math.isnan(v)) else None


def load() -> list[dict]:
    import openpyxl
    if not XLSX.exists():
        raise SystemExit(f"{XLSX} missing: run bash ms/py/fetch_adc_survey.sh")
    wb = openpyxl.load_workbook(XLSX, read_only=True, data_only=True)
    out = []
    for sheet in ("ISSCC", "VLSI"):
        it = wb[sheet].iter_rows(values_only=True)
        hdr = list(next(it))
        for r in it:
            d = dict(zip(hdr, r))
            p, fn, sndr = _num(d.get("P [W]")), _num(d.get("fsnyq [Hz]")), _num(d.get("SNDR_plot [dB]"))
            if p is None or fn is None or sndr is None or p <= 0 or fn <= 0:
                continue
            fw = _num(d.get("FOMW_hf [fJ/conv-step]")) or _num(d.get("FOMW_lf [fJ/conv-step]"))
            fs_ = _num(d.get("FOMS_hf [dB]")) or _num(d.get("FOMS_lf [dB]"))
            out.append({"venue": sheet, "year": d.get("YEAR"), "id": d.get("ID"), "arch": d.get("ARCHITECTURE"),
                        "title": d.get("TITLE"), "doi": d.get("DOI"), "P_W": p, "fsnyq_Hz": fn, "sndr_dB": sndr,
                        "fomw_fJ": fw, "foms_dB": fs_})
    return out


def enob(sndr: float) -> float:
    return (sndr - 1.76) / 6.02


def at_sndr(rows: list[dict], sndr: float, fsnyq: float) -> dict:
    ok = [r for r in rows if r["sndr_dB"] >= sndr]
    band = [r for r in ok if r["sndr_dB"] < sndr + SIMILAR_DB]   # similar resolution: FOMs do not transfer across
    fw = sorted(r["fomw_fJ"] for r in band if r["fomw_fJ"])       # 50 dB of SNDR (FOM_S rewards high SNDR)
    fs_ = sorted((r["foms_dB"] for r in band if r["foms_dB"]), reverse=True)
    low = sorted((r for r in ok if r["fsnyq_Hz"] <= LOWRATE_MAX_HZ), key=lambda r: r["P_W"])
    res = {"sndr_dB": sndr, "enob": enob(sndr), "fsnyq_Hz": fsnyq, "designs_meeting_sndr": len(ok),
           "designs_in_fom_band": len(band)}
    if fw:
        res["walden"] = {"best_fomw_fJ": fw[0], "median_fomw_fJ": float(np.median(fw)),
                         "P_best_W": fw[0] * 1e-15 * 2 ** enob(sndr) * fsnyq,
                         "P_median_W": float(np.median(fw)) * 1e-15 * 2 ** enob(sndr) * fsnyq}
    if fs_:
        res["schreier"] = {"best_foms_dB": fs_[0], "median_foms_dB": float(np.median(fs_)),
                           "P_best_W": fsnyq / 2 * 10 ** ((sndr - fs_[0]) / 10),
                           "P_median_W": fsnyq / 2 * 10 ** ((sndr - float(np.median(fs_))) / 10)}
    if low:
        r = low[0]
        res["lowrate_floor"] = {"P_W": r["P_W"], "design": {k: r[k] for k in ("venue", "year", "id", "arch", "title",
                                                                             "doi", "fsnyq_Hz", "sndr_dB")},
                                "designs_considered": len(low)}
    return res


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sndr", type=float, nargs="*", default=[40, 50, 60, 70, 80])
    ap.add_argument("--fsnyq", type=float, default=256.0)
    args = ap.parse_args()
    rows = load()
    res = {"source": "Murmann ADC Performance Survey 1997-2026, rev 20260801, commit 00b4b85 (ISSCC + VLSI sheets)",
           "designs": len(rows), "lowrate_max_fsnyq_Hz": LOWRATE_MAX_HZ,
           "rows": [at_sndr(rows, s, args.fsnyq) for s in args.sndr]}
    out = REPO / "ms/results/phase1/adc_survey_power.json"
    out.write_text(json.dumps(res, indent=1) + "\n")
    print(f"{len(rows)} designs; fsnyq {args.fsnyq:g} Hz")
    for r in res["rows"]:
        w, s, lo = r.get("walden", {}), r.get("schreier", {}), r.get("lowrate_floor", {})
        d = lo.get("design", {})
        print(f"SNDR {r['sndr_dB']:5.1f} dB (ENOB {r['enob']:.1f}): Walden best {w.get('P_best_W', float('nan')):.2e} W"
              f" (median {w.get('P_median_W', float('nan')):.2e}) | Schreier best {s.get('P_best_W', float('nan')):.2e} W"
              f" (median {s.get('P_median_W', float('nan')):.2e}) | low-rate floor {lo.get('P_W', float('nan')):.2e} W"
              f" [{d.get('venue')} {d.get('year')} {d.get('id')}, {d.get('fsnyq_Hz', 0):g} Hz, "
              f"{d.get('sndr_dB', 0):.1f} dB]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
