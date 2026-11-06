"""Differentiable logic-gate network (Petersen et al., NeurIPS 2022), pure PyTorch.

Each neuron reads two fixed random inputs and learns a softmax mixture over the 16 two-input
Boolean functions (real-valued relaxations on [0, 1]); at inference each neuron becomes its
argmax gate, so the network is plain logic. Output: GroupSum over 2 classes, as for DWN.
Hardware estimate: one gate per neuron; a LUT6 absorbs ~2-5 gates after synthesis, so we report
gates and a conservative LUT bound = number of gates (labelled estimated).
"""
from __future__ import annotations

import numpy as np
import torch
import torch.nn as nn

from .dwn import GroupSum


def _ops(a, b):
    ab = a * b
    return torch.stack([
        torch.zeros_like(a), ab, a - ab, a, b - ab, b, a + b - 2 * ab, a + b - ab,
        1 - (a + b - ab), 1 - (a + b - 2 * ab), 1 - b, 1 - b + ab, 1 - a, 1 - a + ab, 1 - ab, torch.ones_like(a),
    ], dim=-1)


def _ops_bool(a, b, op):
    """Exact Boolean version of op index (0..15) for uint8 arrays."""
    table = [lambda a, b: np.zeros_like(a), lambda a, b: a & b, lambda a, b: a & ~b & 1, lambda a, b: a,
             lambda a, b: ~a & b & 1, lambda a, b: b, lambda a, b: a ^ b, lambda a, b: a | b,
             lambda a, b: 1 - (a | b), lambda a, b: 1 - (a ^ b), lambda a, b: 1 - b, lambda a, b: (a | (1 - b)) & 1,
             lambda a, b: 1 - a, lambda a, b: ((1 - a) | b) & 1, lambda a, b: 1 - (a & b), lambda a, b: np.ones_like(a)]
    return table[op](a, b)


class LogicLayer(nn.Module):
    def __init__(self, n_in: int, n_out: int, generator=None):
        super().__init__()
        idx = torch.randperm(2 * n_out, generator=generator) % n_in
        self.register_buffer("a", idx[:n_out])
        self.register_buffer("b", idx[n_out:])
        self.w = nn.Parameter(torch.randn(n_out, 16, generator=generator))

    def forward(self, x):
        if self.training:
            return (_ops(x[:, self.a], x[:, self.b]) * torch.softmax(self.w, -1)).sum(-1)
        ops = self.w.argmax(-1)
        return _ops(x[:, self.a], x[:, self.b]).gather(-1, ops[None, :, None].expand(x.shape[0], -1, 1)).squeeze(-1)


class LGN(nn.Module):
    def __init__(self, n_inputs: int, layers=(1000, 1000), tau: float = 10.0, seed: int = 0):
        super().__init__()
        g = torch.Generator().manual_seed(seed)
        mods, size = [], n_inputs
        for w in layers:
            mods.append(LogicLayer(size, w, g))
            size = w
        self.layers = nn.Sequential(*mods)
        self.head = GroupSum(2, tau)

    def forward(self, x):
        return self.head(self.layers(x))

    def export(self) -> dict:
        return {"layers": [{"a": m.a.cpu().numpy(), "b": m.b.cpu().numpy(),
                            "op": m.w.argmax(-1).cpu().numpy()} for m in self.layers]}

    @property
    def n_gates(self) -> int:
        return sum(m.w.shape[0] for m in self.layers)


def lgn_integer_forward(bits: np.ndarray, exported: dict) -> np.ndarray:
    h = np.asarray(bits, dtype=np.uint8)
    for layer in exported["layers"]:
        a, b, ops = h[:, layer["a"]], h[:, layer["b"]], layer["op"]
        out = np.empty((h.shape[0], len(ops)), dtype=np.uint8)
        for op in np.unique(ops):
            cols = np.flatnonzero(ops == op)
            out[:, cols] = _ops_bool(a[:, cols], b[:, cols], int(op))
        h = out
    half = (h.shape[1] + 1) // 2
    return h[:, half:].sum(1).astype(np.int64) - h[:, :half].sum(1).astype(np.int64)
