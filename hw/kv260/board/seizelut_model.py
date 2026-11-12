"""Software reference of the LUT-native classifier (numpy only), read from the exported model files in model/.

Same arithmetic as the RTL: bit_i = feature > threshold (signed integers), 50 six-input truth tables,
score = popcount(seizure group) - popcount(background group), decision = score >= threshold (artefact gate),
alarm = at least k of the last n decisions, starting from a reset (no earlier decisions).
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np


class SeizeLUTModel:
    def __init__(self, model_dir: str | Path):
        d = Path(model_dir)
        self.thresholds = json.loads((d / "thresholds.json").read_text())
        self.mapping = json.loads((d / "mapping.json").read_text())
        self.luts = json.loads((d / "luts.json").read_text())
        self.head = json.loads((d / "head.json").read_text())
        # features arrive in register order (thresholds.json "features" order), not the model's input columns
        col = {f["name"]: i for i, f in enumerate(self.thresholds["features"])}
        self.bit_col = np.array([col[b["feature"]] for b in self.thresholds["input_bits"]])
        self.bit_thr = np.array([b["threshold"] for b in self.thresholds["input_bits"]], dtype=np.int64)
        self.layers = []
        for layer, tables in zip(self.mapping["layers"], self.luts["layers"]):
            mp = np.array(layer["inputs"], dtype=np.int64)
            tt = np.array([[(int(t, 16) >> a) & 1 for a in range(1 << mp.shape[1])] for t in tables], dtype=np.uint8)
            self.layers.append((mp, tt))

    def forward(self, feats: np.ndarray, fault: dict | None = None) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """(n, n_features) integer features in register order -> comparator bits (n, n_bits), outputs of the last
        LUT layer (n, n_luts) and scores (n,); the bits and LUT outputs are what the core's debug taps show.
        fault (as the core's fault-injection registers, one LUT layer): {"b0": [...], "b1": [...]} comparator
        outputs stuck at 0 / 1, {"l0": [...], "l1": [...]} LUT outputs stuck at 0 / 1, {"tt": [...], "addr": a}
        truth-table entry a of these LUTs flipped (lists of indices)."""
        bits = (feats.astype(np.int64)[:, self.bit_col] > self.bit_thr).astype(np.uint8)
        fault = fault or {}
        if fault.get("b0"):
            bits[:, list(fault["b0"])] = 0
        if fault.get("b1"):
            bits[:, list(fault["b1"])] = 1
        h = bits
        for li, (mp, tt) in enumerate(self.layers):
            addr = np.zeros((len(h), mp.shape[0]), dtype=np.int64)
            for lb in range(mp.shape[1]):
                addr |= h[:, mp[:, lb]].astype(np.int64) << lb
            h = tt[np.arange(mp.shape[0])[None, :], addr].copy()
            if li == len(self.layers) - 1 and fault:
                for j in fault.get("tt") or []:
                    h[:, j] ^= (addr[:, j] == int(fault.get("addr", 0))).astype(h.dtype)
                if fault.get("l0"):
                    h[:, list(fault["l0"])] = 0
                if fault.get("l1"):
                    h[:, list(fault["l1"])] = 1
        a0, a1 = self.head["groups"]["background"]
        b0, b1 = self.head["groups"]["seizure"]
        return bits, h, h[:, b0:b1].sum(1).astype(np.int64) - h[:, a0:a1].sum(1).astype(np.int64)

    def bist(self, feats: np.ndarray, art: np.ndarray, golden: dict, fault: dict | None = None) -> tuple[int, int]:
        """What the on-chip self-test reports for these vectors with this fault: (mismatches, first mismatch index or
        -1). Compares score, decision and alarm (alarm from a reset at the first vector) with the golden outputs."""
        s = self.forward(feats, fault)[2]
        dec = s >= int(self.head["decision_threshold"])
        if self.head.get("artefact_gate", "none") != "none":
            a = art.astype(bool)
            g = (a[:, 0] & a[:, 1]) if self.head["artefact_gate"] == "both" else (a[:, 0] | a[:, 1])
            dec &= ~g
        c = np.concatenate(([0], np.cumsum(dec.astype(np.int64))))
        t = np.arange(1, len(dec) + 1)
        alarm = (c[t] - c[np.maximum(0, t - int(self.head["n"]))]) >= int(self.head["k"])
        bad = (s != golden["score"]) | (dec != golden["decision"].astype(bool)) | (alarm != golden["alarm"].astype(bool))
        idx = np.nonzero(bad)[0]
        return int(len(idx)), int(idx[0]) if len(idx) else -1

    def score(self, feats: np.ndarray) -> np.ndarray:
        """(n, n_features) integer features in register order -> (n,) integer scores."""
        return self.forward(feats)[2]

    def run(self, feats: np.ndarray, art: np.ndarray | None = None, threshold: int | None = None,
            k: int | None = None) -> dict:
        """Score, decision and alarm of a whole recording, from reset. threshold/k override the frozen operating
        point (as the core's programmable path does; that path ignores the artefact gate)."""
        hd = dict(self.head)
        if threshold is not None:
            hd["decision_threshold"], hd["artefact_gate"] = int(threshold), "none"
        if k is not None:
            hd["k"] = int(k)
        s = self.score(feats)
        gate = np.zeros(len(s), dtype=bool)
        if art is not None and hd["artefact_gate"] != "none":
            a = art.astype(bool)
            gate = (a[:, 0] & a[:, 1]) if hd["artefact_gate"] == "both" else (a[:, 0] | a[:, 1])
        dec = (s >= hd["decision_threshold"]) & ~gate
        c = np.concatenate(([0], np.cumsum(dec.astype(np.int64))))
        t = np.arange(1, len(dec) + 1)
        alarm = (c[t] - c[np.maximum(0, t - hd["n"])]) >= hd["k"]
        return {"score": s, "decision": dec.astype(np.uint8), "alarm": alarm.astype(np.uint8)}
