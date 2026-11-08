"""LogicNets-style sparse quantized MLP (Tier-1 LUT-native family, Section 6.2).

After Umuroglu et al. (FPL 2020): every neuron reads a fixed, random set of `fan_in` inputs, and
inputs and activations are quantized to a few bits, so each neuron's whole function (weights, bias,
batch norm and quantizer folded) is a truth table of fan_in x bits_in input bits. With
fan_in x bits_in <= 6 one output bit is one LUT6; no multiplier survives in hardware.

  input  : each feature quantized to `in_bits` bits by training quantiles (2^in_bits - 1 thresholds,
           one comparator each, as in the DWN thermometer)
  hidden : sparse linear (fixed random mask) -> batch norm -> clamp to [0, 1] -> round to `act_bits`
           bits (straight-through gradient)
  output : the last layer's neurons split in two halves; score = sum of the seizure half's codes
           minus the background half's (an integer, like the DWN's popcount difference)
"""
from __future__ import annotations

import math

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


def quant01(x: torch.Tensor, bits: int) -> torch.Tensor:
    """Clamp to [0, 1] and round to 2^bits levels; returns the integer code (0 .. 2^bits - 1)."""
    levels = 2 ** bits - 1
    return _RoundSTE.apply(torch.clamp(x, 0.0, 1.0) * levels)


class SparseLayer(nn.Module):
    def __init__(self, n_in: int, n_out: int, fan_in: int, gen: torch.Generator):
        super().__init__()
        idx = torch.stack([torch.randperm(n_in, generator=gen)[:fan_in] for _ in range(n_out)])
        self.register_buffer("idx", idx)                      # (n_out, fan_in) input indices
        self.w = nn.Parameter(torch.randn(n_out, fan_in, generator=gen) / math.sqrt(fan_in))
        self.b = nn.Parameter(torch.zeros(n_out))
        self.bn = nn.BatchNorm1d(n_out)

    def forward(self, x):                                      # x: (B, n_in) codes scaled to [0, 1]
        z = (x[:, self.idx] * self.w).sum(-1) + self.b
        return self.bn(z) + 0.5                                # centre the [0, 1] quantizer range


class LogicNet(nn.Module):
    def __init__(self, n_in: int, hidden=(128, 64, 32), fan_in=3, act_bits=2, in_bits=2, tau=1.0, seed=0):
        super().__init__()
        g = torch.Generator().manual_seed(seed)
        self.in_bits, self.act_bits, self.tau = in_bits, act_bits, tau
        sizes = [n_in] + list(hidden)
        self.layers = nn.ModuleList(SparseLayer(a, b, min(fan_in, a), g) for a, b in zip(sizes[:-1], sizes[1:]))

    def forward(self, codes):                                  # codes: (B, n_in) integers 0 .. 2^in_bits - 1
        x = codes.float() / (2 ** self.in_bits - 1)
        for layer in self.layers:
            q = quant01(layer(x), self.act_bits)
            x = q / (2 ** self.act_bits - 1)
        h = q.shape[1] // 2
        sz, bg = q[:, :h].sum(1), q[:, h:2 * h].sum(1)
        return torch.stack([bg, sz], 1) / self.tau, sz - bg   # training logits, integer score

    def lut_cost(self) -> dict:
        """Estimated LUT6 count: a neuron with k input bits and m output bits costs m * lut6(k), where
        lut6(k) = 1 for k <= 6, otherwise 2^(k-6) LUTs for the table plus LUT6s used as 4:1 muxes."""
        def lut6(k):
            return 1 if k <= 6 else 2 ** (k - 6) + math.ceil((2 ** (k - 6) - 1) / 3)
        luts, bits_prev = 0, self.in_bits
        for layer in self.layers:
            n_out, fan = layer.idx.shape
            luts += n_out * self.act_bits * lut6(fan * bits_prev)
            bits_prev = self.act_bits
        n_last = self.layers[-1].idx.shape[0]
        out_bits = math.ceil(math.log2((n_last // 2) * (2 ** self.act_bits - 1) + 1)) + 1
        adder = (n_last // 2) * self.act_bits * 2 + out_bits    # two adder trees and the subtraction
        return {"network_luts": int(luts), "adder_luts": int(adder), "neurons": int(sum(l.idx.shape[0] for l in self.layers))}

    def used_inputs(self) -> np.ndarray:
        return np.unique(self.layers[0].idx.numpy())
