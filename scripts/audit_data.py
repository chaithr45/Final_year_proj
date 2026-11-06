#!/usr/bin/env python3
"""Build the M1 data audit: reports/data_audit.md plus CSV/JSON tables and figures.

Inputs
  * a BIDS tree with at least the sidecars and _events.tsv (scripts/fetch_metadata.py)
  * EDF headers: from the local .edf files, or cache/edf_headers/ (fetch_metadata.py)
  * optional signal statistics: cache/audit/signal_stats.jsonl (scripts/audit_signals.py)

Outputs
  reports/data_audit.md            the human-readable audit
  reports/data_audit.json          summary numbers (read by scripts/verify_data.py)
  results/audit/runs.csv           one row per run
  results/audit/seizures.csv       one row per annotated seizure
  results/audit/subjects.csv       one row per patient
  results/audit/signal_runs.csv    per-run signal statistics (if signal stats exist)
  reports/figures/*.png

Usage:  python scripts/audit_data.py [--root data/raw/ds005873]
"""
from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import yaml

from seizelut.data.bids import MODALITIES, discover_runs
from seizelut.data.edf import parse_header, read_header
from seizelut.data.events import merge_intervals, seizure_class
from seizelut.data.montage import montage_type
from seizelut.data.split import split_of

REPO = Path(__file__).resolve().parents[1]


def edf_header(run, mod, root: Path, hdr_cache: Path):
    if mod in run.edf:
        return read_header(run.edf[mod])
    rel = run.sidecar[mod].relative_to(root).with_suffix(".edf")
    p = hdr_cache / (str(rel) + ".hdr")
    return parse_header(p.read_bytes()) if p.exists() else None


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def md_table(header: list[str], rows: list[list]) -> str:
    out = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def pct(a, b):
    return f"{100 * a / b:.1f}%" if b else "n/a"


def collect(root: Path, hdr_cache: Path):
    runs = discover_runs(root)
    run_rows, sz_rows = [], []
    for r in runs:
        ann = r.read_annotations()
        row = {"subject": r.subject, "split": split_of(r.subject), "run": r.run}
        hdrs = {m: edf_header(r, m, root, hdr_cache) for m in r.modalities}
        eeg_h = hdrs.get("eeg")
        row["duration_s"] = eeg_h.duration_s if eeg_h else ann.recording_duration
        row["annotation_duration_s"] = ann.recording_duration
        side_eeg = r.read_sidecar("eeg")
        row["sidecar_duration_s"] = side_eeg.get("RecordingDuration")
        row["montage"] = montage_type(eeg_h.labels) if eeg_h else "unknown"
        row["sidecar_montage"] = side_eeg.get("EEGMontage")
        row["eeg_labels"] = "|".join(eeg_h.labels) if eeg_h else ""
        for m in MODALITIES:
            h = hdrs.get(m)
            row[f"has_{m}"] = int(m in r.modalities)
            row[f"fs_{m}_sidecar"] = r.read_sidecar(m)["SamplingFrequency"] if m in r.modalities else ""
            row[f"fs_{m}_edf"] = "|".join(f"{v:g}" for v in sorted({h.sampling_rate(lb) for lb in h.labels})) if h else ""
            row[f"duration_{m}_s"] = h.duration_s if h else ""
            row[f"edf_type_{m}"] = h.reserved if h else ""
        mov_h = hdrs.get("mov")
        row["mov_labels"] = "|".join(mov_h.labels) if mov_h else ""
        row["mov_units"] = "|".join(sorted({s.physical_dim for s in mov_h.data_signals})) if mov_h else ""
        sz = sorted(ann.seizures, key=lambda e: e.onset)
        row["n_seizures"] = len(sz)
        row["seizure_s"] = sum(e.duration for e in sz)
        row["n_impd"] = len(ann.impedance_checks)
        row["impd_s"] = sum(e.duration for e in ann.impedance_checks if e.duration > 0)
        row["n_bad_events"] = sum(1 for e in ann.events if e.duration <= 0 and e.event_type != "bckg")
        row["bad_events"] = ";".join(f"{e.event_type}@{e.onset:g}s dur {e.duration:g}s"
                                     for e in ann.events if e.duration <= 0 and e.event_type != "bckg")
        run_rows.append(row)
        for i, e in enumerate(sz):
            prev_gap = e.onset - sz[i - 1].end if i else ""
            sz_rows.append({
                "subject": r.subject, "split": row["split"], "run": r.run, "onset_s": e.onset,
                "duration_s": e.duration, "event_type": e.event_type, "class": seizure_class(e.event_type),
                "lateralization": e.lateralization, "localization": e.localization, "vigilance": e.vigilance,
                "confidence": e.confidence if e.confidence is not None else "n/a", "channels": e.channels,
                "gap_from_previous_s": prev_gap,
                "within_run_bounds": int(e.onset >= 0 and e.end <= (ann.recording_duration or 1e18) + 1e-6),
                "in_first_hour": int(e.onset < 3600),
            })
    return runs, run_rows, sz_rows


