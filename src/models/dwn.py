"""Differentiable Weightless Neural Network (Bacellar et al., ICML 2024), pure PyTorch.

A re-implementation of the `torch-dwn` 1.1.1 operators so DWNs train on CPU and on any
GPU without compiling CUDA code (the library's EFD operator is CUDA-only). It follows the
library's CUDA kernel exactly:

* forward: each LUT neuron reads n input bits (x > 0) through `mapping` and outputs
  luts[j, address];
* backward (Extended Finite Difference): dL/dluts[j, a] = sum of output grads hitting a;
  dL/dx for bit l of neuron j = sum_a2 luts[j, a2] * alpha * beta^H(a\\l, a2\\l) * (+1 if
  bit l of a2 else -1), with H the Hamming distance ignoring bit l;
* STE between layers; GroupSum(k, tau) sums contiguous groups;
* learnable mapping: argmax over a weight matrix, gradients as in torch-dwn.

tests/test_dwn.py checks forward/backward against a literal port of the CUDA kernel.
The deployed classifier is integer: score = popcount(seizure group) - popcount(background group).
"""
from __future__ import annotations

import numpy as np
import torch
import torch.nn as nn


# ----------------------------------------------------------------- thermometer encoders

class DistributiveThermometer:
    """Quantile thresholds per feature (torch_dwn.DistributiveThermometer), fitted on training data.
    Encoding: bit i of feature f = x_f > t_{f,i}. Thresholds stay in the feature's integer units."""

    def __init__(self, num_bits: int):
        self.num_bits = int(num_bits)
        self.thresholds: np.ndarray | None = None    # (n_features, num_bits)

    def fit(self, x: np.ndarray) -> "DistributiveThermometer":
        x = np.sort(np.asarray(x), axis=0)
        idx = [int(x.shape[0] * i / (self.num_bits + 1)) for i in range(1, self.num_bits + 1)]
        self.thresholds = x[idx].T.copy()
        return self

    def encode(self, x) -> torch.Tensor:
        x = torch.as_tensor(np.asarray(x, dtype=np.float32))
        t = torch.as_tensor(self.thresholds, dtype=torch.float32)
        return (x.unsqueeze(-1) > t.unsqueeze(0)).flatten(1).float()

    @property
    def n_bits(self) -> int:
        return int(self.thresholds.size)

    def distinct_comparators(self, used: np.ndarray | None = None) -> int:
        """Comparators needed in hardware: distinct thresholds per feature, optionally only for
        bits the network reads (`used`: boolean mask over encoded bits)."""
        t = self.thresholds
        mask = np.ones_like(t, dtype=bool) if used is None else used.reshape(t.shape)
        return int(sum(len(np.unique(t[f][mask[f] & np.isfinite(t[f])])) for f in range(t.shape[0])))


# ----------------------------------------------------------------- EFD operator

_K_CACHE: dict = {}


def _efd_kernel(n: int, alpha: float, beta: float, device) -> torch.Tensor:
    """K[l, a, a2] = alpha * beta^popcount((a ^ a2) & ~(1<<l)) * (+1 if a2 has bit l else -1)."""
    key = (n, float(alpha), float(beta), str(device))
    if key not in _K_CACHE:
        A = torch.arange(1 << n)
        K = torch.empty(n, 1 << n, 1 << n)
        for lbit in range(n):
            mask = ~(1 << lbit)
            xor = (A[:, None] & mask) ^ (A[None, :] & mask)
            dist = torch.tensor([[bin(v).count("1") for v in row] for row in xor.tolist()], dtype=torch.float32)
            sign = torch.where(((A >> lbit) & 1).bool(), 1.0, -1.0)[None, :]
            K[lbit] = alpha * beta ** dist * sign
        _K_CACHE[key] = K.to(device)
    return _K_CACHE[key]


def lut_addresses(x: torch.Tensor, mapping: torch.Tensor) -> torch.Tensor:
    n = mapping.shape[1]
    bits = (x[:, mapping] > 0).long()                       # (B, L, n)
    weights = (1 << torch.arange(n, device=x.device)).long()
    return (bits * weights).sum(-1)                         # (B, L)


class EFDFunction(torch.autograd.Function):
    @staticmethod
    def forward(ctx, x, mapping, luts, alpha, beta):
        addr = lut_addresses(x, mapping)
        L = luts.shape[0]
        out = luts[torch.arange(L, device=x.device)[None, :], addr]
        ctx.save_for_backward(x, mapping, luts, addr)
        ctx.alpha, ctx.beta = float(alpha), float(beta)
        return out

    @staticmethod
    def backward(ctx, g):
        x, mapping, luts, addr = ctx.saved_tensors
        B, L = addr.shape
        n = mapping.shape[1]
        size = luts.shape[1]
        g = g.contiguous()
        flat = (torch.arange(L, device=x.device)[None, :] * size + addr).reshape(-1)
        luts_grad = torch.zeros(L * size, device=x.device, dtype=luts.dtype).index_add_(0, flat, g.reshape(-1))
        K = _efd_kernel(n, ctx.alpha, ctx.beta, x.device).to(luts.dtype)   # (n, size, size)
        M = torch.einsum("jc,lac->jal", luts, K)                         # (L, size, n)
        w = M[torch.arange(L, device=x.device)[None, :], addr]          # (B, L, n)
        contrib = (w * g[..., None]).reshape(B, L * n)
        x_grad = torch.zeros_like(x).index_add_(1, mapping.reshape(-1), contrib)
        return x_grad, None, luts_grad.view(L, size), None, None


class STEFunction(torch.autograd.Function):
    @staticmethod
    def forward(ctx, x):
        return (x > 0).float()

    @staticmethod
    def backward(ctx, g):
        return g


