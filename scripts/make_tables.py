#!/usr/bin/env python3
"""Build result tables from results/runs/*/metrics.json (inner CV) and final_metrics.json (M6).

  results/tables/inner_cv.md       every inner-CV run: window AUROC/AUPR, SzCORE at both operating
                                   points, estimated hardware cost
  results/tables/inner_cv_tests.md paired Wilcoxon (per patient, event-F1 and FP/24h at best-F1 op)
                                   of each run against a reference run
  paper/tables/inner_cv.tex        LaTeX version of the first table
Usage: python scripts/make_tables.py [--reference lgbm]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import yaml

from seizelut.eval.stats import paired_wilcoxon

REPO = Path(__file__).resolve().parents[1]


def per_subject_f1(op):
    out = {}
    for s, (tp, fp, nref, hours) in op["per_subject"].items():
        se = tp / nref if nref else np.nan
        pr = tp / (tp + fp) if tp + fp else 0.0
        out[s] = (2 * se * pr / (se + pr) if nref and se + pr > 0 else 0.0, 24 * fp / hours if hours else np.nan)
    return out


def load_runs():
    runs = []
    for d in sorted((REPO / "results" / "runs").glob("*")):
        m = d / "metrics.json"
        if d.name.endswith("_invalid"):
            continue
        if m.exists() and "operating_points" in (j := json.loads(m.read_text())):
            if len(j.get("folds", [])) != 5:
                continue
            runs.append((d.name, j))
    return runs


def ablation(latest, out):
    """Section 9.2 table 3: every Tier-2 run against its own base (`base_config` in its config): per-patient
    differences at the best-F1 operating points, bootstrap 95 % interval of the mean, paired Wilcoxon."""
    from seizelut.eval.stats import bootstrap_ci
    rows, tex = [], []
    for cfg, (name, j) in sorted(latest.items()):
        c = yaml.safe_load((REPO / "results" / "runs" / name / "config.yaml").read_text())
        base = c.get("base_config")
        if not base or base not in latest:
            continue
        cur = per_subject_f1(j["operating_points"]["best_f1"])
        ref = per_subject_f1(latest[base][1]["operating_points"]["best_f1"])
        subs = sorted(set(cur) & set(ref))
        df1 = [cur[s][0] - ref[s][0] for s in subs]
        dfp = [cur[s][1] - ref[s][1] for s in subs]
        ci1, cifp = bootstrap_ci(df1), bootstrap_ci(dfp)
        w1 = paired_wilcoxon([cur[s][0] for s in subs], [ref[s][0] for s in subs])
        w2 = paired_wilcoxon([cur[s][1] for s in subs], [ref[s][1] for s in subs])
        lut = j.get("cost_median", {}).get("total_luts")
        blut = latest[base][1].get("cost_median", {}).get("total_luts")
        dl = f"{int(lut - blut):+,}" if lut is not None and blut is not None else "-"
        b, bb = j["operating_points"]["best_f1"], latest[base][1]["operating_points"]["best_f1"]
        rows.append(f"| {cfg} | {base} | {b['f1']:.3f} ({b['f1'] - bb['f1']:+.3f}) | "
                    f"{ci1['estimate']:+.3f} [{ci1['low']:+.3f}, {ci1['high']:+.3f}] | {w1['p']:.3g} | "
                    f"{cifp['estimate']:+.1f} [{cifp['low']:+.1f}, {cifp['high']:+.1f}] | {w2['p']:.3g} | {dl} |")
        tex.append(f"{cfg.replace('_', chr(92) + '_')} & {ci1['estimate']:+.3f} [{ci1['low']:+.3f}, {ci1['high']:+.3f}] & "
                   f"{w1['p']:.2g} & {cifp['estimate']:+.1f} & {w2['p']:.2g} & {dl} \\\\")
    if not rows:
        (out / "m5_ablation.md").unlink(missing_ok=True)
        return
    md = ["# Tier-2 ablations against their own base (inner folds, per patient, best-F1 operating points)\n",
          "Mean per-patient difference with a bootstrap 95 % interval (patients resampled) and the paired "
          "Wilcoxon p-value. A method is kept if p < 0.05 in its favour (Section 6.6).\n",
          "| Config | Base | Event-F1 (diff vs base) | mean dF1 [95 % CI] | p (F1) | mean dFP/24h [95 % CI] | p (FP/24h) | d est. LUTs |",
          "|---|---|---|---|---|---|---|---|"] + rows
    (out / "m5_ablation.md").write_text("\n".join(md) + "\n")
    t = ["\\begin{table}[t]\\centering\\caption{Tier-2 methods against their own baselines (inner folds; mean "
         "per-patient difference, bootstrap 95\\% interval, paired Wilcoxon).}\\label{tab:ablation}",
         "\\resizebox{\\columnwidth}{!}{\\begin{tabular}{lrrrrr}\\toprule",
         "Method & $\\Delta$F1 [95\\% CI] & $p$ & $\\Delta$FP/24h & $p$ & $\\Delta$LUTs \\\\ \\midrule"] + tex + [
         "\\bottomrule\\end{tabular}}\\end{table}"]
    (REPO / "paper" / "tables").mkdir(parents=True, exist_ok=True)
    (REPO / "paper" / "tables" / "m5_ablation.tex").write_text("\n".join(t) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--reference", default="lgbm")
    args = ap.parse_args()
    runs = load_runs()
    if not runs:
        print("no complete inner-CV runs yet")
        out = REPO / "results" / "tables"
        out.mkdir(parents=True, exist_ok=True)
        (out / "inner_cv.md").write_text("# Inner 5-fold CV\n\nNo complete valid inner-CV run yet.\n")
        (out / "inner_cv_tests.md").unlink(missing_ok=True)
        return 0
    latest = {}
    for name, j in runs:
        latest[j["name"]] = (name, j)       # last run of each config wins
    rows = []
    for cfg, (name, j) in sorted(latest.items()):
        b, s = j["operating_points"]["best_f1"], j["operating_points"].get("sens_at_1fah")
        c = j.get("cost_median", {})
        luts = c.get("total_luts", np.nan)
        rows.append([cfg, f"{j['window_auroc']:.3f}", f"{j['window_aupr']:.3f}",
                     f"{b['f1']:.3f}", f"{b['sensitivity']:.3f}", f"{b['precision']:.3f}", f"{b['fp_per_24h']:.1f}",
                     f"{b['gate']}/{b['k']}",
                     f"{s['sensitivity']:.3f} ({s['fp_per_24h']:.1f})" if s else "-",
                     f"{int(luts):,}" if luts == luts else "-",
                     f"{int(c['encoder_comparators']):,}" if "encoder_comparators" in c else (
                         f"{int(c['distinct_comparators']):,}" if "distinct_comparators" in c else "-"),
                     f"{int(c.get('multipliers', 0)):,}", name])
    hdr = ["Config", "AUROC", "AUPR", "Event-F1", "Sens", "Prec", "FP/24h", "gate/k", "Sens @<=1 FA/h (FP/24h)",
           "Est. LUTs", "Comparators", "Multipliers", "Run"]
    md = ["# Inner 5-fold CV on the 96 training patients (SzCORE, mean over patients)\n",
          "Operating points chosen on pooled out-of-fold predictions. Hardware numbers are estimated "
          "(src/hw/cost.py). Generated by `python scripts/make_tables.py`.\n",
          "| " + " | ".join(hdr) + " |", "|" + "---|" * len(hdr)]
    md += ["| " + " | ".join(r) + " |" for r in rows]
    out = REPO / "results" / "tables"
    out.mkdir(parents=True, exist_ok=True)
    (out / "inner_cv.md").write_text("\n".join(md) + "\n")
    if args.reference in latest:
        ref = per_subject_f1(latest[args.reference][1]["operating_points"]["best_f1"])
        t = [f"# Paired Wilcoxon vs `{args.reference}` (per patient, best-F1 operating points)\n",
             "| Config | median dF1 | p (F1) | median dFP/24h | p (FP/24h) |", "|---|---|---|---|---|"]
        for cfg, (name, j) in sorted(latest.items()):
            if cfg == args.reference:
                continue
            cur = per_subject_f1(j["operating_points"]["best_f1"])
            subs = sorted(set(cur) & set(ref))
            w1 = paired_wilcoxon([cur[s][0] for s in subs], [ref[s][0] for s in subs])
            w2 = paired_wilcoxon([cur[s][1] for s in subs], [ref[s][1] for s in subs])
            t.append(f"| {cfg} | {w1['median_diff']:+.3f} | {w1['p']:.3g} | {w2['median_diff']:+.1f} | {w2['p']:.3g} |")
        (out / "inner_cv_tests.md").write_text("\n".join(t) + "\n")
    ablation(latest, out)
    tex = ["\\begin{table}[t]\\centering\\caption{Inner 5-fold cross-validation on the 96 training patients "
           "(SzCORE event metrics, mean over patients; hardware estimated).}\\label{tab:innercv}",
           "\\resizebox{\\columnwidth}{!}{\\begin{tabular}{lrrrrrr}\\toprule",
           "Model & AUROC & F1 & Sens & FP/24h & Est.\\ LUTs & Mult. \\\\ \\midrule"]
    for r in rows:
        tex.append(f"{r[0].replace('_', chr(92) + '_')} & {r[1]} & {r[3]} & {r[4]} & {r[6]} & {r[9]} & {r[11]} \\\\")
    tex += ["\\bottomrule\\end{tabular}}\\end{table}"]
    (REPO / "paper" / "tables").mkdir(parents=True, exist_ok=True)
    (REPO / "paper" / "tables" / "inner_cv.tex").write_text("\n".join(tex) + "\n")
    print("\n".join(md))
    return 0


if __name__ == "__main__":
    sys.exit(main())