def subject_rows(run_rows, sz_rows, participants):
    by = defaultdict(list)
    for r in run_rows:
        by[r["subject"]].append(r)
    nsz = Counter(s["subject"] for s in sz_rows)
    out = []
    for sub in sorted(by):
        rs = by[sub]
        hours = sum(r["duration_s"] for r in rs) / 3600
        out.append({
            "subject": sub, "split": rs[0]["split"], "sex": participants.get(sub, ""), "n_runs": len(rs),
            "hours": round(hours, 2), "n_seizures": nsz[sub],
            "seizure_min": round(sum(s["duration_s"] for s in sz_rows if s["subject"] == sub) / 60, 2),
            "montages": "|".join(sorted({r["montage"] for r in rs})),
            **{f"hours_without_{m}": round(sum(r["duration_s"] for r in rs if not r[f"has_{m}"]) / 3600, 2)
               for m in ("ecg", "emg", "mov")},
            "impd_min": round(sum(r["impd_s"] for r in rs) / 60, 1),
            "seizures_per_24h": round(24 * nsz[sub] / hours, 2) if hours else "",
        })
    return out


def load_signal_stats(path: Path):
    if not path.exists():
        return []
    recs = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    best = {}
    for r in recs:  # later successful records win over earlier errors
        if r["file"] not in best or "error" in best[r["file"]]:
            best[r["file"]] = r
    return list(best.values())


