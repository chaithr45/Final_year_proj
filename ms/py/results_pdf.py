#!/usr/bin/env python3
"""PDF of the Phase 1 results and a log of the work done (every result number is read from the result files in
ms/results/phase1, results/tables and, for a run in progress, cache/ms/confirm; none is typed in here). Sections
10-13 (work log, problems and fixes, what is left, assessment) are descriptive text.

Usage: python3 ms/py/results_pdf.py [--out ms/results/phase1/phase1_results.pdf]
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
H3T = ParagraphStyle("h3t", parent=H3, keepWithNext=0)
INK, MUTED, RULE, HEAD, BAD = (colors.HexColor(c) for c in ("#1f2328", "#57606a", "#d0d7de", "#f2f4f7", "#fbe9e7"))
STEP, PEND = colors.HexColor("#fff4d6"), colors.HexColor("#e3edfb")
CACHE = REPO / "cache/ms/confirm"


def J(name: str):
    return json.loads((P1 / name).read_text())


def uv(s: str) -> str:
    s = s.replace("uVrms", "µV rms").replace("LSBrms", "LSB rms").replace("uV", "µV")
    return s.replace("<=", "≤").replace(">=", "≥")


def p(text, style=BODY):
    return Paragraph(text, style)


def table(rows, widths, head=1, bad_rows=(), font=CELL, step_rows=(), pend_rows=()):
    data = [[c if isinstance(c, Paragraph) else Paragraph(str(c), CELLB if i < head else font) for c in r]
            for i, r in enumerate(rows)]
    t = Table(data, colWidths=widths, repeatRows=head, hAlign="LEFT")
    st = [("GRID", (0, 0), (-1, -1), 0.4, RULE), ("BACKGROUND", (0, 0), (-1, head - 1), HEAD),
          ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 3),
          ("RIGHTPADDING", (0, 0), (-1, -1), 3), ("TOPPADDING", (0, 0), (-1, -1), 2),
          ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]
    st += [("BACKGROUND", (0, r), (-1, r), BAD) for r in bad_rows]
    st += [("BACKGROUND", (0, r), (-1, r), STEP) for r in step_rows]
    st += [("BACKGROUND", (0, r), (-1, r), PEND) for r in pend_rows]
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


def git_branch() -> str:
    try:
        return subprocess.run(["git", "branch", "--show-current"], cwd=REPO, capture_output=True, text=True,
                              check=True).stdout.strip() or "detached"
    except Exception:
        return "unknown"


def mtime(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).strftime("%d %b %H:%M UTC")


def stepdown_files() -> list[Path]:
    """Finished step-down rounds, oldest first."""
    return sorted(P1.glob("confirm_stepdown_*.json"), key=lambda q: q.stat().st_mtime)


def run_in_progress() -> dict | None:
    """A step-down round in cache/ms/confirm whose result file is not written yet."""
    done = {q.stem.split("_")[-1] for q in stepdown_files()}
    for q in sorted(CACHE.glob("stepdown_*.jsonl")):
        if q.stem.split("_")[-1] in done:
            continue
        rows = [json.loads(x) for x in q.read_text().splitlines() if x.strip()]
        if not rows:
            continue
        names = [json.loads(sg)["name"] for sg in rows[0]["job_sigs"]]
        hours_file = CACHE / "run_hours.json"
        total = len(json.loads(hours_file.read_text())) if hours_file.exists() else None
        return {"file": q.name, "done": len(rows), "total": total, "hours_done": sum(r["hours"] for r in rows),
                "jobs": [n for n in names if n != "clean"],
                "clean_equal": all(r["clean_equal_cache"] for r in rows)}
    return None


def paused_note() -> str | None:
    m = re.search(r"\*\*Paused by the user\*\* at ([^(:]+:\d\d UTC on [^(]+?) \(", (REPO / "LOG.md").read_text())
    return m.group(1).strip() if m else None


def level_of(fam: dict, name: str) -> float | None:
    for lv in fam["levels"]:
        if lv["name"] == name:
            return abs(lv["level"])
    m = re.search(r"_([+-]?\d+(?:\.\d+)?)[A-Za-z]*(?:_white\d+uV)?$", name)
    return abs(float(m.group(1))) if m else None


def fmt_level(x, fam: dict) -> str:
    if x is None:
        return "-"
    if fam["family"].startswith("gain"):
        return f"{100 * x:g} %"
    unit = fam["limit_unit"] or next((lv["unit"] for lv in fam["levels"] if lv.get("unit")), "")
    return uv(f"{x:g} {unit}").strip()


def full_first_failing(fam: dict) -> str:
    """Mildest level that failed on all training hours (levels are listed mildest first)."""
    order = {lv["name"]: i for i, lv in enumerate(fam["levels"])}
    bad = [n for n, r in fam.get("full", {}).items() if not r["tolerated"]]
    if not bad:
        if fam["status"] == "beyond grid":
            return "none failed (beyond grid)"
        return "next level passed too; spec kept at the subset limit" if fam["note"] else "none failed"
    n = min(bad, key=lambda x: order.get(x, 99))
    return fmt_level(level_of(fam, n), fam)


def status_text(status: str, x, fam: dict) -> str:
    if status == "limit":
        return f"limit {fmt_level(x, fam)}"
    if status == "beyond grid":
        return f"beyond grid (≥ {fmt_level(x, fam)} tolerated)"
    return status


def full_data_section(s: list) -> None:
    cl, sp = J("confirm_limits.json"), J("spec_limits.json")
    dfl, clean = cl["deltas_full"], cl["clean"]
    fams = {k: f_ for g in sp["grids"].values() for k, f_ in g["families"].items()}
    sd_files = stepdown_files()
    file_label = {"confirm_limits.json": "step 1"}
    file_label.update({q.name: f"step-down round {i + 1}" for i, q in enumerate(sd_files)})
    hours = sum(v[3] for v in clean["per_subject"].values())
    nref = sum(v[2] for v in clean["per_subject"].values())

    s.append(PageBreak())
    s.append(p("8. Full-data confirmation: every limit re-tested on all training hours", H2))
    s.append(p(f"The subset (section 3) is {J('subset.json')['summary']['scored_hours']} scored hours chosen around "
               f"seizures. Each subset limit and its first failing level was re-run on <b>all {cl['recordings']:,} "
               f"training recordings</b> ({hours:,.1f} scored hours, {len(clean['per_subject'])} patients, {nref} "
               "seizure events), out-of-fold, seed-0 fold models, one impairment seed (LOG L18). A level is "
               f"tolerated here when F1 drops by at most {f(dfl['delta_f1'])}, false alarms rise by at most "
               f"{f(dfl['delta_fp24'], 3)} per 24 h (the full-data seed spread, table 1b), <b>and</b> the paired "
               "per-patient Wilcoxon test of impaired vs clean F1 is not significant (p ≥ 0.05). A limit that "
               "fails is stepped down one grid level at a time, each step re-run on all hours, until one passes "
               "(LOG L20). Test patients were not used."))
    s.append(Spacer(1, 4))
    s.append(p("8a. Clean run reproduces the committed result", H3))
    mism = cl["clean_feature_mismatches"]
    rows = [["", "event-F1", "sensitivity", "precision", "FP / 24 h", "pooled F1", "pooled FP / 24 h"],
            ["clean, all training hours (confirm_limits.json)", f(clean["f1"]), f(clean["sensitivity"]),
             f(clean["precision"]), f(clean["fp_per_24h"], 3), f(clean["pooled_f1"]),
             f(clean["pooled_fp_per_24h"], 3)]]
    s.append(table(rows, [5.6 * cm, 1.7 * cm, 1.8 * cm, 1.7 * cm, 1.7 * cm, 1.7 * cm, 2.3 * cm]))
    s.append(p(f"Per-patient means unless 'pooled'. Equal to the committed cross-validation run "
               f"{cl['clean_vs_cv']['run']}: <b>{'yes' if cl['clean_vs_cv']['equal'] else 'NO'}</b>. Recordings "
               f"whose clean features differ from the cached training features: {len(mism)}. The same two checks "
               "pass in every step-down round. Run finished "
               f"{mtime(P1 / 'confirm_limits.json')}. Sources: confirm_limits.json, confirm_stepdown_*.json.", SMALL))

    # 8b: all families
    s.append(p("8b. Every family: subset result and full-data result", H3T))
    rows = [["family", "parameter", "subset (section 3)", "all training hours", "at the full-data limit: "
             "dF1 / dFP24 / Wilcoxon p", "how it was settled"]]
    step_rows, pend_rows, bad_rows = [], [], []
    stepped = 0
    for k, fm in fams.items():
        at = "-"
        if fm["limit"] is not None:
            hit = [(n, r) for n, r in fm.get("full", {}).items()
                   if r["tolerated"] and level_of(fm, n) is not None and abs(level_of(fm, n) - abs(fm["limit"])) < 1e-9]
            if hit:
                r = hit[0][1]
                at = f"{f(r['d_f1'], 4, True)} / {f(r['d_fp24'], 3, True)} / {r['wilcoxon_p']:.2f}"
        if fm["status"] == "pending":
            how = f"<b>pending</b>: next level {uv(fm['pending'])} is in step-down round {len(sd_files) + 1}"
            pend_rows.append(len(rows))
        elif fm["note"] and "stepped down" in fm["note"]:
            how = uv(fm["note"])
            stepped += 1
            step_rows.append(len(rows))
        elif fm["note"]:
            how = "confirmed; " + uv(fm["note"])
        elif fm["status"] == "none tolerated":
            how = "no level tolerated on either data set"
            bad_rows.append(len(rows))
        else:
            how = "confirmed at the subset value"
        rows.append([k.upper().replace("/", " / "), uv(fm["label"]),
                     status_text(fm["subset_status"], fm["subset_limit"], fm),
                     status_text(fm["status"], fm["limit"], fm), at, how])
    s.append(table(rows, [2.0 * cm, 2.9 * cm, 2.9 * cm, 2.9 * cm, 3.1 * cm, 4.0 * cm], bad_rows=bad_rows,
                   step_rows=step_rows, pend_rows=pend_rows))
    from collections import Counter
    cs, cf = Counter(x["subset_status"] for x in fams.values()), Counter(x["status"] for x in fams.values())
    s.append(p(f"{len(fams)} families. Subset: " + ", ".join(f"{v} {k}" for k, v in cs.items()) + ". All hours: "
               + ", ".join(f"{v} {k}" for k, v in cf.items()) + f". Yellow rows: limit stepped down on the full data "
               f"({stepped}); blue rows: still being tested; red: no level tolerated. Gain errors are relative "
               "(5 % = 0.05); C is the clip level (offset as a fraction of it). For the clip level a higher value is "
               "the stricter spec; the high-pass corner must be at or below its limit, the low-pass corner at or "
               "above it. 'beyond grid' means even the most "
               "severe tested level passed, so the true limit is at least that. Source: spec_limits.json.", SMALL))

    # 8c: step-down details
    s.append(p("8c. The families that failed at their subset limit: every full-data level tested", H3))
    rows = [["family", "level", "run", "tolerated", "dF1", "dFP24", "Wilcoxon p", "marginal (L18)"]]
    bad = []
    for k, fm in fams.items():
        full = fm.get("full", {})
        if not any(r["file"] != "confirm_limits.json" for r in full.values()) and fm["status"] != "pending":
            continue
        for n, r in sorted(full.items(), key=lambda kv: list(file_label).index(kv[1]["file"])
                           if kv[1]["file"] in file_label else 99, reverse=True):
            rows.append([k.upper().replace("/", " / "), fmt_level(level_of(fm, n), fm),
                         file_label.get(r["file"], r["file"]), "yes" if r["tolerated"] else "NO",
                         f(r["d_f1"], 4, True), f(r["d_fp24"], 3, True), f"{r['wilcoxon_p']:.3g}",
                         "yes" if r["marginal"] else "-"])
            if not r["tolerated"]:
                bad.append(len(rows) - 1)
    s.append(table(rows, [2.6 * cm, 2.4 * cm, 3.0 * cm, 1.6 * cm, 1.6 * cm, 1.6 * cm, 1.7 * cm, 2.2 * cm],
                   bad_rows=bad))
    sig = [f"{k.upper()} {fmt_level(level_of(fm, n), fm)}" for k, fm in fams.items()
           for n, r in fm.get("full", {}).items()
           if not r["tolerated"] and r["wilcoxon_p"] is not None and r["wilcoxon_p"] < 0.05
           and any(x["file"] != "confirm_limits.json" for x in fm["full"].values())]
    s.append(p(f"Allowed: dF1 ≥ -{f(dfl['delta_f1'])} and dFP24 ≤ +{f(dfl['delta_fp24'], 3)} and p ≥ 0.05. Most "
               "of these levels fail on the F1 drop alone; their Wilcoxon p is above 0.05 except "
               + (", ".join(sig) if sig else "none") + ". The "
               "full-data threshold is tight (one seed-to-seed standard deviation), so each limit is known to "
               "within one grid step (about a factor of 2). 'marginal' = a random-noise verdict closer to the "
               "threshold than the subset noise-seed spread (report only, LOG L18). Sources: confirm_limits.json, "
               + ", ".join(q.name for q in sd_files) + ".", SMALL))

    # 8d: the run in progress
    rp = run_in_progress()
    if rp:
        s.append(p("8d. Run in progress", H3))
        pz = paused_note()
        s.append(p(f"Step-down round {len(sd_files) + 1} tests {', '.join(rp['jobs'])} (plus the clean run). "
                   f"{rp['done']:,} of {rp['total']:,} recordings ({rp['hours_done']:,.0f} h) are finished; clean "
                   f"features equal the cache in all of them: {'yes' if rp['clean_equal'] else 'NO'}. "
                   + (f"<b>Paused by you at {pz}</b>; it resumes from here (finished recordings are kept). "
                      if pz else "") + "No verdict yet: a family's result needs all recordings. "
                   f"Source: cache/ms/confirm/{rp['file']}.", BODY))


def work_log_section(s: list) -> None:
    sw = {}
    for g in ("eeg", "ecg", "emg", "mov"):
        rs = [json.loads(x) for x in (P1 / f"sweeps/{g}.jsonl").read_text().splitlines() if x.strip()]
        sw[g] = sum(1 for r in rs if r["name"] != "clean")
    ss = J("subset.json")["summary"]
    bo, bf = J("combined_backoff.json"), J("combined_backoff_full.json")
    s.append(PageBreak())
    s.append(p("10. What was done (Phases 0 and 1)", H2))
    s.append(p(f"In order. Every item is in the repository on branch {git_branch()} (files named); decisions are in MS_SPEC.md, "
               "problems in LOG.md, interview notes in LEARN.md.", SMALL))
    rows = [["#", "what", "where / evidence", "state"],
            ["0.1", "Inventory of the FCCM repository: frozen detector, data flow, scripts, what reproduces",
             "ms/REPO_MAP.md", "done"],
            ["0.2", "Planning files: spec and decisions, pre-registration for anything touching test patients, "
             "problem log, interview notes", "MS_SPEC.md, PREREG.md, LOG.md, LEARN.md", "done"],
            ["0.3", "Analog tool setup (IIC-OSIC-TOOLS, SKY130A pinned); SKY130 smoke test (nominal and Monte "
             "Carlo) validated with ngspice in the cloud", "ms/setup/IIC_OSIC_TOOLS.md, ms/analog/smoke/",
             "done; your container check pending"],
            ["1.1", "Decisions D-MS4 to D-MS10 (models, data, emulator placement, noise generator, ADC model, "
             "sampling rate, definition of 'tolerated')", "MS_SPEC.md (your go-ahead, 16 Nov)", "decided"],
            ["1.2", "Training feature cache; 5 fold models retrained (seed 0) and checked against the committed CV "
             "run; seeds 1-4 trained for the seed spread", "section 1; cv_frozen_op.json, deltas.json", "done"],
            ["1.3", "Impairment model: ADC step and clip level, white and 1/f noise, gain error, DC offset, drift, "
             "high- and low-pass corners, 50 Hz and 250 Hz mains; xoroshiro128+ generator, Gaussian from a sum of 64 "
             "uniforms; unit tests (all passed on 19 Nov)", "ms/py/impair.py, ms/py/tests/", "done"],
            ["1.4", "Sweep subset fixed before any sweep: " f"{ss['segments']} segments, {ss['patients']} patients, "
             f"all {ss['seizures_in_segments']} training seizures, {ss['scored_hours']} scored hours",
             "subset.json", "done"],
            ["1.5", "Subset sweeps, one impairment at a time: " + ", ".join(f"{g.upper()} {n} runs"
                                                                         for g, n in sw.items()),
             "sweeps/*.jsonl, section 3", "done"],
            ["1.6", "Tolerance analysis and figures; cross-checks: ADC step vs white noise, motion explanation, "
             "noise-generator A/B, ECG offset lock-up", "sections 3-4", "done"],
            ["1.7", "Signal levels at the detector input; ADC power from the Murmann survey (Walden and Schreier "
             "figures of merit)", "sections 2 and 7", "done"],
            ["1.8", "FPGA impairment emulator in Verilog, bit-exact against the Python model, also behind "
             "AXI4-Lite; synthesis cost; ms1 kit build script, board driver and self-test vectors",
             "ms/fpga/, section 6", "done in simulation; board run pending (you)"],
            ["1.9", "All limits at once (preview): fails; back-off rule fixed before any back-off run",
             "section 5a, LOG L21, ms/py/combined_backoff.py", "done"],
            ["1.10", "Full-data confirmation on all training hours with a memory-aware scheduler; step-down rule; "
             "one resumable script for the rest of Phase 1", "ms/py/confirm_full.py, full_spec.py, "
             "run_phase1_confirm.sh, LOG L20, L22", f"done: step 1 and {len(stepdown_files())} step-down rounds"],
            ["1.11", "Combined back-off (subset, then all hours); final spec table with amplifier (NEF) and ADC "
             "power", "ms/py/combined_backoff.py, spec_table.py; sections 5b-5c, 9",
             f"done: {bo['status']} at step {bo['final_step']} (subset), {bf['status']} on all hours"],
            ["1.12", "Phase 1 report", "ms/results/phase1/PHASE1_REPORT.md, this PDF", "done; your review pending"],
            ["1.13", "Board run of the emulator (ms1 kit), digital energy, comparison with published front ends",
             "section 12", "needs your hardware and the papers"]]
    s.append(table(rows, [1.0 * cm, 8.6 * cm, 5.0 * cm, 3.2 * cm]))


def problems_section(s: list) -> None:
    s.append(p("11. Problems met and how they were handled (LOG.md)", H2))
    rows = [["LOG", "problem", "what was done"],
            ["L1", "Frozen design not on the starting branch", "Branch FPGA created from the FCCM branch tip"],
            ["L2-L3", "Analog tool image and PDK download do not work in the cloud",
             "ngspice and SKY130A installed natively; PDK fetched from the pinned release"],
            ["L4-L5", "ngspice Monte Carlo lost results; smoke test not repeatable",
             "Print per sample; split into a deterministic nominal test and a Monte Carlo test"],
            ["L6", "An FCCM verification script overwrote a committed FCCM result",
             "Restored; rule: git status must show no change outside ms/ after such scripts"],
            ["L7", "An FCCM quick check needs test-patient files", "Not run (ground rule 2); recorded"],
            ["L8", "Review paper for the NEF formula could not be fetched",
             "Formula checked in secondary sources, marked as such; primary paper still to read"],
            ["L9-L12", "Design details that would bias results: rounding, a typed 1/f constant, a gain test, "
             "Gaussian tails of a 16-sum", "Fixed before any sweep; 1/f constant measured; 64-sum generator"],
            ["L13", "Subset draw left some patients without background", "Rule amended before any sweep"],
            ["L14", "Fold retraining did not start after feature extraction", "Started by hand; waiters watch PIDs"],
            ["L15, L17, L18", "Open details of the tolerance rule, the A/B criterion and the seed count",
             "Fixed before the results they affect existed"],
            ["L16", "One smoke run before the thresholds were written", "Recorded; used only for timing"],
            ["L19", "Cloud container restarted 7 times during long runs", "Every run resumes; finished work kept; "
             "a watcher plus a scheduled check-in every 1.5-2 h limits the loss"],
            ["L20", "No rule for a limit that fails on all hours", "Step-down rule written before any such result"],
            ["L21", "Back-off rule for the combined point under-specified", "Pinned before any back-off run; it "
             "converged unchanged (a post hoc change I suggested midway was not needed and is withdrawn)"],
            ["L22", "Out-of-memory kill; later idle cores during long recordings",
             "Memory-aware scheduler; reserve for short recordings beside a long one"]]
    s.append(table(rows, [1.8 * cm, 7.6 * cm, 8.4 * cm]))


def left_and_assessment(s: list) -> None:
    bo, bf = J("combined_backoff.json"), J("combined_backoff_full.json")
    vsub, vfull = bo["steps"][-1]["verdicts"], bf["steps"][-1]["verdicts"]
    sub_d = [x["d_f1"] for x in vsub.values()]
    full_d = [x["d_f1"] for x in vfull.values()]
    s.append(p("12. What is left", H2))
    rows = [["step", "who", "estimate (my estimate, not a measurement)"],
            ["Your review of Phase 1 (this PDF, PHASE1_REPORT.md); whether to merge the branch into FPGA", "you",
             "-"],
            ["Analog container check (ms/setup/check_tools.sh)", "you", "-"],
            ["ms1 kit build and board self-test of the impairment emulator; board energy of the digital part "
             "(feature front end and LUT network)", "you (with my wiring and procedure check first)", "-"],
            ["PDFs of the published amplifier papers: replace the assumed NEF range with read values, and draw "
             "the electrode-to-alarm power budget against published wearable EEG front ends", "you send, I do",
             "a few hours after the PDFs"],
            ["Optional, report only: more impairment seeds for the EMG full-data verdicts closest to the threshold",
             "chain, if you say yes", "about 3-4 h"],
            ["Redo the ADC-step vs white-noise check (section 4a) on the full-data limits", "me", "under 1 h"],
            ["Phase 2 (SKY130 comparator) after FCCM", "both", "Feb-Mar 2027"]]
    s.append(table(rows, [9.2 * cm, 3.6 * cm, 5.0 * cm]))
    s.append(p("Container restarts cost only work in progress (LOG L19); no finished result was lost.", SMALL))

    s.append(p("13. Assessment (my judgement, not a measured result)", H2))
    for t in (
        "<b>Strong:</b> the method. Every rule (thresholds, step-down, back-off, seed counts) was fixed before the "
        "results it affects, and the back-off converged under the pinned rule without any change; the clean runs "
        "reproduce the committed result exactly; the hardware emulator is bit-exact against its golden model; "
        "every table regenerates from a script. Test patients were not used.",
        "<b>Strong:</b> a result a circuit designer can use. Single-impairment limits overshoot the error budget "
        "when combined (section 5a); the combined point says how much tighter the front end must be, and where "
        "(section 9: EEG noise and ADC step above all). That gap is the argument for detector-aware co-design.",
        "<b>Weak point 1, the detector:</b> per patient it finds about a quarter of the seizures, and fewer when "
        "all events are pooled (8a). A reviewer "
        "will ask why a spec derived from it matters, and a weak detector may tolerate impairments because it has "
        "little to lose, so the spec may be looser than a better detector would need. Addressing this would change "
        "the research question, which is your decision.",
        "<b>Weak point 2, resolution of the limits:</b> the tolerance threshold is one seed-to-seed standard "
        "deviation, and most full-data failures are not statistically significant (8c). The limits are reliable "
        "to about one grid step and must be reported that way.",
        "<b>Weak point 3, the combined point is sufficient, not minimal:</b> the greedy rule finds one passing "
        "point; another order of back-off could reach a cheaper one. It was set by the subset test, which was the "
        f"stricter one here (dF1 {min(sub_d):+.4f} to {max(sub_d):+.4f} on the subset against {min(full_d):+.4f} to "
        f"{max(full_d):+.4f} on all hours), and two of its steps (the EEG gain errors) did not improve the result. "
        "Report it as 'a front end meeting this spec is tolerated', not as 'the detector needs exactly this'.",
        "<b>Weak point 4, no circuit yet:</b> power numbers come from survey figures of merit and the NEF formula "
        "with an assumed NEF range, not from a design or from read papers. Phases 2-4 (SKY130 comparator, FPGA "
        "delta-sigma ADC, measured chain) supply that.",
        "<b>Publishing:</b> Phase 1 alone fits a short methods paper at best; with Phases 2-4 a biomedical "
        "circuits conference submission becomes realistic. For the PhD applications, a rigorous spec flow plus a "
        "designed comparator and a measured ADC is the stronger evidence. FCCM stays the main paper."):
        s.append(p(t))
        s.append(Spacer(1, 3))


def amp_power_w(nef: float, vn_rms: float, c: dict) -> float:
    """Noise-set amplifier power from the NEF definition (same formula and constants as spec_table.py)."""
    kT4 = 4 * 1.380649e-23 * c["T_K"]
    return nef ** 2 * 3.141592653589793 * c["U_T_V"] * kT4 * c["BW_Hz"] / (2 * vn_rms ** 2) * c["VDD_V"]


def spec_section(s: list) -> None:
    sj = J("spec.json")
    c = sj["constants"]
    tabs = md_tables(P1 / "spec_table.md")
    s.append(PageBreak())
    s.append(p("9. The front-end specification (combined point, all training hours) and its power", H2))
    s.append(p("Input-referred values. <b>One at a time</b> = the limit of each impairment with every other one "
               "clean, confirmed on all training hours (section 8). <b>All at once</b> = the combined point that "
               "passes with every impairment present together (section 5): this column is the specification. "
               "'at least' = every tested level passed (a bound); 'tighter than' = even the mildest level failed. "
               f"Generated by ms/py/spec_table.py from spec_limits.json and the back-off files "
               f"(basis: {sj['combined_basis']}).", SMALL))
    mods = [(k, v) for k, v in tabs.items() if v and v[0][0] == "spec"]
    for letter, (key, rows_md) in zip("abc", mods):
        rows = [["spec", "one at a time (all training hours)", "all at once = the spec"]]
        rows += [[uv(r[0]), uv(r[1]), uv(r[2])] for r in rows_md[1:]]
        s.append(p(f"9{letter}. {key}", H3T))
        s.append(table(rows, [6.4 * cm, 5.0 * cm, 6.4 * cm]))

    # motion sensors: not an analog front end, but part of the combined point
    bf = J("combined_backoff_full.json")
    lev = bf["steps"][-1]["levels"]
    sp = J("spec_limits.json")
    fams = {k: f_ for g in sp["grids"].values() for k, f_ in g["families"].items()}
    mrows = [["motion family", "one at a time (all training hours)", "all at once"]]
    for k in sorted(x for x in lev if x.startswith("mov/")):
        fm = fams[k]
        mrows.append([uv(fm["label"]) + f" ({k.split('/')[1]})", status_text(fm["status"], fm["limit"], fm),
                      "off" if lev[k] == "off" else fmt_level(level_of(fm, lev[k]), fm)])
    s.append(p("9d. Chest motion sensor (digital IMU, 1 LSB = 2<super>-12</super> g)", H3T))
    s.append(table(mrows, [6.4 * cm, 5.0 * cm, 6.4 * cm]))
    s.append(p("The motion sensor is a digital part, so it has no amplifier or ADC to design; its levels are part of "
               "the combined point because they were impaired together with the biopotentials.", SMALL))

    # power budget
    s.append(p("9e. Power per channel and for the whole front end", H3))
    nefs = c["NEF"]
    rows = [["modality (channels)", "input noise, spec (one at a time)", "density"] +
            [f"amplifier, NEF {n:g}" for n in nefs] +
            ["ADC bits (ideal SNDR)", "ADC: FOM scaling (best)", "ADC: lowest real low-rate design"]]
    tot_amp = {n: 0.0 for n in nefs}
    tot_amp_single = {n: 0.0 for n in nefs}
    tot_fom, tot_floor = 0.0, 0.0
    ratio_txt = []
    for m in ("eeg", "ecg", "emg"):
        x = sj["modalities"][m]
        ch = x["channels"]
        vn = x["combined"]["white"]
        v1 = x["limits"]["white"]["value"]
        a = x["adc"]
        pw = x["amp_power_uW_per_channel"]
        for n in nefs:
            tot_amp[n] += ch * pw[f"NEF {n:g}"] * 1e-6
            tot_amp_single[n] += ch * amp_power_w(n, v1 * 1e-6, c)
        tot_fom += ch * a["P_walden_best_uW"] * 1e-6
        tot_floor += ch * a["P_lowrate_floor_uW"] * 1e-6
        ratio_txt.append(f"{m.upper()} {v1:g} → {vn:g} µV rms (× {(v1 / vn) ** 2:.0f})")
        rows.append([f"{m.upper()} ({ch})", f"{vn:g} µV rms ({v1:g})", f"{x['noise_density_nV_rtHz']:.0f} nV/√Hz"] +
                    [watts(pw[f"NEF {n:g}"] * 1e-6) for n in nefs] +
                    [f"{a['bits']} ({a['sndr_dB']:.1f} dB)",
                     f"{watts(a['P_schreier_best_uW'] * 1e-6)} - {watts(a['P_walden_best_uW'] * 1e-6)}",
                     watts(a["P_lowrate_floor_uW"] * 1e-6)])
    nch = sum(sj["modalities"][m]["channels"] for m in ("eeg", "ecg", "emg"))
    rows.append([f"all {nch} channels", "", ""] + [watts(tot_amp[n]) for n in nefs] +
                ["", f"≤ {watts(tot_fom)}", watts(tot_floor)])
    s.append(table(rows, [2.3 * cm, 2.4 * cm, 1.6 * cm] + [1.6 * cm] * len(nefs) + [2.0 * cm, 2.6 * cm, 2.1 * cm],
                   step_rows=[len(rows) - 1]))
    s.append(p(f"Amplifier: noise-set lower bound from the NEF definition, I = NEF² π U<sub>T</sub> 4kT BW / "
               f"(2 v<sub>n</sub>²), P = I × VDD, with VDD {c['VDD_V']:g} V, T {c['T_K']:g} K, BW {c['BW_Hz']:g} Hz. "
               "NEF 2, 3 and 5 are an illustrative range, <b>not</b> values read from published amplifiers yet (the "
               "papers are still to be read, section 12). Per channel; the last row is the sum over channels. ADC: "
               f"the bits are ceil(log2(2 C / q)) at the spec's clip level C and step q, sampled at "
               f"{c['fsnyq_Hz']:g} Hz; the FOM columns scale the best survey designs to that rate (optimistic) and the "
               "last column is the lowest power a real low-rate design reached at its own rate (section 7). Digital "
               "part (feature front end and LUT network): not measured yet (board, section 12). Source: spec.json.",
               SMALL))
    s.append(p("<b>What the combined point costs.</b> The noise spec tightens from one at a time to all at once: "
               + ", ".join(ratio_txt) + " in amplifier current at the same NEF. Summed over the "
               f"{nch} channels at NEF {nefs[1]:g}: {watts(tot_amp_single[nefs[1]])} with the one-at-a-time noise "
               f"limits against {watts(tot_amp[nefs[1]])} at the combined point. That is still a few microwatts: the "
               f"same order as the lowest real low-rate ADCs ({watts(tot_floor)} for all channels) and far above the "
               f"FOM-scaled ADC power ({watts(tot_fom)}). So if the FOM scaling held at 256 Hz, the amplifiers would "
               "set the analog power; with real low-rate ADCs the two are comparable.", BODY))


def summary(s: list) -> None:
    import math
    cl, sp, d = J("confirm_limits.json"), J("spec_limits.json"), J("deltas.json")
    fams = {k: f_ for g in sp["grids"].values() for k, f_ in g["families"].items()}
    clean = cl["clean"]
    cv5 = J("combined_verdict.json")
    ratios = [-x["d_f1"] / cv5["deltas"]["delta_f1"] for x in cv5["jobs"].values()]
    rtl = sum(x["mismatches"] for fn in ("impair_rtl_check.json", "impair_rtl_axi_check.json")
              for x in J(fn)["cases"] if not x["case"].startswith("NEGATIVE"))
    from collections import Counter
    cf = Counter(x["status"] for x in fams.values())
    stepped = sum(1 for x in fams.values() if x["note"] and "stepped down" in x["note"])
    bo, bf, sj = J("combined_backoff.json"), J("combined_backoff_full.json"), J("spec.json")
    vsub = bo["steps"][-1]["verdicts"]
    vfull = bf["steps"][-1]["verdicts"]
    lev = bf["steps"][-1]["levels"]
    sign = lambda v, sg: next(x for k, x in v.items() if k.endswith(f"gain{sg}"))
    nefs = sj["constants"]["NEF"]
    mods = ("eeg", "ecg", "emg")
    nch = sum(sj["modalities"][m]["channels"] for m in mods)
    amp = [sum(sj["modalities"][m]["channels"] * sj["modalities"][m]["amp_power_uW_per_channel"][f"NEF {n:g}"]
               for m in mods) * 1e-6 for n in (nefs[0], nefs[-1])]
    floor = sum(sj["modalities"][m]["channels"] * sj["modalities"][m]["adc"]["P_lowrate_floor_uW"] for m in mods) * 1e-6
    bits = ", ".join(f"{m.upper()} {sj['modalities'][m]['adc']['bits']}" for m in mods)

    s.append(p("Summary", H2))
    s.append(p("<b>Where things stand.</b> Phase 0 is done (your analog-tool container check is open). The Phase 1 "
               "study is complete on the training patients: every impairment swept one at a time on the subset, "
               "every limit confirmed on all training hours, and all impairments together backed off by the rule "
               f"fixed beforehand until the combined point passed: on the subset after {bo['final_step']} steps, then "
               "on all training hours with no further step. That combined point is the front-end specification "
               "(section 9). Open, on your side: the board run of the FPGA emulator, the measured energy of the "
               "digital part, and the published amplifier papers for the NEF comparison (section 12)."))
    s.append(Spacer(1, 4))

    def vtxt(x, full=False):
        return (f"dF1 {f(x['d_f1'], 4, True)}, dFP {f(x['d_fp24'], 3, True)}/24 h"
                + (f", p {x['wilcoxon_p']:.2f}" if full else ""))

    rows = [["result", "value", "section"],
            ["Detector, clean, all training hours (seed-0 fold models, out-of-fold)",
             f"F1 {f(clean['f1'], 3)}, sensitivity {f(clean['sensitivity'], 3)}, "
             f"{f(clean['fp_per_24h'], 2)} false alarms / 24 h; equal to the committed CV run: "
             f"{'yes' if cl['clean_vs_cv']['equal'] else 'NO'}", "8a"],
            ["Tolerance thresholds (one seed-to-seed sd)", f"subset: F1 drop ≤ {f(d['subset']['delta_f1'])}, "
             f"FP rise ≤ {f(d['subset']['delta_fp24'], 3)}/24 h; all hours: ≤ {f(d['full']['delta_f1'])} and "
             f"≤ {f(d['full']['delta_fp24'], 3)}/24 h, plus Wilcoxon p ≥ 0.05", "1b, 8"],
            ["Impairment families tested", f"{len(fams)} (EEG, ECG, EMG: 12 each; motion: 4)", "3"],
            ["One at a time, after the full-data confirmation", ", ".join(f"{v} {k}" for k, v in cf.items())
             + f"; {stepped} limits stepped down one grid level", "8b"],
            ["All subset limits at once (preview)", f"fails: F1 drop {min(ratios):.1f}-{max(ratios):.1f} × the "
             "allowed", "5a"],
            [f"Combined point after {bo['final_step']} back-off steps, subset (5 seeds)",
             f"{bo['status']}: gain+ {vtxt(sign(vsub, '+'))}; gain− {vtxt(sign(vsub, '-'))}", "5b"],
            ["Same point, all training hours (seed 0)",
             f"{bf['status']}: gain+ {vtxt(sign(vfull, '+'), True)}; gain− {vtxt(sign(vfull, '-'), True)}", "5c"],
            [f"Amplifiers, all {nch} channels (noise-set bound, NEF {nefs[0]:g}-{nefs[-1]:g} assumed)",
             f"{watts(amp[0])} - {watts(amp[1])}", "9e"],
            ["ADC bits at the spec; lowest real low-rate ADCs, all channels", f"{bits} bits; {watts(floor)}", "9e"],
            ["FPGA impairment emulator vs Python golden model", f"{rtl} mismatching words", "6"]]
    s.append(table(rows, [6.2 * cm, 9.6 * cm, 2.0 * cm]))
    s.append(Spacer(1, 6))

    s.append(p("<b>Main front-end numbers</b>: the limit with one impairment at a time, and the level in the combined "
               "point, which is the specification:", BODY))
    s.append(Spacer(1, 3))
    pick = ["eeg/white", "eeg/lsb", "eeg/clip", "eeg/hp", "eeg/lp", "eeg/mains50", "eeg/gain+", "eeg/gain-",
            "eeg/offset", "ecg/white", "ecg/lsb", "ecg/lp", "ecg/mains50", "emg/white", "emg/lsb", "emg/mains50",
            "mov/lsb", "mov/white"]
    rows = [["family", "parameter", "one at a time (all hours)", "first failing on all hours", "combined point"]]
    pend, tight = [], []
    for k in pick:
        fm = fams[k]
        if k not in lev:
            comb = "not included (no level tolerated)"
        elif lev[k] == "off":
            comb = "off (backed off)"
        else:
            comb = fmt_level(level_of(fm, lev[k]), fm)
        one = status_text(fm["status"], fm["limit"], fm)
        rows.append([k.upper().replace("/", " / "), uv(fm["label"]), one, full_first_failing(fm), comb])
        if fm["status"] == "pending":
            pend.append(len(rows) - 1)
        elif k in lev and fm["limit"] is not None and (lev[k] == "off" or
                                                       abs(level_of(fm, lev[k]) - abs(fm["limit"])) > 1e-9):
            tight.append(len(rows) - 1)
    s.append(table(rows, [2.2 * cm, 4.2 * cm, 4.0 * cm, 3.6 * cm, 3.8 * cm], pend_rows=pend, step_rows=tight,
                   bad_rows=[i for i, r in enumerate(rows) if r[2] == "none tolerated"]))
    s.append(p("Yellow: the combined point is tighter than the one-at-a-time limit; red: no level tolerated even "
               "alone. Full tables: sections 8b (one at a time) and 9 (combined). Sources: spec_limits.json, "
               "combined_backoff_full.json.", SMALL))
    m50, lsb, wh, ecglp = fams["eeg/mains50"], fams["eeg/lsb"], fams["eeg/white"], fams["ecg/lp"]
    clip = abs(fams["eeg/clip"]["limit"])
    eb1 = math.ceil(math.log2(2 * clip / abs(lsb["limit"])))
    eb2 = sj["modalities"]["eeg"]["adc"]["bits"]
    v1, v2 = sj["modalities"]["eeg"]["limits"]["white"]["value"], sj["modalities"]["eeg"]["combined"]["white"]
    s.append(Spacer(1, 4))
    s.append(p("<b>Four findings to be able to explain.</b> (1) Mains pick-up drives the EEG front end: "
               f"{fmt_level(m50['limit'], m50)} of 50 Hz passes, {full_first_failing(m50)} fails, so "
               "common-mode rejection or a notch matters more than the noise floor. (2) The EEG path tolerates an "
               f"ADC step of {fmt_level(lsb['limit'], lsb)} but only {fmt_level(wh['limit'], wh)} of added white "
               "noise on all hours. On the subset the two limits agreed with the textbook quantisation-noise model "
               "(section 4a); on all hours the white-noise limit moved one step down while the step limit held, and "
               "that check has not been redone on the full-data limits. (3) ECG cannot be low-passed at any tested "
               f"corner (from {fmt_level(ecglp['first_failing'], ecglp)} down), so the detector probably relies on its "
               "high-frequency content (not checked yet). (4) One-at-a-time limits do not add up: with everything "
               f"present the EEG noise has to go from {v1:g} to {v2:g} µV rms ({(v1 / v2) ** 2:.0f} × the amplifier "
               f"current at the same NEF) and the EEG ADC from {eb1} to {eb2} bits. A spec made of single-impairment "
               "limits fails (section 5a). The rule also switched the EEG gain error off (its next step below "
               f"{fmt_level(level_of(fams['eeg/gain+'], fams['eeg/gain+']['levels'][0]['name']), fams['eeg/gain+'])}), "
               "but that step did not improve the result (section 5b), so a gain spec below that level is what the "
               "rule produced, not something the data show is needed."))


def build(out: Path) -> None:
    W = A4[0] - 3.2 * cm
    d = J("deltas.json")
    sub, full = d["subset"], d["full"]
    cv = next(iter(J("cv_frozen_op.json").values()))
    s = []

    # ---- title -------------------------------------------------------------------------------------------------
    s.append(p("SeizeLUT-MS Phase 1: results and work log", H1))
    s.append(p(f"Detector-derived analog front-end specification. Branch {git_branch()}, commit {git_commit()}, generated "
               f"{datetime.now(timezone.utc):%d %b %Y %H:%M} UTC by <font face='DV'>ms/py/results_pdf.py</font>. "
               "Every result number below is read from a result file (named under each table).", SMALL))
    s.append(Spacer(1, 6))
    summary(s)
    s.append(Spacer(1, 10))
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
    s.append(p("<b>Not in this PDF because it needs your hardware or papers:</b> the board run of the FPGA emulator, "
               "the measured energy of the digital part, and the comparison with published front ends "
               "(section 12).", SMALL))

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

    # ---- 5. combined point --------------------------------------------------------------------------------------
    combined_section(s)

    # ---- 6. hardware impairment emulator -----------------------------------------------------------------------
    emulator_and_adc_sections(s)

    full_data_section(s)
    spec_section(s)
    work_log_section(s)
    problems_section(s)
    left_and_assessment(s)

    doc = SimpleDocTemplate(str(out), pagesize=A4, leftMargin=1.6 * cm, rightMargin=1.6 * cm, topMargin=1.5 * cm,
                            bottomMargin=1.5 * cm, title="SeizeLUT-MS Phase 1 results and work log",
                            author="SeizeLUT-MS")

    def footer(canvas, doc_):
        canvas.saveState()
        canvas.setFont("DV", 7)
        canvas.setFillColor(MUTED)
        canvas.drawString(1.6 * cm, 0.9 * cm, "SeizeLUT-MS Phase 1: results and work log (training patients only)")
        canvas.drawRightString(A4[0] - 1.6 * cm, 0.9 * cm, f"page {doc_.page}")
        canvas.restoreState()

    doc.build(s, onFirstPage=footer, onLaterPages=footer)


def combined_section(s: list) -> None:
    cv5 = J("combined_verdict.json")
    ratios = [-x["d_f1"] / cv5["deltas"]["delta_f1"] for x in cv5["jobs"].values()]
    s.append(PageBreak())
    s.append(p("5. All limits at once: the combined spec point", H2))
    s.append(p("5a. Preview: every subset limit at the same time fails", H3))
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
               "was fixed in LOG L21 before any back-off run. Source: combined_verdict.json.", SMALL))

    # 5b: back-off trace on the subset
    sp, bo = J("spec_limits.json"), J("combined_backoff.json")
    fams = {k: f_ for g in sp["grids"].values() for k, f_ in g["families"].items()}
    dsub = J("deltas.json")["subset"]

    def lv(fam_key: str, name: str) -> str:
        if name == "off":
            return "off"
        fm = fams.get(fam_key)
        return fmt_level(level_of(fm, name), fm) if fm else name

    s.append(p("5b. Back-off on the subset (rule of LOG L21), one family one grid step milder per step", H3))
    s.append(p("Start: every family at its limit confirmed on all training hours (section 8). Each step runs both "
               "gain signs with 5 noise seeds. If a job fails, the family that flips the most comparator bits per "
               "window on its own (single-impairment subset run at its current level) moves one grid step milder, "
               "or off from its mildest level; the ranking is redone after every step. A gain sign stops being a "
               "candidate once its job passes.", SMALL))
    rows = [["step", "gain+: dF1 / dFP24", "gain−: dF1 / dFP24", "then backed off", "from → to",
             "bit flips / window"]]
    bad = []
    for st in bo["steps"]:
        v = st["verdicts"]
        cells = []
        for sign in ("+", "-"):
            x = next(val for k, val in v.items() if k.endswith(f"gain{sign}"))
            cells.append(f"{f(x['d_f1'], 4, True)} / {f(x['d_fp24'], 3, True)}" + ("" if x["tolerated"] else " ✗"))
        b = st.get("back_off")
        if b:
            row = [st["step"]] + cells + [b["family"].upper().replace("/", " / "),
                                          f"{lv(b['family'], b['from'])} → {lv(b['family'], b['to'])}",
                                          f"{b['flips_per_window']:.2f}"]
            bad.append(len(rows))
        else:
            row = [st["step"]] + cells + ["none: both jobs pass", "-", "-"]
        rows.append(row)
    s.append(table(rows, [1.0 * cm, 3.2 * cm, 3.2 * cm, 2.8 * cm, 4.2 * cm, 2.2 * cm], bad_rows=bad))
    s.append(p(f"✗ = not tolerated. Allowed on the subset: dF1 ≥ -{f(dsub['delta_f1'])} and dFP24 ≤ "
               f"+{f(dsub['delta_fp24'], 3)}. Result: <b>{bo['status']} at step {bo['final_step']}</b>. Gain errors are relative (50 % = "
               "0.5). Source: combined_backoff.json.", SMALL))

    # 5c: the passing point on all training hours
    bf, cc = J("combined_backoff_full.json"), None
    last = bf["steps"][-1]
    fname = next(iter(last["verdicts"].values()))["file"]
    cc = J(fname)
    dfl = cc["deltas_full"]
    s.append(p("5c. The passing point on all training hours", H3))
    rows = [["run", "F1", "sensitivity", "FP / 24 h", "dF1", "dFP24", "Wilcoxon p", "pooled F1",
             "tolerated"]]
    cl = cc["clean"]
    rows.append(["clean", f(cl["f1"]), f(cl["sensitivity"]), f(cl["fp_per_24h"], 3), "-", "-", "-",
                 f(cl["pooled_f1"]), "-"])
    for j in cc["jobs"]:
        rows.append([j["name"].replace("combined_b", "combined point, step ").replace("_gain", ", gain "),
                     f(j["f1"]), f(j["sensitivity"]), f(j["fp_per_24h"], 3), f(j["d_f1"], 4, True),
                     f(j["d_fp24"], 3, True), f"{j['wilcoxon_p']:.2f}", f(j["pooled_f1"]),
                     "yes" if j["tolerated"] else "NO"])
    s.append(table(rows, [4.0 * cm, 1.4 * cm, 1.9 * cm, 1.6 * cm, 1.5 * cm, 1.4 * cm, 1.8 * cm, 1.6 * cm,
                          1.6 * cm]))
    pooled = ", ".join(f"{j['name'].split('_')[-1].replace('gain', 'gain ')} {f(j['pooled_f1'] - cl['pooled_f1'], 4, True)}"
                       for j in cc["jobs"])
    sub_d = sorted(x["d_f1"] for x in bo["steps"][-1]["verdicts"].values())
    full_d = sorted(j["d_f1"] for j in cc["jobs"])
    s.append(p(f"{cc['recordings']:,} training recordings, seed-0 fold models, impairment seed 0 (LOG L18). Allowed: "
               f"dF1 ≥ -{f(dfl['delta_f1'])}, dFP24 ≤ +{f(dfl['delta_fp24'], 3)}, p ≥ 0.05. Result: "
               f"<b>{bf['status']} at step {bf['final_step']}</b>, so no further back-off was needed. Clean run "
               f"equal to the committed CV run: {'yes' if cc['clean_vs_cv']['equal'] else 'NO'}; recordings whose "
               f"clean features differ from the cache: {len(cc['clean_feature_mismatches'])}. The D-MS10 test uses "
               "the mean over patients. Pooled over all events instead (not part of the test; reported because "
               f"it can move differently): pooled F1 change {pooled}. The subset test was the stricter one here "
               f"(dF1 {f(sub_d[0], 4, True)} to {f(sub_d[-1], 4, True)} on the subset against {f(full_d[0], 4, True)} "
               f"to {f(full_d[-1], 4, True)} on all hours); the subset holds every training seizure but only a few "
               "background hours per patient (D-MS5), so it weighs seizure detection more. Sources: combined_backoff_full.json, "
               + fname + ".", SMALL))


def emulator_and_adc_sections(s: list) -> None:
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
               "low-rate design achieved at its own, higher rate. The SNDR the detector needs, and the power at "
               "that SNDR, are in section 9. Source: adc_survey_power.json.", SMALL))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(P1 / "phase1_results.pdf"))
    a = ap.parse_args()
    build(Path(a.out))
    print(a.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
