"""Export package of a trained LUT-native classifier (Section 8.2).

export/<model_id>/
  thresholds.json  integer thermometer thresholds per feature, only those the network reads,
                   and the ordered list of input bits (feature, threshold) after pruning
  mapping.json     which input bit feeds which input of each LUT, per layer
  luts.json        every LUT's truth table as hex (bit a of the table = output for address a,
                   address bit l = LUT input l), per layer
  head.json        GroupSum groups, decision threshold, artefact gate, k of n post-processing,
                   merge and refractory times
  manifest.json    training run id, git commit, config hash, dataset version, feature spec
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

from ..eval.runlog import git_state
from ..features import spec as S


def pruned_bits(model) -> tuple[list[tuple[int, int]], np.ndarray]:
    """Ordered list of distinct (feature column, threshold) actually read by layer 1, and the
    remap from original encoded-bit index to position in that list (-1 = unread)."""
    th = model.therm.thresholds
    nb = model.therm.num_bits
    mp0 = model.exported["layers"][0]["mapping"]
    used = np.unique(mp0)
    pairs, remap = [], np.full(th.size, -1, dtype=np.int64)
    index = {}
    for b in used:
        f, i = divmod(int(b), nb)
        key = (f, int(th[f, i]))
        if key not in index:
            index[key] = len(pairs)
            pairs.append(key)
        remap[b] = index[key]
    return pairs, remap


def truth_table_hex(table: np.ndarray) -> str:
    v = 0
    for a, bit in enumerate(table.astype(int)):
        v |= int(bit) << a
    return f"{v:0{(len(table) + 3) // 4}x}"


def export_dwn(model, feature_names: list[str], operating_point: dict, out_dir: Path, run_meta: dict) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    pairs, remap = pruned_bits(model)
    layers = model.exported["layers"]
    feat_used = sorted({f for f, _ in pairs})
    thresholds = {feature_names[f]: sorted({t for ff, t in pairs if ff == f}) for f in feat_used}
    (out_dir / "thresholds.json").write_text(json.dumps({
        "features": [{"name": feature_names[f], "column": int(f), "width_bits": S.FEATURE_BITS.get(feature_names[f], 16),
                      "thresholds": thresholds[feature_names[f]]} for f in feat_used],
        "input_bits": [{"bit": i, "feature": feature_names[f], "threshold": int(t)} for i, (f, t) in enumerate(pairs)],
        "rule": "bit = (feature > threshold), signed integer compare"}, indent=1))
    maps = []
    for li, layer in enumerate(layers):
        mp = layer["mapping"].astype(np.int64)
        if li == 0:
            mp = remap[mp]
        maps.append(mp.tolist())
    (out_dir / "mapping.json").write_text(json.dumps({"layers": [{"n_luts": len(m), "n_inputs": len(m[0]),
                                                                    "inputs": m} for m in maps]}))
    (out_dir / "luts.json").write_text(json.dumps({"layers": [[truth_table_hex(t) for t in layer["tables"]]
                                                               for layer in layers]}))
    last = layers[-1]["tables"].shape[0]
    half = (last + 1) // 2
    head = {"groups": {"background": [0, half], "seizure": [half, last]},
            "score": "popcount(seizure group) - popcount(background group)",
            "decision_threshold": int(np.ceil(operating_point["threshold"])),
            "decision": "score >= decision_threshold and artefact gate clear",
            "artefact_gate": operating_point["gate"], "k": int(operating_point["k"]), "n": 10,
            "merge_s": 90, "refractory_s": 0,
            "window_s": 2, "hop_s": 1}
    (out_dir / "head.json").write_text(json.dumps(head, indent=1))
    spec_hash = hashlib.sha256(json.dumps(S.FEATURES).encode() + Path(S.__file__).read_bytes()).hexdigest()[:16]
    manifest = {"model_type": "dwn", "n_input_bits": len(pairs), "luts_per_layer": [len(m) for m in maps],
                "lut_inputs": len(maps[0][0]), "git": git_state(), "feature_spec_sha256_16": spec_hash,
                "dataset": "SeizeIT2 ds005873 v1.1.0", **run_meta}
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=1))
    return out_dir


def load_export(d: Path) -> dict:
    d = Path(d)
    return {k: json.loads((d / f"{k}.json").read_text()) for k in ("thresholds", "mapping", "luts", "head", "manifest")}


def golden_from_export(pkg: dict, X: np.ndarray, artefact: np.ndarray | None = None) -> dict:
    """Bit-exact reference of the exported classifier on feature rows X (columns = original order).
    Returns every stage: input bits, LUT outputs per layer, score, decision, alarm."""
    bits = np.stack([(X[:, b["column"]] > b["threshold"]) for b in _bit_columns(pkg)], axis=1).astype(np.uint8)
    h = bits
    lut_out = []
    for layer, tables in zip(pkg["mapping"]["layers"], pkg["luts"]["layers"]):
        mp = np.array(layer["inputs"])
        tt = np.array([[(int(t, 16) >> a) & 1 for a in range(1 << mp.shape[1])] for t in tables], dtype=np.uint8)
        addr = np.zeros((len(h), mp.shape[0]), dtype=np.int64)
        for lb in range(mp.shape[1]):
            addr |= h[:, mp[:, lb]].astype(np.int64) << lb
        h = tt[np.arange(mp.shape[0])[None, :], addr]
        lut_out.append(h)
    hd = pkg["head"]
    a0, a1 = hd["groups"]["background"]
    b0, b1 = hd["groups"]["seizure"]
    score = h[:, b0:b1].sum(1).astype(np.int64) - h[:, a0:a1].sum(1).astype(np.int64)
    gate = np.zeros(len(score), dtype=bool)
    if artefact is not None and hd["artefact_gate"] != "none":
        gate = (artefact[:, 0] & artefact[:, 1]) if hd["artefact_gate"] == "both" else (artefact[:, 0] | artefact[:, 1])
    decision = (score >= hd["decision_threshold"]) & ~gate
    c = np.concatenate(([0], np.cumsum(decision.astype(np.int64))))
    t = np.arange(1, len(decision) + 1)
    alarm = (c[t] - c[np.maximum(0, t - hd["n"])]) >= hd["k"]
    return {"bits": bits, "lut_out": lut_out, "score": score, "decision": decision.astype(np.uint8),
            "alarm": alarm.astype(np.uint8), "gate": gate.astype(np.uint8)}


def _bit_columns(pkg):
    col = {f["name"]: f["column"] for f in pkg["thresholds"]["features"]}
    return [{"column": col[b["feature"]], "threshold": b["threshold"]} for b in pkg["thresholds"]["input_bits"]]