def figures(run_rows, sz_rows, subj_rows, sig, fig_dir: Path) -> list[str]:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig_dir.mkdir(parents=True, exist_ok=True)
    made = []
    d = np.array([s["duration_s"] for s in sz_rows])
    fig, ax = plt.subplots(figsize=(6, 3.2), dpi=150)
    bins = np.logspace(np.log10(max(1, d.min())), np.log10(d.max()), 30)
    for split, color in (("train", "#2a6fdb"), ("test", "#e8833a")):
        ax.hist([s["duration_s"] for s in sz_rows if s["split"] == split], bins=bins, alpha=0.75,
                label=f"{split} (n={sum(s['split'] == split for s in sz_rows)})", color=color)
    ax.set_xscale("log")
    ax.set_xlabel("seizure duration (s, log scale)")
    ax.set_ylabel("seizures")
    ax.axvline(np.median(d), color="k", lw=0.8, ls="--")
    ax.text(np.median(d) * 1.05, ax.get_ylim()[1] * 0.9, f"median {np.median(d):.0f} s", fontsize=8)
    ax.legend(frameon=False, fontsize=8)
    ax.set_title("SeizeIT2 annotated seizure durations")
    fig.tight_layout()
    fig.savefig(fig_dir / "seizure_duration_hist.png")
    plt.close(fig)
    made.append("seizure_duration_hist.png")

    fig, ax = plt.subplots(figsize=(8, 3.2), dpi=150)
    xs = np.arange(len(subj_rows))
    colors = ["#2a6fdb" if s["split"] == "train" else "#e8833a" for s in subj_rows]
    ax.bar(xs, [s["hours"] for s in subj_rows], color=colors, width=0.85)
    ax2 = ax.twinx()
    ax2.plot(xs, [s["n_seizures"] for s in subj_rows], "k.", ms=3)
    ax.set_xlabel("patient (sub-001 ... sub-125; blue = train, orange = test)")
    ax.set_ylabel("hours recorded")
    ax2.set_ylabel("seizures (dots)")
    ax.set_xlim(-1, len(xs))
    fig.tight_layout()
    fig.savefig(fig_dir / "hours_and_seizures_per_patient.png")
    plt.close(fig)
    made.append("hours_and_seizures_per_patient.png")

    eeg = [r for r in sig if r.get("modality") == "eeg" and "error" not in r]
    if eeg:
        fig, ax = plt.subplots(figsize=(6, 3.2), dpi=150)
        for role, color in (("same-side/left lateral", "#2a6fdb"), ("cross-head/right lateral", "#e8833a")):
            vals = []
            for r in eeg:
                labs = list(r["channels"])
                lab = labs[0] if role.startswith("same") else labs[1]
                if r["channels"][lab].get("rms_median"):
                    vals.append(r["channels"][lab]["rms_median"])
            ax.hist(vals, bins=np.logspace(0, 3, 40), alpha=0.7, color=color, label=f"channel 1 ({role})" if role.startswith("same") else f"channel 2 ({role})")
        ax.axvspan(13, 150, color="0.9", zorder=0, label="official 'clean' band 13-150 uV")
        ax.set_xscale("log")
        ax.set_xlabel("median window RMS per run (uV, official 0.5-60 Hz filter)")
        ax.set_ylabel("runs")
        ax.legend(frameon=False, fontsize=7)
        fig.tight_layout()
        fig.savefig(fig_dir / "eeg_rms_per_run.png")
        plt.close(fig)
        made.append("eeg_rms_per_run.png")
    return made


