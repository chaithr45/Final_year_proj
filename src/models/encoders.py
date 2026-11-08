"""Thermometer encoders for N2 (hardware-aware encoding, Section 6.3).

All encoders output bits x_f > t_{f,i}; in hardware each distinct threshold is one comparator.
  uniform      : equally spaced between the training min and max (torch_dwn.Thermometer)
  distributive : training quantiles (torch_dwn.DistributiveThermometer)  [default]
  gaussian     : mean + std * normal quantiles (torch_dwn.GaussianThermometer)
  learned      : thresholds trained jointly with the DWN (sigmoid relaxation, straight-through
                 forward) with a gate per threshold and an L1 penalty on open gates, so the
                 optimiser trades comparators for accuracy; thresholds are rounded to integers.
"""
from __future__ import annotations

import numpy as np
import torch
import torch.nn as nn

from .dwn import DistributiveThermometer


class UniformThermometer(DistributiveThermometer):
    def fit(self, x):
        x = np.asarray(x, dtype=np.float64)
        lo, hi = x.min(0), x.max(0)
        steps = np.arange(1, self.num_bits + 1) / (self.num_bits + 1)
        self.thresholds = np.floor(lo[:, None] + (hi - lo)[:, None] * steps[None, :])
        return self


class GaussianThermometer(DistributiveThermometer):
    def fit(self, x):
        from scipy.stats import norm
        x = np.asarray(x, dtype=np.float64)
        z = norm.ppf(np.arange(1, self.num_bits + 1) / (self.num_bits + 1))
        self.thresholds = np.floor(x.mean(0)[:, None] + x.std(0)[:, None] * z[None, :])
        return self


def make_encoder(kind: str, bits: int):
    return {"distributive": DistributiveThermometer, "uniform": UniformThermometer,
            "gaussian": GaussianThermometer}[kind](bits)


class _HardSigmoidSTE(torch.autograd.Function):
    """forward: (z > 0); backward: derivative of sigmoid(z)."""

    @staticmethod
    def forward(ctx, z):
        ctx.save_for_backward(z)
        return (z > 0).float()

    @staticmethod
    def backward(ctx, g):
        (z,) = ctx.saved_tensors
        s = torch.sigmoid(z)
        return g * s * (1 - s)


class LearnedThermometer(nn.Module):
    """Trainable thresholds (initialised at training quantiles) with per-threshold gates."""

    def __init__(self, init: DistributiveThermometer, x_scale: np.ndarray, gate_init: float = 3.0):
        super().__init__()
        self.t = nn.Parameter(torch.tensor(init.thresholds, dtype=torch.float32))
        self.scale = torch.tensor(np.maximum(x_scale, 1.0), dtype=torch.float32)[:, None]
        self.gate = nn.Parameter(torch.full_like(self.t, gate_init))
        self.num_bits = init.num_bits

    def forward(self, x):
        z = (x.unsqueeze(-1) - self.t.unsqueeze(0)) / self.scale.unsqueeze(0)
        bits = _HardSigmoidSTE.apply(z)
        g = _HardSigmoidSTE.apply(self.gate)            # closed gate -> constant 0 bit (no comparator)
        return (bits * g.unsqueeze(0)).flatten(1)

    def penalty(self):
        return torch.sigmoid(self.gate).sum()

    def freeze(self) -> DistributiveThermometer:
        """Integer thresholds; closed gates become +inf (bit always 0)."""
        th = DistributiveThermometer(self.num_bits)
        t = torch.round(self.t.detach()).numpy().astype(np.float64)
        t[(self.gate.detach() <= 0).numpy()] = np.inf
        th.thresholds = t
        return th
