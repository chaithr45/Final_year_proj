"""N1: stateful LUT network (Section 6.3).

At second t one LUT layer reads [thermometer bits of x_t, state bits s_{t-1}]. Its first
`n_vote` neurons feed GroupSum (the seizure score); the remaining `n_state` neurons are the
next state s_t, registered in flip-flops (in hardware: S D-flip-flops, no multipliers).
An optional second LUT layer can sit between input and the vote/state split.
Training: truncated backpropagation through time over sequences of consecutive windows,
straight-through estimator on the state bits, EFD gradients inside the LUTs.
"""
from __future__ import annotations

import numpy as np
import torch
import torch.nn as nn

from .dwn import GroupSum, LUTLayer, STEFunction, lut_addresses


class StatefulDWN(nn.Module):
    def __init__(self, n_in: int, n_state: int = 16, n_vote: int = 200, n: int = 6, mapping: str = "learnable",
                 tau: float = 1 / 0.3, hidden: int | None = None, seed: int = 0):
        super().__init__()
        g = torch.Generator().manual_seed(seed)
        torch.manual_seed(seed)
        self.n_state, self.n_vote = n_state, n_vote
        size = n_in + n_state
        self.hidden = LUTLayer(size, hidden, n, mapping, generator=g) if hidden else None
        self.out = LUTLayer(hidden or size, n_vote + n_state, n, "random" if hidden else mapping, generator=g)
        self.head = GroupSum(2, tau)

    def step(self, x_t, s):
        h = torch.cat([x_t, s], dim=1)
        if self.hidden is not None:
            h = self.hidden(h)
        o = self.out(h)
        return self.head(o[:, : self.n_vote]), STEFunction.apply(o[:, self.n_vote:])

    def forward(self, seq, s0=None):
        """seq: (B, T, n_in) bits -> logits (B, T, 2)."""
        B, T, _ = seq.shape
        s = torch.zeros(B, self.n_state, device=seq.device) if s0 is None else s0
        outs = []
        for t in range(T):
            logit, s = self.step(seq[:, t], s)
            outs.append(logit)
        return torch.stack(outs, 1), s

    def export(self) -> dict:
        layers = ([self.hidden] if self.hidden is not None else []) + [self.out]
        return {"n_state": self.n_state, "n_vote": self.n_vote,
                "layers": [{"mapping": m.input_mapping().cpu().numpy().astype(np.int32),
                            "tables": m.truth_tables().cpu().numpy()} for m in layers]}


def stateful_integer_forward(bits_seq: np.ndarray, exported: dict) -> tuple[np.ndarray, np.ndarray]:
    """Hardware model over one recording: bits_seq (T, n_in) uint8 -> scores (T,), states (T, S)."""
    S, V = exported["n_state"], exported["n_vote"]
    T = bits_seq.shape[0]
    s = np.zeros(S, dtype=np.uint8)
    scores = np.zeros(T, dtype=np.int64)
    states = np.zeros((T, S), dtype=np.uint8)
    for t in range(T):
        h = np.concatenate([bits_seq[t], s])
        for layer in exported["layers"]:
            mp, tt = layer["mapping"], layer["tables"]
            addr = np.zeros(mp.shape[0], dtype=np.int64)
            for lb in range(mp.shape[1]):
                addr |= h[mp[:, lb]].astype(np.int64) << lb
            h = tt[np.arange(mp.shape[0]), addr]
        vote = h[:V]
        half = (V + 1) // 2
        scores[t] = int(vote[half:].sum()) - int(vote[:half].sum())
        s = h[V:].astype(np.uint8)
        states[t] = s
    return scores, states


def batched_integer_forward(bits_list: list[np.ndarray], exported: dict) -> list[np.ndarray]:
    """Same as stateful_integer_forward for many recordings at once (stepping time, batching runs)."""
    S, V = exported["n_state"], exported["n_vote"]
    n = len(bits_list)
    T = max(len(b) for b in bits_list)
    lens = np.array([len(b) for b in bits_list])
    s = np.zeros((n, S), dtype=np.uint8)
    out = np.zeros((n, T), dtype=np.int64)
    half = (V + 1) // 2
    idx_layers = [(lay["mapping"], lay["tables"], np.arange(lay["mapping"].shape[0])) for lay in exported["layers"]]
    for t in range(T):
        active = np.flatnonzero(lens > t)
        x = np.stack([bits_list[i][t] for i in active])
        h = np.concatenate([x, s[active]], axis=1)
        for mp, tt, ar in idx_layers:
            addr = np.zeros((len(active), mp.shape[0]), dtype=np.int64)
            for lb in range(mp.shape[1]):
                addr |= h[:, mp[:, lb]].astype(np.int64) << lb
            h = tt[ar[None, :], addr]
        out[active, t] = h[:, half:V].sum(1).astype(np.int64) - h[:, :half].sum(1).astype(np.int64)
        s[active] = h[:, V:]
    return [out[i, :lens[i]] for i in range(n)]
