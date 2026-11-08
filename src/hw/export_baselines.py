"""Export of the two baselines Phase 2 compares against in hardware (Section 8.2): the INT8 MLP and
TreeLUT. Each package holds everything needed to recompute the model's output from integers alone;
reference functions here recompute it from the package (tests check them against the trained model).

export/<model_id>/
  mlp_int8.json   input standardisation (mean, std per feature), per layer int8 weights, weight scale,
                  float bias, clipped-ReLU alpha and 8-bit activation grid; score = logit1 - logit0
  mlp_float.pt    the same network as a plain torch.nn.Sequential (Linear / ReLU) with dequantised
                  weights, which hls4ml's PyTorch front end reads; the alphas are in mlp_int8.json
  treelut.json    input quantisation (min, scale, w_feature bits per feature), every tree as integer
                  split / leaf nodes, leaf scale and offset; integer decision threshold
  head.json       artefact gate, k of n, merge and refractory times; manifest.json as for the DWN
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from ..eval.runlog import git_state


def _head(op, threshold_int=None):
    h = {"artefact_gate": op["gate"], "k": int(op["k"]), "n": 10, "merge_s": 90, "refractory_s": 0,
         "window_s": 2, "hop_s": 1, "decision_threshold": float(op["threshold"])}
    if threshold_int is not None:
        h["decision_threshold_int"] = int(threshold_int)
    return h


def export_mlp_int8(model, feature_names, op, out_dir, meta) -> Path:
    import torch
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    ex = model.net.export()
    layers = []
    for lyr in ex["layers"]:
        if lyr["type"] == "dense":
            layers.append({"type": "dense", "w_int8": lyr["w_int8"].astype(int).tolist(), "w_scale": lyr["w_scale"],
                           "bias": lyr["bias"].astype(float).tolist()})
        else:
            layers.append(lyr)
    (out / "mlp_int8.json").write_text(json.dumps({
        "features": list(feature_names), "input_mean": model.mu.astype(float).tolist(),
        "input_std": model.sd.astype(float).tolist(), "layers": layers, "sizes": ex["sizes"],
        "score": "logit[1] - logit[0]"}))
    seq = []
    for lyr in ex["layers"]:
        if lyr["type"] == "dense":
            w = torch.tensor(lyr["w_int8"].astype(np.float32) * lyr["w_scale"])
            lin = torch.nn.Linear(w.shape[1], w.shape[0])
            lin.weight.data, lin.bias.data = w, torch.tensor(lyr["bias"].astype(np.float32))
            seq.append(lin)
        else:
            seq.append(torch.nn.ReLU())
    torch.save(torch.nn.Sequential(*seq), out / "mlp_float.pt")
    (out / "head.json").write_text(json.dumps(_head(op), indent=1))
    (out / "manifest.json").write_text(json.dumps({"model_type": "mlp_int8", "git": git_state(), **meta}, indent=1, default=str))
    return out


def mlp_from_export(pkg_dir, X) -> np.ndarray:
    """Recompute the INT8 MLP score from mlp_int8.json alone."""
    p = json.loads((Path(pkg_dir) / "mlp_int8.json").read_text())
    h = (X.astype(np.float32) - np.array(p["input_mean"], np.float32)) / np.array(p["input_std"], np.float32)
    for lyr in p["layers"]:
        if lyr["type"] == "dense":
            h = h @ (np.array(lyr["w_int8"], np.float32) * np.float32(lyr["w_scale"])).T + np.array(lyr["bias"], np.float32)
        else:
            s = np.float32(lyr["alpha"]) / np.float32((1 << lyr["bits"]) - 1)
            h = np.round(np.minimum(np.maximum(h, 0), np.float32(lyr["alpha"])) / s) * s
    return (h[:, 1] - h[:, 0]).astype(np.float32)


def export_treelut(model, feature_names, op, out_dir, meta) -> Path:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    trees = []
    for nodes in model.trees:
        t = {}
        for nid, nd in nodes.items():
            t[str(nid)] = ({"leaf": nd[1]} if nd[0] == "leaf" else
                           {"feature": int(nd[1]), "lt_threshold": int(nd[2]), "yes": int(nd[3]), "no": int(nd[4])})
        trees.append(t)
    (out / "treelut.json").write_text(json.dumps({
        "features": list(feature_names), "w_feature": model.wf, "w_tree": model.wt,
        "input_min": model.lo.astype(float).tolist(), "input_scale": model.scale.astype(float).tolist(),
        "quantise": "q = clip(floor((x - min) * scale), 0, 2^w_feature - 1)",
        "node_rule": "go to 'yes' if q[feature] < lt_threshold, else 'no'; start at node 0",
        "leaf_scale": float(model.leaf_scale), "offset": float(model.offset),
        "score_int": "sum of the reached leaves", "trees": trees}))
    (out / "head.json").write_text(json.dumps(_head(op, model.int_threshold(op["threshold"])), indent=1))
    (out / "manifest.json").write_text(json.dumps({"model_type": "treelut", "git": git_state(), **meta}, indent=1, default=str))
    return out


def treelut_from_export(pkg_dir, X) -> np.ndarray:
    """Recompute TreeLUT's integer score from treelut.json alone."""
    p = json.loads((Path(pkg_dir) / "treelut.json").read_text())
    q = np.clip(np.floor((X.astype(np.float64) - np.array(p["input_min"])) * np.array(p["input_scale"])),
                0, (1 << p["w_feature"]) - 1).astype(np.int64)
    total = np.zeros(len(q), dtype=np.int64)
    for t in p["trees"]:
        for i in range(len(q)):
            nd = t["0"]
            while "leaf" not in nd:
                nd = t[str(nd["yes"] if q[i, nd["feature"]] < nd["lt_threshold"] else nd["no"])]
            total[i] += nd["leaf"]
    return total
