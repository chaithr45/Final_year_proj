#!/usr/bin/env python3
"""Fault table for the paper: per fault class, the faults that are observable / decision-relevant / alarm-relevant
on the training data (frozen threshold) and how many of the decision-relevant ones three BIST vector sets detect
(the same sets as scripts/make_fault_figure.py). Output: results/tables/fault_table.json, paper/tables/fault.tex"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("ff", REPO / "scripts/make_fault_figure.py")
ff = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ff)


def main() -> int:
    import sys
    sys.path.insert(0, str(REPO / "hw/kv260/board"))
    from seizelut_model import SeizeLUTModel
    from seizelut.data.featureset import FeatureStore
    from seizelut.data.split import official_train_subjects
    model = SeizeLUTModel(REPO / "hw/kv260/board/model")
    faults = json.loads((REPO / "hw/kv260/board/fault_list.json").read_text())["faults"]
    new = np.load(REPO / "hw/kv260/board/seizelut_bist_vectors.npz")
    n_sel = int(new["n_selected"])
    v = np.load(REPO / "hw/kv260/board/vectors/sub-098_run-03.npz")
    old = v["feats"][69571:69571 + 1024].astype(np.int64)
    store = FeatureStore("int")
    rng = np.random.default_rng(0)
    keys = store.runs_of(official_train_subjects())
    spec_idx = [f["spec_index"] for f in json.loads((REPO / "hw/kv260/board/model/thresholds.json").read_text())["features"]]
    rows = []
    for i in rng.choice(len(keys), 64, replace=False):
        r = store.load_run(keys[i])
        rows.append(r.X[rng.choice(len(r.X), 16, replace=False)][:, spec_idx])
    rnd = np.concatenate(rows).astype(np.int64)
    det = {"consecutive": ff.first_detection(model, old, faults) < len(old),
           "random": ff.first_detection(model, rnd, faults) < len(rnd),
           "selected": ff.first_detection(model, new["feats"][:n_sel].astype(np.int64), faults) < n_sel}
    classes = {"truth-table bit flipped": lambda f: f["kind"] == "tt",
               "comparator output stuck at 0/1": lambda f: f["kind"].startswith("sab"),
               "LUT output stuck at 0/1": lambda f: f["kind"].startswith("sal"),
               "all": lambda f: True}
    out = {}
    for name, sel in classes.items():
        m = np.array([sel(f) for f in faults])
        rel = m & np.array([f["decision_9"] for f in faults])
        out[name] = {"faults": int(m.sum()), "observable": int((m & np.array([f["observable"] for f in faults])).sum()),
                     "decision_relevant": int(rel.sum()),
                     "alarm_relevant": int((m & np.array([f["alarm_9"] for f in faults])).sum()),
                     **{f"detected_{k}": int((d & rel).sum()) for k, d in det.items()}}
    (REPO / "results/tables/fault_table.json").write_text(json.dumps(out, indent=1))
    pct = lambda a, b: f"{100 * a / b:.1f}" if b else "--"
    L = [r"\begin{table}[t]\centering",
         r"\caption{Single faults of the fabric classifier on the 96 training patients (8,714\,h; frozen threshold) and "
         r"the decision-relevant faults detected (\%) by three BIST vector sets: 1,024 consecutive windows of one "
         rf"recording, 1,024 random training windows and the {n_sel} coverage-selected windows.}}\label{{tab:fault}}",
         r"\setlength{\tabcolsep}{2.6pt}\resizebox{\columnwidth}{!}{\begin{tabular}{lrrrrrrr}\toprule",
         r"Fault & All & Obs. & Dec. & Alarm & Consec. & Random & \textbf{Selected} \\ \midrule"]
    for name, o in out.items():
        lab = r"\textbf{all}" if name == "all" else name
        if name == "all":
            L.append(r"\midrule")
        L.append(f"{lab} & {o['faults']:,} & {o['observable']:,} & {o['decision_relevant']:,} & {o['alarm_relevant']:,} & "
                 f"{pct(o['detected_consecutive'], o['decision_relevant'])} & {pct(o['detected_random'], o['decision_relevant'])}"
                 f" & \\textbf{{{pct(o['detected_selected'], o['decision_relevant'])}}} \\\\")
    L += [r"\bottomrule\end{tabular}}\end{table}"]
    (REPO / "paper/tables/fault.tex").write_text("\n".join(L) + "\n")
    print(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
