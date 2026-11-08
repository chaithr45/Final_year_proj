"""Small neural networks on raw behind-the-ear EEG (Tier-1 references, Section 6.2): a 1-D CNN and a
TCN on the ChronoNet input (2 s x 250 Hz x 2 channels, the official preprocessing). Both are
multiplier-based; their cost is reported as multiply-accumulates per window and weights.
"""
from __future__ import annotations

import torch
import torch.nn as nn


class CNN1D(nn.Module):
    """Four conv blocks (BN, ReLU, max-pool), global average pool, linear head."""

    def __init__(self, channels=(16, 32, 64, 64), kernels=(7, 7, 5, 3), pools=(4, 4, 2, 1), dropout=0.2):
        super().__init__()
        blocks, c_in = [], 2
        for c, k, p in zip(channels, kernels, pools):
            blocks += [nn.Conv1d(c_in, c, k, padding=k // 2), nn.BatchNorm1d(c), nn.ReLU()]
            if p > 1:
                blocks.append(nn.MaxPool1d(p))
            c_in = c
        self.body = nn.Sequential(*blocks)
        self.drop = nn.Dropout(dropout)
        self.head = nn.Linear(c_in, 2)

    def forward(self, x):                       # x: (B, 500, 2)
        h = self.body(x.transpose(1, 2))
        return self.head(self.drop(h.mean(-1)))


class _TCNBlock(nn.Module):
    def __init__(self, c, dilation, k=3, dropout=0.1):
        super().__init__()
        self.pad = (k - 1) * dilation                     # causal: pad on the left only
        self.c1 = nn.Conv1d(c, c, k, dilation=dilation)
        self.c2 = nn.Conv1d(c, c, k, dilation=dilation)
        self.n1, self.n2 = nn.BatchNorm1d(c), nn.BatchNorm1d(c)
        self.drop = nn.Dropout(dropout)

    def forward(self, x):
        h = self.drop(torch.relu(self.n1(self.c1(nn.functional.pad(x, (self.pad, 0))))))
        h = self.drop(torch.relu(self.n2(self.c2(nn.functional.pad(h, (self.pad, 0))))))
        return torch.relu(x + h)


class TCN(nn.Module):
    """Temporal convolutional network: 2x average pool to 125 Hz, residual causal dilated blocks
    (receptive field about 2 s at the default dilations), average of the last second, linear head."""

    def __init__(self, channels=24, dilations=(1, 2, 4, 8, 16, 32), k=3, dropout=0.1):
        super().__init__()
        self.inp = nn.Sequential(nn.AvgPool1d(2), nn.Conv1d(2, channels, 1))
        self.blocks = nn.Sequential(*[_TCNBlock(channels, d, k, dropout) for d in dilations])
        self.head = nn.Linear(channels, 2)

    def forward(self, x):                       # x: (B, 500, 2)
        h = self.blocks(self.inp(x.transpose(1, 2)))
        return self.head(h[..., -h.shape[-1] // 2:].mean(-1))


ARCH = {"cnn1d": CNN1D, "tcn": TCN}


def build_raw(kind: str, **params) -> nn.Module:
    return ARCH[kind](**params)


def macs_per_window(model: nn.Module, length: int = 500) -> dict:
    """Multiply-accumulates of one window (conv and linear layers), counted with forward hooks."""
    total = [0]

    def hook(m, inp, out):
        if isinstance(m, nn.Conv1d):
            total[0] += out.numel() * (m.in_channels // m.groups) * m.kernel_size[0]
        elif isinstance(m, nn.Linear):
            total[0] += out.numel() * m.in_features

    hs = [m.register_forward_hook(hook) for m in model.modules() if isinstance(m, (nn.Conv1d, nn.Linear))]
    was = model.training
    model.eval()
    with torch.no_grad():
        model(torch.zeros(1, length, 2))
    model.train(was)
    for h in hs:
        h.remove()
    weights = sum(p.numel() for p in model.parameters())
    return {"macs": int(total[0]), "weights": int(weights), "multipliers": int(total[0])}
