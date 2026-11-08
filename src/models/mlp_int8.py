"""INT8 quantisation-aware MLP: the multiplier-based reference (Section 6.2).

Weights: symmetric per-layer int8 (scale = max|w| / 127). Activations: unsigned 8-bit after
ReLU with a learned clip (PACT-style), straight-through estimator for rounding. Inputs are the
integer features standardised with training-set statistics. Exports integer weights, biases
and scales for Phase 2 (hls4ml).
"""
from __future__ import annotations

import numpy as np
import torch
import torch.nn as nn


class _RoundSTE(torch.autograd.Function):
    @staticmethod
    def forward(ctx, x):
        return torch.round(x)

    @staticmethod
    def backward(ctx, g):
        return g


def fake_quant_weight(w, bits=8):
    q = (1 << (bits - 1)) - 1
    s = w.detach().abs().max().clamp_min(1e-8) / q
    return _RoundSTE.apply(w / s).clamp(-q, q) * s


class QLinear(nn.Linear):
    def forward(self, x):
        return nn.functional.linear(x, fake_quant_weight(self.weight), self.bias)


class QReLU(nn.Module):
    """ReLU clipped at a learned alpha, quantised to 8 unsigned bits."""

    def __init__(self, alpha=6.0, bits=8):
        super().__init__()
        self.alpha = nn.Parameter(torch.tensor(float(alpha)))
        self.levels = (1 << bits) - 1

    def forward(self, x):
        y = torch.minimum(torch.relu(x), self.alpha)
        s = self.alpha / self.levels
        return _RoundSTE.apply(y / s) * s


class Int8MLP(nn.Module):
    def __init__(self, n_in, hidden=(64, 32)):
        super().__init__()
        layers, size = [], n_in
        for h in hidden:
            layers += [QLinear(size, h), QReLU()]
            size = h
        layers.append(QLinear(size, 2))
        self.net = nn.Sequential(*layers)
        self.sizes = [n_in, *hidden, 2]

    def forward(self, x):
        return self.net(x)

    def export(self) -> dict:
        out = []
        for m in self.net:
            if isinstance(m, QLinear):
                q = 127
                s = float(m.weight.detach().abs().max() / q)
                out.append({"type": "dense", "w_int8": torch.round(m.weight.detach() / s).clamp(-q, q).to(torch.int8).numpy(),
                            "w_scale": s, "bias": m.bias.detach().numpy()})
            else:
                out.append({"type": "qrelu", "alpha": float(m.alpha.detach()), "bits": 8})
        return {"layers": out, "sizes": self.sizes}