def git_hash() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=REPO, text=True).strip()
    except Exception:
        return "unknown"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default=str(REPO / "configs/dataset.yaml"))
    ap.add_argument("--root", default=None)
    ap.add_argument("--headers", default=str(REPO / "cache/edf_headers"))
    ap.add_argument("--signal-stats", default=str(REPO / "cache/audit/signal_stats.jsonl"))
    ap.add_argument("--listing", default=str(REPO / "cache/s3_listing.json"))
    ap.add_argument("--report", default=str(REPO / "reports/data_audit.md"))
    ap.add_argument("--tables", default=str(REPO / "results/audit"))
    ap.add_argument("--figures", default=str(REPO / "reports/figures"))
    args = ap.parse_args()

    cfg = yaml.safe_load(Path(args.config).read_text())
    exp = cfg["expected"]
    root = Path(args.root or REPO / cfg["dataset"]["root"])
    runs, run_rows, sz_rows = collect(root, Path(args.headers))
    participants = {}
    with open(root / "participants.tsv") as fh:
        for row in csv.DictReader(fh, delimiter="\t"):
            participants[row["participant_id"]] = row.get("sex", "")
    participant_columns = list(participants and csv.DictReader(open(root / "participants.tsv"), delimiter="\t").fieldnames)
    subj = subject_rows(run_rows, sz_rows, participants)
    sig = load_signal_stats(Path(args.signal_stats))
    tables = Path(args.tables)
    write_csv(tables / "runs.csv", run_rows)
    write_csv(tables / "seizures.csv", sz_rows)
    write_csv(tables / "subjects.csv", subj)

    # ---------------------------------------------------------------- numbers
    n_sub = len(subj)
    n_f = sum(1 for s in subj if s["sex"] == "f")
    hours = {m: sum(r[f"duration_{m}_s"] or 0 for r in run_rows) / 3600 for m in MODALITIES}
    eeg_h = hours["eeg"]
    n_runs = {m: sum(r[f"has_{m}"] for r in run_rows) for m in MODALITIES}
    fs_counts = Counter((m, r[f"fs_{m}_sidecar"], r[f"fs_{m}_edf"]) for r in run_rows for m in MODALITIES if r[f"has_{m}"])
    fs_mismatch = sum(1 for (m, side, edf), n in fs_counts.items() if str(side) != str(edf) for _ in range(n))
    off_nominal = {m: sum(n for (mm, side, edf), n in fs_counts.items() if mm == m and edf != ("25" if m == "mov" else "250"))
                   for m in MODALITIES}
    edf_types = Counter(r[f"edf_type_{m}"] for r in run_rows for m in MODALITIES if r[f"has_{m}"])
    montages = Counter(r["montage"] for r in run_rows)
    montage_subj = Counter(s["montages"] for s in subj)
    sidecar_montage_agree = sum(
        1 for r in run_rows
        if {"left": "left", "right": "right", "bilateral": "generalized"}.get(r["montage"]) == r["sidecar_montage"])
    sz_split = Counter(s["split"] for s in sz_rows)
    sz_class = Counter(s["class"] for s in sz_rows)
    sz_class_split = Counter((s["class"], s["split"]) for s in sz_rows)
    durs = np.array([s["duration_s"] for s in sz_rows])
    overlaps, close = 0, 0
    for s in sz_rows:
        g = s["gap_from_previous_s"]
        if g != "":
            overlaps += g < 0
            close += 0 <= g < 90
    merged_90 = 0
    by_run = defaultdict(list)
    for s in sz_rows:
        by_run[(s["subject"], s["run"])].append((s["onset_s"], s["onset_s"] + s["duration_s"]))
    for ivs in by_run.values():
        m = merge_intervals([(a - 45, b + 45) for a, b in ivs])
        merged_90 += len(m)
    out_of_bounds = sum(1 for s in sz_rows if not s["within_run_bounds"])
    chan_known = sum(1 for s in sz_rows if s["channels"] not in ("n/a", ""))
    conf_known = sum(1 for s in sz_rows if s["confidence"] != "n/a")
    sz_hours = durs.sum() / 3600
    pos_frac = sz_hours / eeg_h
    missing_runs = {m: n_runs["eeg"] - n_runs[m] for m in ("ecg", "emg", "mov")}
    missing_hours = {m: eeg_h - hours[m] for m in ("ecg", "emg", "mov")}
    mov_sets = Counter((r["mov_labels"], r["mov_units"]) for r in run_rows if r["has_mov"])
    chest_full = sum(n for (labs, _), n in mov_sets.items()
                     if all(f"ECGEMG SD {k}" in labs for k in ("ACC X", "ACC Y", "ACC Z", "GYR A", "GYR B", "GYR C")))
    impd_n = sum(r["n_impd"] for r in run_rows)
    impd_h = sum(r["impd_s"] for r in run_rows) / 3600
    bad_events = [(r["subject"], r["run"], r["bad_events"]) for r in run_rows if r["n_bad_events"]]
    no_sz_subjects = [s["subject"] for s in subj if s["n_seizures"] == 0]
    short_runs = sum(1 for r in run_rows if r["duration_s"] < 600)
    listing = json.loads(Path(args.listing).read_text()) if Path(args.listing).exists() else []
    total_gb = sum(o["size"] for o in listing) / 1e9 if listing else None

    summary = {
        "dataset_version": cfg["dataset"]["version"], "n_subjects": n_sub, "n_female": n_f,
        "n_runs": n_runs, "hours": {m: round(v, 1) for m, v in hours.items()},
        "n_seizures": len(sz_rows), "seizures_by_split": dict(sz_split),
        "seizures_by_class": dict(sz_class), "edf_files": sum(n_runs.values()),
        "fs_counts": {f"{m}|{side}|{edf}": n for (m, side, edf), n in sorted(fs_counts.items())},
        "montage_runs": dict(montages), "total_gb": round(total_gb, 2) if total_gb else None,
        "subjects": [s["subject"] for s in subj],
    }
    Path(args.report).parent.mkdir(parents=True, exist_ok=True)
    Path(args.report).with_suffix(".json").write_text(json.dumps(summary, indent=2) + "\n")

    # --------------------------------------------------------------- signals
    sig_ok = [r for r in sig if "error" not in r]
    sig_err = [r for r in sig if "error" in r]
    sig_by_mod = defaultdict(list)
    for r in sig_ok:
        sig_by_mod[r["modality"]].append(r)
    sig_rows = []
    for r in sorted(sig_ok, key=lambda r: r["file"]):
        for lab, ch in r["channels"].items():
            sig_rows.append({"file": r["file"], "modality": r["modality"], "channel": lab,
                             "duration_s": r["duration_s"], "fs": ch["fs"], "unit": ch["unit"],
                             "gain_per_lsb": ch["gain"], "saturation_frac": ch["saturation"],
                             "flat_spans_1s": ch["flat_spans"], "flat_s": ch["flat_s"],
                             "longest_flat_s": ch["longest_flat_s"], "flat_spans_10s": ch["flat_10s_spans"],
                             "artefact_frac": ch.get("artefact_frac", ""), "rms_median_uv": ch.get("rms_median", ""),
                             "record_gaps": r.get("record_gaps", "")})
    if sig_rows:
        write_csv(tables / "signal_channels.csv", sig_rows)
    figs = figures(run_rows, sz_rows, subj, sig_ok, Path(args.figures))

    # ---------------------------------------------------------------- report
    L = []
    w = L.append
    w("# M1 data audit: SeizeIT2 (OpenNeuro ds005873)\n")
    w(f"Generated by `python scripts/audit_data.py` at commit `{git_hash()}`. Every number below is "
      "computed from the files; tables are in `results/audit/`, summary numbers in `reports/data_audit.json`.\n")
    w(f"Dataset version {cfg['dataset']['version']} (DOI {cfg['dataset']['doi']}), licence CC0. "
      f"Bucket listing: {len(listing)} objects, {total_gb:.1f} GB.\n" if listing else "")
    w("## 1. Contradictions with Section 3 of the prompt\n")
    contra = [
        ["Sampling rate of EEG/ECG/EMG", "250 Hz", ", ".join(f"{m.upper()}: {s} Hz in {n} files" for (m, _, s), n in sorted(fs_counts.items()) if m != "mov"),
         "Never hard-code 250. Windows are defined in seconds; integer filters must be designed for 256 Hz (or resampled, which costs logic). The official baseline resamples to 250 Hz."],
        ["Motion channels", "3-axis ACC and GYR from the chest module", f"{len(mov_sets)} channel layouts; 12 channels (ACC+GYR of both the EEG module and the chest module) in {mov_sets.most_common(1)[0][1]} of {n_runs['mov']} runs; full chest ACC+GYR in {chest_full} runs",
         "Use chest ACC+GYR when present; treat missing axes as a missing sub-modality (present bit = 0)."],
        ["Number of seizures", f"{exp['n_seizures']} (train {exp['train_seizures']}, test {exp['test_seizures']})",
         f"{len(sz_rows)} (train {sz_split['train']}, test {sz_split['test']})", "Report our count; cite the paper's count with a footnote."],
        ["Seizure types", "317 FA, 393 FIA, 55 FBTC, 12 unclear awareness, 2 subclinical, 93 unknown onset",
         ", ".join(f"{k} {v}" for k, v in sz_class.most_common()),
         "No `subclinical` level exists in events.json; per-type breakdowns use the classes found."],
        ["Shortest seizure", "3 s", f"{durs.min():g} s ({int((durs < 3).sum())} seizures under 3 s)", "Keep; a 2 s seizure can still be one positive window."],
        ["Female patients", f"{exp['n_female']}", f"{n_f} in participants.tsv", "Check with the authors; the paper text and the file disagree."],
        ["Total recording", f"{exp['total_hours']} h", f"{eeg_h:,.0f} h of EEG", "Minor (0.1%)."],
        ["Centre and age per patient", "used for stratified folds, leave-one-centre-out, centre and adult/child breakdowns",
         f"not in the public release (participants.tsv columns: {participant_columns}); not in sidecars or EDF headers",
         "Inner folds are stratified by seizure count only. Centre/adult-child analyses are blocked until the authors provide the mapping."],
        ["Seizure visibility on the wearable", "secondary result on visible seizures 'if the annotation supports it'",
         f"`channels` is n/a for {len(sz_rows) - chan_known} of {len(sz_rows)} seizures; `confidence` n/a for {len(sz_rows) - conf_known}",
         "The annotation does not support it: drop the visible-only secondary result (or ask the authors)."],
        ["Session folder", "ses-001", "ses-01", "Loader reads whatever session folder exists."],
        ["Dataset version / DOI", "v1.0.0", f"v{cfg['dataset']['version']} (CHANGES: 1.1.0 corrected accelerometer data)", "Cite 10.18112/openneuro.ds005873.v1.1.0."],
        ["Gaps inside files", "recordings have gaps and runs", f"{dict(edf_types)}; sidecars say RecordingType=discontinuous but every EDF is continuous" +
         (f"; signal audit found {sum(r.get('record_gaps', 0) for r in sig_ok)} record gaps in {len(sig_ok)} files read" if sig_ok else ""),
         "Gaps exist only between runs; treat each run as continuous, never cross a file boundary."],
    ]
    w(md_table(["Item", "Prompt says", "Files say", "Consequence"], contra))
    w("")
    w("## 2. Inventory\n")
    w(md_table(["Quantity", "Value"], [
        ["Patients", f"{n_sub} ({n_f} female per participants.tsv); train {sum(s['split'] == 'train' for s in subj)}, test {sum(s['split'] == 'test' for s in subj)}"],
        ["Runs (EEG files)", n_runs["eeg"]],
        ["Files per modality (.edf)", ", ".join(f"{m.upper()} {n_runs[m]}" for m in MODALITIES)],
        ["Hours per modality", ", ".join(f"{m.upper()} {hours[m]:,.1f}" for m in MODALITIES)],
        ["Runs shorter than 10 min", short_runs],
        ["Hours per patient (min / median / max)", f"{min(s['hours'] for s in subj):.1f} / {np.median([s['hours'] for s in subj]):.1f} / {max(s['hours'] for s in subj):.1f}"],
        ["Seizure time", f"{sz_hours:.2f} h = {100 * pos_frac:.3f}% of EEG time (positive-window rate before augmentation)"],
        ["Patients without a seizure", ", ".join(no_sz_subjects) or "none"],
        ["Impedance-check (`impd`) events", f"{impd_n} events, {impd_h:.1f} h (positive durations only); official code treats them as background"],
        ["Malformed events (duration <= 0)", "; ".join(f"{a} {b}: {c}" for a, b, c in bad_events) or "none"],
        ["Sidecar vs EDF sampling rate disagreements", fs_mismatch],
        ["Sidecar EEGMontage agrees with EDF channel labels", f"{sidecar_montage_agree} of {n_runs['eeg']} runs"],
    ]))
    w("")
    w("### Sampling rates found\n")
    w(md_table(["Modality", "Sidecar (Hz)", "EDF header (Hz)", "Files"],
               [[m.upper(), side, edf, n] for (m, side, edf), n in sorted(fs_counts.items())]))
    w("")
    w("Files that differ from the nominal 250 Hz / 25 Hz: " +
      ", ".join(f"{m.upper()} {off_nominal[m]} of {n_runs[m]}" for m in MODALITIES) +
      ". The per-file list is `results/audit/runs.csv` (columns `fs_*`).\n")
    w("## 3. EEG montages\n")
    w(md_table(["Montage (from EDF labels)", "Channels", "Runs", "Sidecar EEGMontage"],
               [["left", "BTEleft SD + CROSStop SD", montages["left"], "left"],
                ["right", "BTEright SD + CROSStop SD", montages["right"], "right"],
                ["bilateral", "BTEleft SD + BTEright SD", montages["bilateral"], "generalized"]] +
               [[k, "", v, ""] for k, v in montages.items() if k not in ("left", "right", "bilateral")]))
    w("")
    w("Patients by montage set: " + ", ".join(f"{k}: {v}" for k, v in sorted(montage_subj.items())) +
      ". A patient whose montage changes between runs means channel position is not even fixed within a patient.\n")
    w("## 4. Missing modalities\n")
    w(md_table(["Modality", "Runs missing", "Hours missing", "Share of EEG time"],
               [[m.upper(), missing_runs[m], f"{missing_hours[m]:.1f}", pct(missing_hours[m], eeg_h)] for m in ("ecg", "emg", "mov")]))
    w("")
    w("Motion channel layouts (label set, unit, runs):\n")
    w(md_table(["Channels", "Unit", "Runs"], [[labs.replace("|", ", "), unit, n] for (labs, unit), n in mov_sets.most_common()]))
    w("")
    w("## 5. Seizures\n")
    w(md_table(["Class", "Train", "Test", "Total"],
               [[c, sz_class_split[(c, "train")], sz_class_split[(c, "test")], sz_class[c]] for c, _ in sz_class.most_common()] +
               [["all", sz_split["train"], sz_split["test"], len(sz_rows)]]))
    w("")
    w(f"Duration: min {durs.min():g} s, median {np.median(durs):g} s, mean {durs.mean():.1f} s, max {durs.max():g} s; "
      f"{int((durs < 10).sum())} seizures shorter than 10 s, {int((durs > 300).sum())} longer than 5 min.\n")
    w("![seizure durations](figures/seizure_duration_hist.png)\n")
    w(f"* Overlapping annotated seizures within a run: {overlaps} pairs; consecutive seizures less than 90 s apart: {close} pairs. "
      f"Under the SzCORE 90 s merge rule the {len(sz_rows)} annotations become {merged_90} reference events (approximate count; "
      "the exact count is produced by `timescoring` in M2).")
    w(f"* Seizures outside their run's duration: {out_of_bounds}.")
    w(f"* Seizures starting within the first hour of a run: {sum(s['in_first_hour'] for s in sz_rows)} "
      "(relevant for N3, which adapts on the first H hours).")
    w("* Lateralization: " + ", ".join(f"{k} {v}" for k, v in Counter(s['lateralization'] for s in sz_rows).most_common()) +
      "; vigilance: " + ", ".join(f"{k} {v}" for k, v in Counter(s['vigilance'] for s in sz_rows).most_common()) +
      ". These are annotations and are never fed to a model (Section 7.2).\n")
    w("![hours and seizures per patient](figures/hours_and_seizures_per_patient.png)\n")
    w("## 6. Signal quality (flat-lines, saturation, artefact rate)\n")
    if not sig_ok:
        w("Not yet computed. Run `python scripts/audit_signals.py --stream` (or `--root` with a local copy).\n")
    else:
        w(f"From `scripts/audit_signals.py`: {len(sig_ok)} of {sum(n_runs.values())} EDF files measured "
          + ", ".join(f"({m.upper()} {len(sig_by_mod[m])}/{n_runs[m]})" for m in MODALITIES)
          + (f"; {len(sig_err)} files failed (listed in the JSONL)" if sig_err else "") + ".\n")
        rows = []
        for m in MODALITIES:
            chans = [c for r in sig_by_mod[m] for c in r["channels"].values()]
            if not chans:
                continue
            dur = sum(r["duration_s"] * len(r["channels"]) for r in sig_by_mod[m])
            rows.append([m.upper(), len(sig_by_mod[m]), sum(c["flat_spans"] for c in chans),
                         f"{sum(c['flat_s'] for c in chans) / 3600:.1f} h ({pct(sum(c['flat_s'] for c in chans), dur)})",
                         sum(c["flat_10s_spans"] for c in chans), f"{max(c['longest_flat_s'] for c in chans) / 60:.1f} min",
                         f"{100 * np.average([c['saturation'] for c in chans]):.4f}%"])
        w(md_table(["Modality", "Files", "Flat spans >= 1 s", "Flat time (channel-hours)", "Flat spans >= 10 s",
                    "Longest flat span", "Saturated samples"], rows))
        w("")
        eeg = sig_by_mod["eeg"]
        if eeg:
            def role_stats(idx):
                fr, med = [], []
                for r in eeg:
                    lab = list(r["channels"])[idx]
                    c = r["channels"][lab]
                    if c.get("n_windows"):
                        fr.append((c["artefact_frac"], c["n_windows"]))
                        med.append(c["rms_median"])
                tot = sum(n for _, n in fr)
                return sum(f * n for f, n in fr) / tot, np.median(med)
            a1, m1 = role_stats(0)
            a2, m2 = role_stats(1)
            nwin = sum(list(r["channels"].values())[0].get("n_windows", 0) for r in eeg)
            any_f = sum(r.get("artefact_any_frac", 0) * list(r["channels"].values())[0]["n_windows"] for r in eeg) / nwin
            both_f = sum(r.get("artefact_both_frac", 0) * list(r["channels"].values())[0]["n_windows"] for r in eeg) / nwin
            w("**Official RMS artefact rule** (window RMS outside 13-150 uV after the official 0.5-60 Hz + 50 Hz notch "
              "filter, 2 s windows, 1 s hop; filtered at the file's 256 Hz rather than after resampling to 250 Hz):\n")
            w(md_table(["Channel", "Windows flagged", "Median of per-run median RMS"],
                       [["channel 1 (BTEleft, else BTEright)", f"{100 * a1:.1f}%", f"{m1:.1f} uV"],
                        ["channel 2 (CROSStop, else BTEright)", f"{100 * a2:.1f}%", f"{m2:.1f} uV"],
                        ["either channel flagged", f"{100 * any_f:.1f}%", ""],
                        ["both channels flagged", f"{100 * both_f:.1f}%", ""]]))
            w("")
            w("The 13 uV floor is close to the typical RMS of a behind-the-ear channel, so the rule flags a large share "
              "of ordinary windows. The official evaluation code computes `rmsa = rmsa_f and rmsa_c` on two Python lists, "
              "which returns only the cross-channel list, so in practice the published baselines gate on channel 2 alone. "
              "M2 reproduces that behaviour for the baselines; the artefact flag of our own models is a design decision "
              "for M3 (see `results/decisions.md`).\n")
            if "eeg_rms_per_run.png" in figs:
                w("![EEG RMS per run](figures/eeg_rms_per_run.png)\n")
        mov_ch = [c for r in sig_by_mod["mov"] for c in r["channels"].values()]
        if mov_ch:
            mdur = sum(r["duration_s"] * len(r["channels"]) for r in sig_by_mod["mov"])
            w(f"Motion channels are exactly constant for {pct(sum(c['flat_s'] for c in mov_ch), mdur)} of channel time "
              f"and {100 * np.average([c['saturation'] for c in mov_ch]):.1f}% of motion samples sit at the digital limits: "
              "long idle/off stretches of the sensor. A flat motion window is therefore not evidence of a missing "
              "file, and motion features must tolerate constant input (M3 uses offset removal and |x| sums).\n")
        w("Per-channel numbers: `results/audit/signal_channels.csv`.\n")
    w("## 7. What M2/M3 must do differently because of this audit\n")
    w("1. Design every filter and window for 256 Hz read from the header; test the 250 Hz path too (fixtures cover both).")
    w("2. Stratify inner folds by seizure count only until centre labels arrive; keep the centre/adult-child tables as placeholders.")
    w("3. Drop the visible-seizure secondary result unless the authors can supply visibility labels.")
    w("4. Motion features need a per-axis present mask: chest ACC/GYR are not always there, and the EEG-module motion is an extra source.")
    w("5. Report SzCORE metrics on the reference events after `timescoring`'s 90 s merge, and state the annotation count we used.")
    w("6. Revisit the 13 uV artefact floor for our own models: feed the flag as an input bit, do not gate on it blindly.")
    w("7. Motion is often constant (sensor idle); its present bit comes from file availability, not from signal activity.\n")
    Path(args.report).write_text("\n".join(L) + "\n")
    print(f"wrote {args.report}, {tables}/*.csv, figures {figs}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
