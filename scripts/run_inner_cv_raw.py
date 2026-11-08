#!/usr/bin/env python3
"""Raw-EEG 1-D CNN and TCN on the inner folds (Tier-1 small neural networks, Section 6.2; GPU laptop).

Training windows come from the ChronoNet cache (scripts/baselines/chrononet_data.py with the config
named in `data.config`: every seizure window of the 96 training patients plus `factor` times as many
background windows, official preprocessing, 2 s x 250 Hz x 2 channels), split by patient with the
fixed inner folds. Each fold trains every model of the config, then streams the held-out patients'
recordings once and scores every 1 s step with all of them (the slow part). The out-of-fold scores
use the same 2 s windows as the feature cache (window t starts at second t), whose artefact flags,
labels and seizures feed the shared operating-point selection (src/eval/innercv.py), so these runs
sit in the same tables as every feature model. Never touches the test patients. Resumable: per
fold, per recording, and per training epoch.

Usage:  python scripts/run_inner_cv_raw.py --config configs/m4/raw_cnn_tcn.yaml --device cuda
Output: one results/runs/<id>/ per model (as run_inner_cv.py) and cache/oof/<id>/
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import torch
import yaml

from seizelut.data.bids import discover_runs
from seizelut.data.edf import read_edf
from seizelut.data.featureset import FeatureStore
from seizelut.data.remote import local_edf
from seizelut.data.split import load_folds
from seizelut.eval.innercv import finalize
from seizelut.eval.runlog import new_run_dir, require_test_access, resolve_subjects
from seizelut.models.baselines import official as off
from seizelut.models.raw import build_raw, macs_per_window

REPO = Path(__file__).resolve().parents[1]


def _resolve(p, base=REPO):
    p = Path(p)
    return p if p.is_absolute() else base / p


def train_net(spec, x, y, idx, tc, seed, dev, ckpt, log):
    """Train one model on the windows `idx` (sorted per batch for memory-mapped reads); per-epoch state
    in `ckpt` so an interrupted fold resumes."""
    torch.manual_seed(seed)
    net = build_raw(spec["type"], **spec.get("params", {})).to(dev)
    rng = np.random.default_rng(seed)
    probe = np.sort(rng.choice(idx, size=min(len(idx), 20_000), replace=False))
    scale = np.maximum(np.asarray(x[probe]).std(axis=(0, 1)), 1e-3).astype(np.float32)   # per channel
    yy = y[idx]
    w = torch.tensor([1.0, float((yy == 0).sum()) / max(1, int((yy == 1).sum()))], device=dev)
    opt = torch.optim.Adam(net.parameters(), lr=tc.get("lr", 1e-3))
    epochs, bs = tc.get("epochs", 30), tc.get("batch", 256)
    sched = torch.optim.lr_scheduler.StepLR(opt, max(1, int(0.7 * epochs)), 0.1)
    start = 0
    if ckpt.exists():
        st = torch.load(ckpt, map_location=dev, weights_only=False)
        net.load_state_dict(st["net"]); opt.load_state_dict(st["opt"]); sched.load_state_dict(st["sched"])
        rng.bit_generator.state = st["rng"]
        start = st["epoch"]
        log(f"    {spec['name']}: resumed after epoch {start}")
    for ep in range(start, epochs):
        net.train()
        perm = rng.permutation(idx)
        tot, t0 = 0.0, time.time()
        for i in range(0, len(perm), bs):
            ids = np.sort(perm[i:i + bs])
            xb = torch.from_numpy(np.asarray(x[ids]) / scale).to(dev)
            yb = torch.from_numpy(y[ids].astype(np.int64)).to(dev)
            loss = torch.nn.functional.cross_entropy(net(xb), yb, weight=w)
            opt.zero_grad()
            loss.backward()
            opt.step()
            tot += float(loss.detach()) * len(ids)
        sched.step()
        log(f"    {spec['name']} epoch {ep + 1}/{epochs} loss {tot / len(perm):.4f} ({time.time() - t0:.0f} s)")
        tmp = Path(str(ckpt) + ".tmp")
        torch.save({"net": net.state_dict(), "opt": opt.state_dict(), "sched": sched.state_dict(),
                    "rng": rng.bit_generator.state, "epoch": ep + 1}, tmp)
        tmp.replace(ckpt)
    return net.eval(), scale


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", required=True)
    ap.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    ap.add_argument("--folds-file", default=str(REPO / "configs/folds_inner5.json"))
    ap.add_argument("--dataset-root", default=None, help="default: configs/dataset.yaml")
    ap.add_argument("--features-root", default=None)
    ap.add_argument("--out", default=None, help="write runs/, oof scores and checkpoints here (tests)")
    ap.add_argument("--batch", type=int, default=2048, help="inference batch")
    args = ap.parse_args()
    cfg = yaml.safe_load(Path(args.config).read_text())
    out = Path(args.out).resolve() if args.out else REPO
    seed = cfg.get("seed", 0)
    dev = torch.device(args.device)
    folds = load_folds(args.folds_file)
    fold_ids = sorted(set(folds.values()))
    require_test_access(sorted(folds), False)
    ds = yaml.safe_load((REPO / "configs/dataset.yaml").read_text())
    root = Path(args.dataset_root) if args.dataset_root else REPO / ds["dataset"]["root"]
    data = _resolve(cfg["data"]["cache_dir"])
    x = np.load(data / "train_x.npy", mmap_mode="r")
    y = np.load(data / "train_y.npy").astype(np.int8)
    keys = np.load(data / "train_keys.npy")
    ccfg = yaml.safe_load(_resolve(cfg["data"]["config"]).read_text())
    runs_all = discover_runs(root, resolve_subjects(ccfg["train_subjects"]))
    seg_subject = np.array([runs_all[int(i)].subject for i in keys[:, 0]])
    store = FeatureStore("int", root=Path(args.features_root) if args.features_root else None)
    tc = cfg.get("train", {})

    models, logs = [], {}
    for spec in cfg["models"]:
        mcfg = {k: v for k, v in cfg.items() if k != "models"} | {"name": spec["name"], "model": spec,
                                                                    "folds_file": Path(args.folds_file).name}
        runs_dir = (out / "results" / "runs") if args.out else REPO / "results" / "runs"
        if any((d / "metrics.json").exists() and not (d / ".gitignore").exists()
               for d in runs_dir.glob(f"*_{spec['name']}_s{seed}")):
            print(f"{spec['name']}: a finished run exists, skipped", flush=True)
            continue
        prev = [d for d in sorted(runs_dir.glob(f"*_{spec['name']}_s{seed}"), reverse=True)
                if (d / ".gitignore").exists() and not (d / "metrics.json").exists()]
        run = prev[0] if prev else new_run_dir(spec["name"], mcfg, seed, root=runs_dir if args.out else None)
        fh = open(run / "log.txt", "a")
        logs[spec["name"]] = fh
        oof_dir = out / "cache" / "oof" / run.name
        oof_dir.mkdir(parents=True, exist_ok=True)
        models.append({"spec": spec, "cfg": mcfg, "run": run, "oof": oof_dir,
                       "ck": out / "checkpoints" / run.name})

    if not models:
        return 0

    def log(msg, name=None):
        print(msg, flush=True)
        for n, fh in logs.items():
            if name is None or n == name:
                fh.write(msg + "\n")
                fh.flush()

    tmp = out / "cache" / "tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    for k in fold_ids:
        va = sorted(s for s, f in folds.items() if f == k)
        todo = [m for m in models if not (m["oof"] / f"_fold_{k}.json").exists()]
        if not todo:
            continue
        t0 = time.time()
        idx = np.flatnonzero(np.isin(seg_subject, [s for s, f in folds.items() if f != k]))
        log(f"fold {k}: {len(idx)} training windows ({int(y[idx].sum())} seizure); val {len(va)} patients")
        nets = {}
        for m in todo:
            m["ck"].mkdir(parents=True, exist_ok=True)
            done_w = m["ck"] / f"fold_{k}.pt"
            if done_w.exists():
                st = torch.load(done_w, map_location=dev, weights_only=False)
                net = build_raw(m["spec"]["type"], **m["spec"].get("params", {})).to(dev)
                net.load_state_dict(st["net"])
                nets[m["spec"]["name"]] = (net.eval(), st["scale"])
                continue
            net, scale = train_net(m["spec"], x, y, idx, tc, seed + k, dev, m["oof"] / f"_fold_{k}_train.pt",
                                   lambda s, n=m["spec"]["name"]: log(s, n))
            torch.save({"net": net.state_dict(), "scale": scale}, done_w)
            (m["oof"] / f"_fold_{k}_train.pt").unlink(missing_ok=True)
            nets[m["spec"]["name"]] = (net, scale)
        vruns = discover_runs(root, va)
        for i, r in enumerate(vruns):
            if all((m["oof"] / f"{r.key}.npy").exists() for m in todo):
                continue
            with local_edf(r, "eeg", tmp) as p:
                chans = off.preprocess_eeg(read_edf(p))
            n = len(off.window_rms(chans[0]))
            starts = np.arange(n, dtype=float)
            with torch.no_grad():
                for m in todo:
                    net, scale = nets[m["spec"]["name"]]
                    s = []
                    for a in range(0, n, args.batch):
                        w = torch.from_numpy(off.cut_windows(chans, starts[a:a + args.batch]) / scale).float().to(dev)
                        o = net(w)
                        s.append((o[:, 1] - o[:, 0]).float().cpu().numpy())
                    np.save(m["oof"] / f"{r.key}.npy", np.concatenate(s).astype(np.float32) if s else np.zeros(0, np.float32))
            log(f"  {i + 1}/{len(vruns)} {r.key}: {n} windows")
        for m in todo:
            net = nets[m["spec"]["name"]][0]
            info = {"fold": k, "train_windows": int(len(idx)), "seconds": round(time.time() - t0, 1),
                    "cost": macs_per_window(net.cpu())}
            net.to(dev)
            (m["oof"] / f"_fold_{k}.json").write_text(json.dumps(info))
            log(f"  fold {k} done ({info['cost']})", m["spec"]["name"])

    for m in models:
        oof, fold_info, costs = [], [], []
        for k in fold_ids:
            info = json.loads((m["oof"] / f"_fold_{k}.json").read_text())
            fold_info.append(info)
            costs.append(info["cost"])
            for r in store.iter_runs(sorted(s for s, f in folds.items() if f == k)):
                s = np.load(m["oof"] / f"{r.subject}_{r.run}.npy")
                n = min(len(s), len(r.y))           # same 2 s windows; lengths can differ by a rounding second
                oof.append({"subject": r.subject, "fold": k, "score": s[:n], "artefact": r.artefact[:n],
                            "seizures": r.seizures, "duration_s": r.duration_s, "y": r.y[:n]})
                r.X = None
        finalize(oof, m["cfg"], seed, fold_ids, folds, 0, fold_info, costs, m["run"],
                 lambda s, n=m["spec"]["name"]: log(s, n))
        log(f"run dir: {m['run']}", m["spec"]["name"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