class LearnableMappingFunction(torch.autograd.Function):
    @staticmethod
    def forward(ctx, x, weights, tau):
        ctx.save_for_backward(x, weights)
        ctx.tau = float(tau)
        return x[:, weights.argmax(dim=0)]

    @staticmethod
    def backward(ctx, g):
        x, weights = ctx.saved_tensors
        w_grad = (2 * x - 1).T @ g
        x_grad = g @ torch.softmax(weights / ctx.tau, dim=0).T
        return x_grad, w_grad, None


class LearnableMapping(nn.Module):
    def __init__(self, input_size: int, output_size: int, tau: float = 0.001):
        super().__init__()
        self.weights = nn.Parameter(torch.rand(input_size, output_size))
        self.tau = tau

    def forward(self, x):
        return LearnableMappingFunction.apply(x, self.weights, self.tau)

    def hard_mapping(self) -> torch.Tensor:
        return self.weights.argmax(dim=0)


def random_mapping(input_size: int, n: int, output_size: int, generator=None) -> torch.Tensor:
    """torch_dwn.mapping.layer_mapping(random=True): cover every input before repeating."""
    total = n * output_size
    full, rest = divmod(total, input_size)
    parts = [torch.randperm(input_size, generator=generator) for _ in range(full)]
    parts.append(torch.randperm(input_size, generator=generator)[:rest])
    return torch.cat(parts).reshape(output_size, n).long()


class LUTLayer(nn.Module):
    def __init__(self, input_size: int, output_size: int, n: int = 6, mapping: str = "random",
                 alpha: float | None = None, beta: float | None = None, ste: bool = True,
                 clamp_luts: bool = True, lm_tau: float = 0.001, generator=None):
        super().__init__()
        self.input_size, self.output_size, self.n = input_size, output_size, n
        self.alpha = 0.5 * 0.75 ** (n - 1) if alpha is None else alpha
        self.beta = 0.25 / 0.75 if beta is None else beta
        self.ste, self.clamp_luts = ste, clamp_luts
        self.learnable = mapping == "learnable"
        if self.learnable:
            self.lmap = LearnableMapping(input_size, output_size * n, lm_tau)
            self.register_buffer("mapping", torch.arange(output_size * n).reshape(output_size, n))
        else:
            self.register_buffer("mapping", random_mapping(input_size, n, output_size, generator))
        self.luts = nn.Parameter(torch.rand(output_size, 1 << n) * 2 - 1)

    def forward(self, x):
        if self.training and self.clamp_luts:
            with torch.no_grad():
                self.luts.clamp_(-1, 1)
        if self.learnable:
            x = self.lmap(x)
        x = EFDFunction.apply(x, self.mapping, self.luts, self.alpha, self.beta)
        return STEFunction.apply(x) if self.ste else x

    def input_mapping(self) -> torch.Tensor:
        """(output_size, n) indices into this layer's input."""
        if self.learnable:
            return self.lmap.hard_mapping().reshape(self.output_size, self.n)
        return self.mapping

    def truth_tables(self) -> torch.Tensor:
        return (self.luts > 0).to(torch.uint8)


class GroupSum(nn.Module):
    def __init__(self, k: int, tau: float = 1.0):
        super().__init__()
        self.k, self.tau = k, tau

    def forward(self, x):
        pad = (-x.shape[-1]) % self.k
        if pad:
            x = nn.functional.pad(x, (0, pad))
        return x.view(*x.shape[:-1], self.k, -1).sum(-1) / self.tau


class DWN(nn.Module):
    """Thermometer bits -> LUT layer(s) -> GroupSum over 2 classes (background, seizure)."""

    def __init__(self, n_inputs: int, layers=(200,), n: int = 6, mapping: str = "learnable", tau: float = 1 / 0.3,
                 seed: int = 0):
        super().__init__()
        g = torch.Generator().manual_seed(seed)
        torch.manual_seed(seed)
        mods, size = [], n_inputs
        for i, width in enumerate(layers):
            mods.append(LUTLayer(size, width, n, mapping if i == 0 else "random", generator=g))
            size = width
        self.layers = nn.Sequential(*mods)
        self.head = GroupSum(2, tau)

    def forward(self, bits):
        return self.head(self.layers(bits))

    @property
    def n_luts(self) -> int:
        return sum(m.output_size for m in self.layers)

    def export(self) -> dict:
        return {"layers": [{"mapping": m.input_mapping().cpu().numpy().astype(np.int32),
                            "tables": m.truth_tables().cpu().numpy()} for m in self.layers]}


# ----------------------------------------------------------------- integer inference (golden classifier)

def integer_forward(bits: np.ndarray, exported: dict) -> np.ndarray:
    """Bit-exact hardware model: LUT lookups, then score = popcount(group 1) - popcount(group 0)."""
    h = np.asarray(bits, dtype=np.uint8)
    for layer in exported["layers"]:
        mp, tt = layer["mapping"], layer["tables"]
        n = mp.shape[1]
        addr = np.zeros((h.shape[0], mp.shape[0]), dtype=np.int64)
        for lbit in range(n):
            addr |= h[:, mp[:, lbit]].astype(np.int64) << lbit
        h = tt[np.arange(mp.shape[0])[None, :], addr]
    half = (h.shape[1] + 1) // 2           # GroupSum(2): first half background, second half seizure
    return h[:, half:].sum(1).astype(np.int64) - h[:, :half].sum(1).astype(np.int64)


def used_input_bits(exported: dict, n_inputs: int) -> np.ndarray:
    used = np.zeros(n_inputs, dtype=bool)
    used[np.unique(exported["layers"][0]["mapping"])] = True
    return used
