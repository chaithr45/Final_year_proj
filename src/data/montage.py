"""Behind-the-ear EEG montage handling.

The two EEG channels do not mean the same thing in every patient (Section 3.1):
  * left-onset suspicion:  BTEleft SD (same side) + CROSStop SD (cross-head)
  * right-onset suspicion: BTEright SD (same side) + CROSStop SD (cross-head)
  * generalised suspicion: BTEleft SD + BTEright SD (two lateral channels)

`eeg_channel_pair` returns the channels in the same order as the official code
(biomedepi/seizeit2 net/utils.py::apply_preprocess_eeg): first BTEleft, else
BTEright; second CROSStop, else BTEright. Models must not rely on this order --
the feature pipeline feeds symmetric cross-channel combinations (mean, max,
|difference|) -- but the order is fixed so per-channel features are reproducible.
"""
from __future__ import annotations

BTE_LEFT = "BTEleft SD"
BTE_RIGHT = "BTEright SD"
CROSS = "CROSStop SD"

MONTAGE_TYPES = ("left", "right", "bilateral")


def eeg_channel_pair(labels: list[str]) -> tuple[str, str]:
    first = BTE_LEFT if BTE_LEFT in labels else BTE_RIGHT if BTE_RIGHT in labels else None
    second = CROSS if CROSS in labels else BTE_RIGHT if (BTE_RIGHT in labels and first != BTE_RIGHT) else None
    if first is None or second is None:
        raise ValueError(f"cannot form an EEG channel pair from {labels}")
    return first, second


def montage_type(labels: list[str]) -> str:
    """Classify the montage from the channel labels in the EDF."""
    s = set(labels)
    if CROSS in s and BTE_LEFT in s and BTE_RIGHT not in s:
        return "left"
    if CROSS in s and BTE_RIGHT in s and BTE_LEFT not in s:
        return "right"
    if BTE_LEFT in s and BTE_RIGHT in s and CROSS not in s:
        return "bilateral"
    return "other:" + "|".join(sorted(labels))
