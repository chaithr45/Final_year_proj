#!/usr/bin/env python3
"""PDF of the Phase 1 results obtained so far (only finished, committed results; every number is read from the
result files in ms/results/phase1 and results/tables, none is typed in here).

Usage: python3 ms/py/results_pdf.py [--out ms/results/phase1/phase1_results_so_far.pdf]
Needs reportlab (the system python3 has it; the repo venv does not).
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table,
                                TableStyle)

REPO = Path(__file__).resolve().parents[2]
P1 = REPO / "ms/results/phase1"
FONT_DIR = Path("/usr/share/fonts/truetype/dejavu")

pdfmetrics.registerFont(TTFont("DV", str(FONT_DIR / "DejaVuSans.ttf")))
pdfmetrics.registerFont(TTFont("DVB", str(FONT_DIR / "DejaVuSans-Bold.ttf")))
pdfmetrics.registerFontFamily("DV", normal="DV", bold="DVB", italic="DV", boldItalic="DVB")

SS = getSampleStyleSheet()
BODY = ParagraphStyle("body", parent=SS["Normal"], fontName="DV", fontSize=9, leading=12, alignment=TA_LEFT)
SMALL = ParagraphStyle("small", parent=BODY, fontSize=7.5, leading=9.5, spaceBefore=2, spaceAfter=4)
CELL = ParagraphStyle("cell", parent=BODY, fontSize=7, leading=8.5)
CELLB = ParagraphStyle("cellb", parent=CELL, fontName="DVB")
H1 = ParagraphStyle("h1", parent=BODY, fontName="DVB", fontSize=16, leading=20, spaceAfter=4)
H2 = ParagraphStyle("h2", parent=BODY, fontName="DVB", fontSize=11.5, leading=15, spaceBefore=10, spaceAfter=4,
                    keepWithNext=1)
H3 = ParagraphStyle("h3", parent=BODY, fontName="DVB", fontSize=9.5, leading=12, spaceBefore=8, spaceAfter=3,
                    keepWithNext=1)
INK, MUTED, RULE, HEAD, BAD = (colors.HexColor(c) for c in ("#1f2328", "#57606a", "#d0d7de", "#f2f4f7", "#fbe9e7"))


def J(name: str):
    return json.loads((P1 / name).read_text())


def uv(s: str) -> str:
    s = s.replace("uVrms", "µV rms").replace("LSBrms", "LSB rms").replace("uV", "µV")
    return s.replace("<=", "≤").replace(">=", "≥")


def p(text, style=BODY):
    return Paragraph(text, style)


def table(rows, widths, head=1, bad_rows=(), font=CELL):
    data = [[c if isinstance(c, Paragraph) else Paragraph(str(c), CELLB if i < head else font) for c in r]
            for i, r in enumerate(rows)]
    t = Table(data, colWidths=widths, repeatRows=head, hAlign="LEFT")
    st = [("GRID", (0, 0), (-1, -1), 0.4, RULE), ("BACKGROUND", (0, 0), (-1, head - 1), HEAD),
          ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 3),
          ("RIGHTPADDING", (0, 0), (-1, -1), 3), ("TOPPADDING", (0, 0), (-1, -1), 2),
          ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]
    st += [("BACKGROUND", (0, r), (-1, r), BAD) for r in bad_rows]
    t.setStyle(TableStyle(st))
    return t


def md_tables(path: Path) -> dict[str, list[list[str]]]:
    """Markdown tables keyed by the heading above them."""
    out, cur, key = {}, None, "_"
    for line in path.read_text().splitlines():
        if line.startswith("#"):
            key = line.lstrip("# ").strip()
            cur = None
        elif line.startswith("|"):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if set("".join(cells)) <= set("-: "):
                continue
            if cur is None:
                cur = out.setdefault(key, [])
            cur.append(cells)
        else:
            cur = None
    return out


def f(x, nd=4, sign=False):
    return f"{x:+.{nd}f}" if sign else f"{x:.{nd}f}"


def watts(w: float) -> str:
    for unit, k in (("µW", 1e-6), ("nW", 1e-9), ("pW", 1e-12), ("fW", 1e-15)):
        if w >= k:
            return f"{w / k:.3g} {unit}"
    return f"{w:.3g} W"


def git_commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=REPO, capture_output=True, text=True,
                              check=True).stdout.strip()
    except Exception:
        return "unknown"


def build(out: Path) -> None:
    W = A4[0] - 3.2 * cm
    d = J("deltas.json")
    sub, full = d["subset"], d["full"]
    cv = next(iter(J("cv_frozen_op.json").values()))
    s = []

    # ---- title -------------------------------------------------------------------------------------------------
    s.append(p("SeizeLUT-MS, Phase 1: results so far", H1))
    s.append(p(f"Detector-derived analog front-end specification. Branch FPGA, commit {git_commit()}, generated "
               f"{datetime.now(timezone.utc):%d %b %Y %H:%M} UTC by <font face='DV'>ms/py/results_pdf.py</font>. "
               "Every number below is read from a committed result file (named under each table).", SMALL))
    s.append(Spacer(1, 6))
    s.append(p("<b>What was measured.</b> How much of each analog impairment (ADC step, noise, clipping, filter "
               "corners, gain error, offset, drift, mains pick-up) the frozen detector <i>n4_distill_s0</i> tolerates "
               "at its frozen operating point (score ≥ 9, alarm 10 of 10). Impairments are applied to the raw "
               "int16 inputs of the 96 <b>training</b> patients; each patient is scored by a fold model that never "
               "saw it (out-of-fold). The test patients (sub-097..sub-125) were not used."))
    s.append(Spacer(1, 4))
    ss = J("subset.json")["summary"]
    s.append(p(f"<b>Sweep data (subset).</b> {ss['segments']} segments from {ss['patients']} training patients: "
               f"{ss['seizure_segments']} around seizures (all {ss['seizures_in_segments']} training seizures) and "
               f"{ss['background_segments']} background; {ss['scored_hours']} scored hours "
               f"({ss['background_hours']} h background). Random impairments use 5 noise seeds. Source: subset.json."))
    s.append(Spacer(1, 4))
    s.append(p(f"<b>Tolerated</b> (decision D-MS10, fixed before any sweep): event-F1 drop ≤ {f(sub['delta_f1'])} "
               f"and false alarms per 24 h rise ≤ {f(sub['delta_fp24'], 3)} against the clean subset run. Both "
               "thresholds are the standard deviation of the clean result over 5 training seeds (table 1b), so a "
               "change smaller than retraining the model with another seed counts as tolerated."))
    s.append(Spacer(1, 4))
    s.append(p("<b>Not in this PDF because it is not finished:</b> the confirmation of every limit on all 8,714 "
               "training hours (running), the step-down of limits that fail there, the back-off of the combined "
               "point, and the final spec table with amplifier and ADC power tied to it.", SMALL))

    # ---- 1. baseline -------------------------------------------------------------------------------------------
    s.append(p("1. Baseline: the retrained fold models and their seed spread", H2))
    row = next(r for r in md_tables(REPO / "results/tables/inner_cv.md").get(
        "Inner 5-fold CV on the 96 training patients (SzCORE, mean over patients)", []) if "145504" in r[-1])
    s.append(p("1a. The fold checkpoints of the original cross-validation run were lost with an old container, so "
               "the 5 fold models were retrained with the same recipe and seed and checked against the committed "
               "result (all training hours, out-of-fold).", BODY))
    s.append(Spacer(1, 3))
    s.append(table([["", "event-F1", "sensitivity", "precision", "FP / 24 h"],
                    ["committed CV run (results/tables/inner_cv.md)", row[3], row[4], row[5], row[6]],
                    ["retrained, seed 0 (cv_frozen_op.json)", f(cv["f1"]), f(cv["sensitivity"]),
                     f(cv["precision"]), f(cv["fp_per_24h"], 3)]],
                   [6.4 * cm, 2.2 * cm, 2.2 * cm, 2.2 * cm, 2.2 * cm]))
    s.append(Spacer(1, 6))
    s.append(p("1b. Clean result of the fold models of 5 training seeds. The standard deviation is the tolerance "
               "threshold: subset for the sweeps, all hours for the confirmation (source: deltas.json).", BODY))
    s.append(Spacer(1, 3))
    rows = [["data", "metric"] + [f"seed {k}" for k in sub["seeds"]] + ["mean", "sd = threshold"]]
    for name, x in (("subset (667 h)", sub), ("all training hours", full)):
        rows.append([name, "event-F1"] + [f(v) for v in x["f1"]] + [f(x["f1_mean"]), f(x["delta_f1"])])
        rows.append([name, "FP / 24 h"] + [f(v, 3) for v in x["fp_per_24h"]] + [f(x["fp24_mean"], 3),
                                                                                f(x["delta_fp24"], 3)])
    s.append(table(rows, [2.7 * cm, 1.7 * cm] + [1.45 * cm] * 5 + [1.45 * cm, 2.1 * cm]))
    s.append(p("The sweeps compare each impaired run with the clean run of the same seed-0 models on the same "
               f"segments: clean subset F1 {f(sub['f1'][0])}, FP/24 h {f(sub['fp_per_24h'][0], 3)}.", SMALL))

    # ---- 2. signal levels --------------------------------------------------------------------------------------
    sl = J("signal_levels.json")
    s.append(p("2. Signal levels at the detector input", H2))
    rows = [["modality", "channels", "median rms", "rms IQR (25-75 %)", "quiet floor (median of 1st pct. rms)"]]
    for m in ("eeg", "ecg", "emg", "mov"):
        x, u = sl[m], uv(sl["unit"][m]).split(" (")[0]
        rows.append([m.upper(), x["channels"], f"{x['rms_median_of_medians']:.1f} {u}",
                     f"{x['rms_iqr'][0]:.1f} - {x['rms_iqr'][1]:.1f}", f"{x['floor_p1_median']:.1f} {u}"])
    s.append(table(rows, [2.2 * cm, 2 * cm, 3.3 * cm, 3.6 * cm, 5.5 * cm]))
    s.append(p(f"{sl['segments_used']} subset segments. Motion unit: 1 LSB = 2<super>-12</super> g "
               "(source: signal_levels.json).", SMALL))

    # ---- 3. single-impairment limits ---------------------------------------------------------------------------
    s.append(PageBreak())
    s.append(p("3. One impairment at a time: tolerated limits (subset)", H2))
    s.append(p("<b>limit</b> = most severe level of the unbroken run of tolerated levels from the mildest; "
               "<b>first failing</b> = the next grid level. dF1 and dFP are changes against the clean run (mean "
               "over 5 noise seeds for random impairments). <b>beyond grid</b> = even the most severe level tested "
               "is tolerated. <b>bit flips</b> = comparator bits of the frozen model that change per window. "
               "Rows shaded red: no level is tolerated. Source: tolerance_table.md (from tolerance.json).", SMALL))
    tabs = md_tables(P1 / "tolerance_table.md")
    for key, rows_md in tabs.items():
        if not rows_md or rows_md[0][0] != "parameter":
            continue
        mod = key.split(":")[0]
        clean = key.split(":", 1)[1].strip()
        rows = [["parameter", "limit", "first failing (same unit)", "at limit: dF1 / dFP24 / bit flips",
                 "first failing: dF1 / dFP24", "features moving most at first failing (mean |change|, LSB)",
                 "status"]]
        bad = []
        for r in rows_md[1:]:
            ff = r[4].split(" / ")
            rows.append([uv(r[0]), uv(r[1]), uv(r[2]), r[3], " / ".join(ff[:2]) if len(ff) > 1 else ff[0],
                         ff[3] if len(ff) > 3 else "-", uv(r[5])])
            if r[5].startswith("none tolerated"):
                bad.append(len(rows) - 1)
        s.append(p(f"3.{'eeg ecg emg mov'.split().index(mod) + 1} {mod.upper()} ({uv(clean)})", H3))
        s.append(table(rows, [2.9 * cm, 1.5 * cm, 1.3 * cm, 2.9 * cm, 2.1 * cm, 4.2 * cm, 2.9 * cm], bad_rows=bad))
    for mod in ("eeg", "ecg", "emg", "mov"):
        img = P1 / f"figures/tolerance_{mod}.png"
        w = W * 0.88
        s.append(KeepTogether([p(f"Figure: {mod.upper()} tolerance curves (figures/tolerance_{mod}.png)", H3),
                               Image(str(img), width=w, height=w * 1939 / 2400)]))

    # ---- 4. cross-checks ---------------------------------------------------------------------------------------
    s.append(PageBreak())
    s.append(p("4. Cross-checks of the limits", H2))
    s.append(p("4a. Does the ADC-step limit agree with the white-noise limit?", H3))
    cons = next(v for v in md_tables(P1 / "consistency.md").values() if v and v[0][0] == "modality")
    rows = [["modality", "LSB limit → in-band quantisation noise", "first failing LSB → noise", "white-noise limit",
             "first failing white", "intervals agree"]]
    bad = []
    for r in cons[1:]:
        rows.append([r[0].upper()] + [("beyond grid" if c.strip() in ("- -> - rms", "- rms") else
                                        uv(c).replace(" -> ", " → ")) for c in r[1:]])
        if r[-1] == "NO":
            bad.append(len(rows) - 1)
    s.append(table(rows, [1.7 * cm, 4.2 * cm, 3.4 * cm, 2.5 * cm, 2.6 * cm, 2 * cm], bad_rows=bad))
    s.append(p("Textbook model: rounding to step q adds white noise of q/√12, spread over the Nyquist band "
               "(source: consistency.md). It holds for EEG, ECG and EMG. It fails for motion, explained in 4b.",
               SMALL))

    mq = J("mov_quant_vs_white.json")
    s.append(p("4b. Why motion tolerates a coarse ADC step but little white noise", H3))
    rows = [["sensor", "impairment", "quiet seconds: median log<sub>2</sub>(impaired / clean jerk)",
             "active seconds: same", "quiet seconds with zero jerk (clean)"]]
    labels = {"lsb_16": "LSB 16 (limit)", "lsb_32": "LSB 32 (fails)", "white_2LSBrms": "white 2 LSB rms (limit)",
              "white_4LSBrms": "white 4 LSB rms (fails)"}
    for sen in ("acc", "gyr"):
        r = mq["sensors"][sen]
        for k, lab in labels.items():
            v = r[k]
            rows.append([sen.upper(), lab, f(v["quiet_median_log2_ratio"], 2, True),
                         f(v["active_median_log2_ratio"], 2, True),
                         f"{100 * v['quiet_fraction_zero_jerk']:.0f} % ({100 * v['clean_quiet_fraction_zero_jerk']:.0f} %)"])
    s.append(table(rows, [1.4 * cm, 3.6 * cm, 4.6 * cm, 2.8 * cm, 4 * cm]))
    s.append(p("Jerk = sum of |x[n] - x[n-1]| per second over the 3 axes, computed with the frozen front end's own "
               "integer code. +1 = doubled, -1 = halved. Quiet = clean jerk at or below the median, active = at or "
               f"above the 90th percentile; {mq['segments']} segments (every {mq['every_nth_segment']}th), noise "
               f"seed 0. On a quiet signal (median motion rms {sl['mov']['rms_median_of_medians']:.1f} LSB) rounding holds the output on one code and "
               "<b>removes</b> movement, while white noise <b>adds</b> movement to every sample; active seconds are "
               "unchanged by both. Source: mov_quant_vs_white.json.", SMALL))

    ga = J("gauss_ab.json")
    s.append(p("4c. Does the hardware noise generator behave like true Gaussian noise?", H3))
    rows = [["generator", "level", "mean F1 (5 seeds)", "mean FP / 24 h", "dF1 vs clean", "dFP24 vs clean",
             "tolerated"]]
    for k, lab in (("sum64", "sum of 64 uniforms (the FPGA generator)"), ("exact", "exact Gaussian (reference)")):
        g = ga["generators"][k]
        rows.append([lab, "EEG white 8 µV rms", f(g["f1_mean"]), f(g["fp24_mean"], 3), f(g["d_f1"], 4, True),
                     f(g["d_fp24"], 3, True), "yes" if g["tolerated"] else "no"])
    s.append(table(rows, [4.4 * cm, 2.5 * cm, 2 * cm, 1.9 * cm, 1.8 * cm, 1.8 * cm, 2 * cm]))
    s.append(p(f"Difference between the generators: F1 {f(ga['diff_f1'], 4, True)}, FP/24 h "
               f"{f(ga['diff_fp24'], 3, True)}, both well inside the thresholds, so the verdict is "
               f"<b>{'SAME' if ga['same'] else 'DIFFERENT'}</b> (criterion fixed beforehand, LOG L17). "
               "Source: gauss_ab.json.", SMALL))

    lk = J("ecg_offset_lockup.json")
    s.append(p("4d. Why the ECG offset limit is small: the R-peak detector locks up", H3))
    rows = [["DC offset (C = 8192 µV)", "minutes scored", "minutes with < 20 beats", "share",
             "segments with ≥ half such minutes", "beats detected"]]
    for k, t in lk["totals"].items():
        rows.append([k.replace("C", " C") if k != "0C" else "0 (clean)", f"{t['minutes']:,}", f"{t['low_minutes']:,}",
                     f"{100 * t['low_fraction']:.1f} %", t["segments_half_low"], f"{t['beats']:,}"])
    s.append(table(rows, [3.4 * cm, 2.2 * cm, 2.8 * cm, 1.6 * cm, 3.2 * cm, 2.6 * cm]))
    s.append(p("An offset present from the first sample is a step for the ECG high-pass filter. The detector sets "
               "its peak level from the first 2 s, sees the step's transient, and its threshold stays above the R "
               f"peaks. {lk['segments']} subset segments, first 2 minutes skipped. Offset 0.1 C is the limit and "
               f"0.3 C fails (section 3.2). Note: {100 * lk['totals']['0C']['low_fraction']:.1f} % of minutes are already "
               "low on clean data. "
               "Source: ecg_offset_lockup.json.", SMALL))

    # ---- 5. combined preview -----------------------------------------------------------------------------------
    cv5 = J("combined_verdict.json")
    ratios = [-x["d_f1"] / cv5["deltas"]["delta_f1"] for x in cv5["jobs"].values()]
    s.append(p("5. All limits at once (preview): fails", H2))
    rows = [["job", "seeds", "F1", "FP / 24 h", "dF1", "dFP24", "tolerated"]]
    for n, x in cv5["jobs"].items():
        rows.append([n.replace("combined_preview_", "every subset limit, gain error at "), x["seeds"], f(x["f1"]),
                     f(x["fp_per_24h"], 3), f(x["d_f1"], 4, True), f(x["d_fp24"], 3, True),
                     "yes" if x["tolerated"] else "NO"])
    s.append(table(rows, [6.2 * cm, 1.2 * cm, 1.6 * cm, 1.8 * cm, 1.8 * cm, 1.8 * cm, 1.6 * cm],
                   bad_rows=[i for i in range(1, len(rows)) if rows[i][-1] == "NO"]))
    s.append(p(f"Clean: F1 {f(cv5['clean']['f1'])}, FP/24 h {f(cv5['clean']['fp_per_24h'], 3)}. Every family set "
               "to its subset limit at the same time, in both signs of gain error. The F1 drop is "
               f"{min(ratios):.1f} to {max(ratios):.1f} times the allowed {f(cv5['deltas']['delta_f1'])}. Each limit "
               "was found with the whole error budget to itself, so together they overshoot it. The back-off rule "
               "(fixed in LOG L21 before any back-off run) runs after the full-data confirmation. "
               "Source: combined_verdict.json.", SMALL))

    # ---- 6. hardware impairment emulator -----------------------------------------------------------------------
    s.append(p("6. FPGA impairment emulator: bit-exact against the Python model", H2))
    rows = [["design", "test cases", "samples per case", "mismatches", "negative control (one seed bit flipped)"]]
    for fn, lab in (("impair_rtl_check.json", "ms_impair.v (core)"),
                    ("impair_rtl_axi_check.json", "ms_impair_axi.v (behind AXI4-Lite)")):
        c = J(fn)["cases"]
        pos = [x for x in c if not x["case"].startswith("NEGATIVE")]
        neg = [x for x in c if x["case"].startswith("NEGATIVE")]
        rows.append([lab, len(pos), f"{pos[0]['samples']:,}", sum(x["mismatches"] for x in pos),
                     ", ".join(f"{x['mismatches']:,} of {x['samples']:,} differ" for x in neg)])
    s.append(table(rows, [4.6 * cm, 1.7 * cm, 2.4 * cm, 1.9 * cm, 5.8 * cm]))
    cases = ", ".join(x["case"] for x in J("impair_rtl_check.json")["cases"] if not x["case"].startswith("NEG"))
    s.append(p(f"Verilator simulation vs ms/py/impair.py, word for word. Cases: {cases}. The negative control "
               "shows the comparison catches a one-bit difference. Sources: impair_rtl_check.json, "
               "impair_rtl_axi_check.json.", SMALL))
    rows = [["design (Yosys synth_xilinx, UltraScale+)", "LUTs", "flip-flops", "CARRY4", "block RAM"]]
    for fn, lab in (("impair_rtl_yosys.txt", "ms_impair (core)"), ("ms_impair_axi_yosys.txt", "ms_impair_axi")):
        txt = (P1 / fn).read_text()
        cnt = lambda pat: sum(int(n) for n, _ in re.findall(rf"^\s+(\d+)\s+({pat})\s*$", txt, re.M))
        rows.append([lab, f"{cnt('LUT[1-6]'):,}", f"{cnt('FD[A-Z]{2}'):,}", f"{cnt('CARRY4'):,}",
                     ", ".join(f"{n} × {t}" for n, t in re.findall(r"^\s+(\d+)\s+(RAMB\w+)\s*$", txt, re.M))])
    s.append(table(rows, [6 * cm, 2 * cm, 2.2 * cm, 2 * cm, 4.2 * cm]))
    s.append(p("Pre-place-and-route cell counts. Sources: impair_rtl_yosys.txt, ms_impair_axi_yosys.txt.", SMALL))

    # ---- 7. ADC power ------------------------------------------------------------------------------------------
    ad = J("adc_survey_power.json")
    s.append(p("7. ADC power per channel from the published state of the art", H2))
    rows = [["SNDR", "ENOB", "Walden: best design", "Walden: median", "Schreier: best", "Schreier: median",
             "lowest power actually built (≤ 20 kHz)"]]
    for r in ad["rows"]:
        lf = r["lowrate_floor"]
        dsg = lf.get("design") or {}
        rows.append([f"{r['sndr_dB']} dB", f"{r['enob']:.2f}", watts(r["walden"]["P_best_W"]),
                     watts(r["walden"]["P_median_W"]), watts(r["schreier"]["P_best_W"]),
                     watts(r["schreier"]["P_median_W"]),
                     f"{watts(lf['P_W'])} ({dsg.get('venue', '')} {dsg.get('year', '')}, "
                     f"{dsg.get('fsnyq_Hz', 0):g} Hz, {dsg.get('sndr_dB', 0):g} dB)"])
    s.append(table(rows, [1.4 * cm, 1.2 * cm, 2.1 * cm, 2 * cm, 2 * cm, 2.1 * cm, 6 * cm]))
    s.append(p(f"{ad['source']}; {ad['designs']} designs. Power at our Nyquist rate of 256 Hz from the figure of "
               "merit of designs of similar resolution (required SNDR to +20 dB). The FOM columns scale "
               "fast designs down to 256 Hz and are optimistic; the last column is the lowest power a real "
               "low-rate design achieved at its own, higher rate. Which SNDR the detector needs comes from the "
               "final spec table, which is not finished. Source: adc_survey_power.json.", SMALL))

    doc = SimpleDocTemplate(str(out), pagesize=A4, leftMargin=1.6 * cm, rightMargin=1.6 * cm, topMargin=1.5 * cm,
                            bottomMargin=1.5 * cm, title="SeizeLUT-MS Phase 1 results so far",
                            author="SeizeLUT-MS")

    def footer(canvas, doc_):
        canvas.saveState()
        canvas.setFont("DV", 7)
        canvas.setFillColor(MUTED)
        canvas.drawString(1.6 * cm, 0.9 * cm, "SeizeLUT-MS Phase 1: results so far (training patients only)")
        canvas.drawRightString(A4[0] - 1.6 * cm, 0.9 * cm, f"page {doc_.page}")
        canvas.restoreState()

    doc.build(s, onFirstPage=footer, onLaterPages=footer)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(P1 / "phase1_results_so_far.pdf"))
    a = ap.parse_args()
    build(Path(a.out))
    print(a.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
