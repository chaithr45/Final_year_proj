#!/usr/bin/env python3
"""Train the ChronoNet baseline on the windows cut by chrononet_data.py.

Usage:  python scripts/baselines/chrononet_train.py --config configs/baselines/chrononet_official.yaml [--device cuda]
Writes results/runs/<id>/ (config, git state, history.csv, selected epoch) and the weights to
checkpoints/<id>.pt (not committed).
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import sys
import time
from pathlib import Path

import numpy as np
import torch
import yaml

from seizelut.eval.runlog import log_test_access, new_run_dir
from seizelut.models.baselines.chrononet import ChronoNet, decay_schedule, val_score, weighted_focal_loss

REPO = Path(__file__).resolve().parents[2]


def seed_all(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.use_deterministic_algorithms(False)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", required=True)
    ap.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    ap.add_argument("--seed", type=int, default=None)
    args = ap.parse_args()
    cfg = yaml.safe_load(Path(args.config).read_text())
    seed = args.seed if args.seed is not None else cfg["seed"]
    seed_all(seed)
    tc = cfg["train"]
    cache = REPO / cfg["data"]["cache_dir"]
    x = np.load(cache / "train_x.npy", mmap_mode="r")
    y = np.load(cache / "train_y.npy")
    run = new_run_dir(cfg["name"], cfg, seed)
    print(f"run dir {run}; {len(y)} windows ({int(y.sum())} seizure); device {args.device}", flush=True)

    sel = None
    if tc["selection"] == "official_test":
        log_test_access(run, "epoch selection on official validation(=test) patients, as in the published code")
        sel = (torch.from_numpy(np.load(cache / "sel_x.npy")), torch.from_numpy(np.load(cache / "sel_y.npy")),
               np.load(cache / "sel_block.npy"))

    dev = torch.device(args.device)
    model = ChronoNet(cnn_drop=tc["cnn_dropout"], l2=tc["l2"]).to(dev)
    opt = torch.optim.Adam(model.parameters(), lr=tc["lr"], betas=(0.9, 0.999), eps=1e-7)
    lr = tc["lr"]
    bs = tc["batch_size"]
    ckpt_dir = REPO / "checkpoints" / run.name
    ckpt_dir.mkdir(parents=True, exist_ok=True)
    hist = []
    rng = np.random.default_rng(seed)
    for epoch in range(tc["epochs"]):
        lr = decay_schedule(epoch, lr)
        for g in opt.param_groups:
            g["lr"] = lr
        model.train()
        order = rng.permutation(len(y))
        t0, tot, nb = time.time(), 0.0, 0
        for b in range(len(order) // bs):          # Keras Sequence drops the last partial batch
            idx = np.sort(order[b * bs:(b + 1) * bs])
            xb = torch.from_numpy(np.asarray(x[idx])).to(dev)
            yb = torch.from_numpy(y[idx]).to(dev)
            loss = weighted_focal_loss(model(xb), yb) + model.l2_penalty()
            opt.zero_grad()
            loss.backward()
            opt.step()
            tot += float(loss.detach())
            nb += 1
        row = {"epoch": epoch + 1, "lr": lr, "loss": tot / max(nb, 1), "seconds": round(time.time() - t0, 1)}
        if sel is not None:
            model.eval()
            scores = []
            with torch.no_grad():
                for blk in np.unique(sel[2]):
                    m = sel[2] == blk
                    p = torch.cat([model(sel[0][m][i:i + 1024].to(dev)).cpu() for i in range(0, int(m.sum()), 1024)])
                    scores.append(val_score(p, sel[1][m]))
            row["val_score"] = float(np.nanmean(scores))
        hist.append(row)
        torch.save(model.state_dict(), ckpt_dir / f"epoch_{epoch + 1:03d}.pt")
        print(json.dumps(row), flush=True)
        with open(run / "history.csv", "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(hist[-1]))
            w.writeheader()
            w.writerows(hist)

    best = int(np.nanargmax([h["val_score"] for h in hist])) + 1 if sel is not None else len(hist)
    final = REPO / "checkpoints" / f"{run.name}.pt"
    final.write_bytes((ckpt_dir / f"epoch_{best:03d}.pt").read_bytes())
    (run / "selected_epoch.json").write_text(json.dumps({"epoch": best, "rule": tc["selection"],
                                                         "weights": str(final.relative_to(REPO))}, indent=2) + "\n")
    print(f"selected epoch {best} -> {final}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
