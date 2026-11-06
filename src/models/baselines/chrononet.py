"""PyTorch port of the official ChronoNet baseline (biomedepi/seizeit2 net/ChronoNet.py, Keras).

Architecture (inception=True, res=True, strided=True, batchnorm=True):
  3 x [Conv1D k=2,4,8 (32 filters each, stride 2, 'same', ReLU) -> concat(96) -> BatchNorm
       -> SpatialDropout1D(0.6)]
  GRU g1 -> GRU g2 -> GRU g3 on [g1,g2] -> GRU g4 on [g1,g2,g3] (last state), 32 units,
  L2(0.01) on GRU kernels and recurrent kernels -> Dense(2) -> softmax.
Training (net/routines.py): Adam(lr=0.01), weighted focal loss, lr halved every 10 epochs
while lr > 1e-5, batch 128, 300 epochs, best epoch by val 'score'.

Keras details matched: 'same' padding for strided convs (extra pad on the right),
BatchNorm momentum 0.99 / eps 1e-3, GRU with reset_after=True (PyTorch's formulation),
glorot-uniform kernels, orthogonal recurrent kernels, zero biases, Adam eps 1e-7.
"""
from __future__ import annotations

import math

import torch
import torch.nn as nn
import torch.nn.functional as F


class SameConv1d(nn.Module):
    """Keras Conv1D(padding='same') including the stride>1 asymmetric padding."""

    def __init__(self, c_in, c_out, k, stride):
        super().__init__()
        self.k, self.stride = k, stride
        self.conv = nn.Conv1d(c_in, c_out, k, stride=stride)
        nn.init.xavier_uniform_(self.conv.weight)
        nn.init.zeros_(self.conv.bias)

    def forward(self, x):
        length = x.shape[-1]
        out = math.ceil(length / self.stride)
        pad = max((out - 1) * self.stride + self.k - length, 0)
        return self.conv(F.pad(x, (pad // 2, pad - pad // 2)))


class InceptionBlock(nn.Module):
    def __init__(self, c_in, filters=32, stride=2, drop=0.6):
        super().__init__()
        self.convs = nn.ModuleList([SameConv1d(c_in, filters, k, stride) for k in (2, 4, 8)])
        self.bn = nn.BatchNorm1d(3 * filters, eps=1e-3, momentum=0.01)
        self.drop = nn.Dropout1d(drop)

    def forward(self, x):
        x = torch.cat([F.relu(c(x)) for c in self.convs], dim=1)
        return self.drop(self.bn(x))


def _keras_gru(inp, hidden):
    g = nn.GRU(inp, hidden, batch_first=True)
    for name, p in g.named_parameters():
        if "weight_ih" in name:
            for chunk in p.data.chunk(3, 0):
                nn.init.xavier_uniform_(chunk)
        elif "weight_hh" in name:
            for chunk in p.data.chunk(3, 0):
                nn.init.orthogonal_(chunk)
        else:
            nn.init.zeros_(p)
    return g


class ChronoNet(nn.Module):
    def __init__(self, n_channels=2, filters=32, state=32, cnn_drop=0.6, l2=0.01):
        super().__init__()
        self.blocks = nn.Sequential(InceptionBlock(n_channels, filters, drop=cnn_drop),
                                    InceptionBlock(3 * filters, filters, drop=cnn_drop),
                                    InceptionBlock(3 * filters, filters, drop=cnn_drop))
        c = 3 * filters
        self.g1, self.g2 = _keras_gru(c, state), _keras_gru(state, state)
        self.g3, self.g4 = _keras_gru(2 * state, state), _keras_gru(3 * state, state)
        self.dense = nn.Linear(state, 2)
        nn.init.xavier_uniform_(self.dense.weight)
        nn.init.zeros_(self.dense.bias)
        self.l2 = l2

    def forward(self, x):
        """x: (batch, time, channels) as in Keras; returns softmax probabilities (batch, 2)."""
        h = self.blocks(x.transpose(1, 2)).transpose(1, 2)
        g1, _ = self.g1(h)
        g2, _ = self.g2(g1)
        g3, _ = self.g3(torch.cat([g1, g2], -1))
        _, last = self.g4(torch.cat([g1, g2, g3], -1))
        return torch.softmax(self.dense(last[-1]), dim=-1)

    def l2_penalty(self):
        """Keras l2(0.01) on GRU kernel and recurrent kernel: 0.01 * sum(w^2)."""
        total = 0.0
        for g in (self.g1, self.g2, self.g3, self.g4):
            for name, p in g.named_parameters():
                if name.startswith("weight"):
                    total = total + (p ** 2).sum()
        return self.l2 * total


def weighted_focal_loss(probs: torch.Tensor, y: torch.Tensor, gamma: float = 2.0, eps: float = 1e-7) -> torch.Tensor:
    """net/utils.py::weighted_focal_loss, averaged over the batch as Keras does.
    probs: (B, 2) softmax; y: (B,) {0,1}. Positive loss weighted by #neg/#pos in the batch."""
    p = probs[:, 1].clamp_min(eps)
    q = probs[:, 0].clamp_min(eps)
    yb = y.bool()
    n_pos = yb.sum().float()
    n_neg = (~yb).sum().float()
    pos = -(q ** gamma) * torch.log(p) * (n_neg / (n_pos + eps))
    neg = -(p ** gamma) * torch.log(q)
    return torch.where(yb, pos, neg).mean()


def decay_schedule(epoch: int, lr: float) -> float:
    """net/utils.py::decay_schedule (Keras LearningRateScheduler, called before each epoch)."""
    if lr > 1e-5 and (epoch + 1) % 10 == 0:
        lr = lr / 2
    return lr


def val_score(probs: torch.Tensor, y: torch.Tensor) -> float:
    """Keras 'score' metric on one validation batch: 100 * sens_ovlp - 0.4 * fa_rate,
    on rounded predictions without post-processing (net/utils.py::score). The Keras tensor
    version counts detected reference events (perf_measure_ovlp_tensor), i.e. fixed=True."""
    import numpy as np
    from ...eval.seizeit2 import perf_measure_ovlp
    pred = (probs[:, 1] > 0.5).cpu().numpy().astype(int)
    true = y.cpu().numpy().astype(int)
    if true.sum() == 0:
        return float("nan")
    tp, fp, fn = perf_measure_ovlp(true, pred, fs=1, fixed=True)
    sens = tp / (tp + fn + 1e-7)
    fa_rate = float(np.clip(pred - true, 0, 1).sum()) / len(true)
    return sens * 100 - 0.4 * fa_rate
