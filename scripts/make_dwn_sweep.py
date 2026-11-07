#!/usr/bin/env python3
"""Write the Section 6.1 DWN grid as configs/m4/sweep/*.yaml (run them on the GPU).

Grid: LUTs in layer 1 {50, 100, 200, 500, 1000, 2000} x thermometer bits {4, 8, 16} x mapping
{learnable, random}, n = 6, one layer, tau = 1/0.3; plus n in {4, 5}, two layers and
tau in {1/0.1, 1/1} at 500 LUTs / 8 bits. Every config uses MI top-40 features (per fold).
Usage:  python scripts/make_dwn_sweep.py && scripts/run_queue.sh configs/m4/sweep/*.yaml
"""
from pathlib import Path

import yaml

OUT = Path(__file__).resolve().parents[1] / "configs" / "m4" / "sweep"
OUT.mkdir(parents=True, exist_ok=True)
POST = {"k": [4, 6, 8, 10], "gate": ["none", "both", "any"], "n_thresholds": 40}


def write(name, **params):
    base = dict(bits=8, layers=[200], n=6, mapping="learnable", tau=3.3333, epochs=30, lr=0.01, batch=4096,
                decay_at=0.7, loss="ce", device="cuda", threads=8)
    base.update(params)
    cfg = {"name": name, "seed": 0, "model": {"type": "dwn", "params": base}, "features": {"mi_top": 40},
           "train": {"bg_ratio": 20}, "post": POST}
    (OUT / f"{name}.yaml").write_text(yaml.safe_dump(cfg, sort_keys=False))


for L in (50, 100, 200, 500, 1000, 2000):
    for bits in (4, 8, 16):
        for mapping in ("learnable", "random"):
            write(f"dwn_L{L}_b{bits}_{mapping[:5]}", layers=[L], bits=bits, mapping=mapping)
for n in (4, 5):
    write(f"dwn_L500_b8_learn_n{n}", layers=[500], n=n)
write("dwn_L500x100_b8_learn", layers=[500, 100])
for tau, tag in ((10.0, "t10"), (1.0, "t1")):
    write(f"dwn_L500_b8_learn_{tag}", layers=[500], tau=tau)
print(len(list(OUT.glob("*.yaml"))), "configs in", OUT)
