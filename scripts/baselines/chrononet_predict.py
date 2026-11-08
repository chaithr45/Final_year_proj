#!/usr/bin/env python3
"""Per-second ChronoNet probabilities for every recording of the evaluation subjects.

Each recording is pre-processed like the official code, cut into 2 s windows with a
1 s hop, and scored. The window RMS of both channels (official 13-150 uV rule) is
stored too, so evaluation can apply the published or the corrected gate.

Usage:  python scripts/baselines/chrononet_predict.py --run results/runs/<id> [--final-test] [--device cuda]
Output: cache/predictions/<run id>/<sub>_<run>.npz  (y_pred, y_true, rms1, rms2)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import torch
import yaml

from seizelut.data.bids import discover_runs
from seizelut.data.edf import read_edf
from seizelut.data.remote import local_edf
from seizelut.eval.runlog import log_test_access, require_test_access, resolve_subjects, touches_test
from seizelut.models.baselines import official as off
from seizelut.models.baselines.chrononet import ChronoNet

REPO = Path(__file__).resolve().parents[2]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", required=True)
    ap.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    ap.add_argument("--final-test", action="store_true")
    ap.add_argument("--batch", type=int, default=2048)
    args = ap.parse_args()
    run = Path(args.run)
    cfg = yaml.safe_load((run / "config.yaml").read_text())
    subjects = resolve_subjects(cfg["eval"]["subjects"])
    require_test_access(subjects, args.final_test)
    if touches_test(subjects):
        log_test_access(run, "ChronoNet predictions on test patients")
    sel = yaml.safe_load((run / "selected_epoch.json").read_text())
    dev = torch.device(args.device)
    model = ChronoNet(cnn_drop=cfg["train"]["cnn_dropout"], l2=cfg["train"]["l2"]).to(dev)
    model.load_state_dict(torch.load(REPO / sel["weights"], map_location=dev))
    model.eval()

    ds = yaml.safe_load((REPO / "configs/dataset.yaml").read_text())
    out = REPO / "cache" / "predictions" / run.name
    out.mkdir(parents=True, exist_ok=True)
    tmp = REPO / "cache" / "tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    runs = discover_runs(REPO / ds["dataset"]["root"], subjects)
    for i, r in enumerate(runs):
        dest = out / f"{r.key}.npz"
        if dest.exists():
            continue
        with local_edf(r, "eeg", tmp) as p:
            chans = off.preprocess_eeg(read_edf(p))
        rms1, rms2 = off.window_rms(chans[0]), off.window_rms(chans[1])
        n = len(rms1)
        starts = np.arange(n, dtype=float)
        probs = []
        with torch.no_grad():
            for a in range(0, n, args.batch):
                w = torch.from_numpy(off.cut_windows(chans, starts[a:a + args.batch])).to(dev)
                probs.append(model(w)[:, 1].float().cpu().numpy())
        y_pred = np.concatenate(probs) if probs else np.zeros(0)
        ann = r.read_annotations()
        y_true = off.sequential_labels(n, ann.seizure_intervals())
        np.savez_compressed(dest, y_pred=y_pred.astype(np.float32), y_true=y_true, rms1=rms1.astype(np.float32),
                            rms2=rms2.astype(np.float32), duration_s=ann.recording_duration)
        print(f"  {i + 1}/{len(runs)} {r.key}: {n} windows", flush=True)
    print(f"predictions in {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
