"""Hardware cost estimates computed in software (Section 8.3). Always labelled "estimated".

Assumptions (stated in the paper):
* LUT network: one LUT6 per neuron with n <= 6 inputs.
* Encoder: one comparator per distinct threshold kept after pruning; a W-bit compare against a
  constant costs ceil(W/2) LUT6 on a carry chain (about 2 bits per LUT). The prompt's
  "thresholds x feature width" is reported as comparator bits.
* Popcount + compare: an N-input popcount costs about N LUTs (adder tree), plus one comparator.
* Post-processing (k of last 10, merge, refractory): 10-bit shift register, 4-bit counter,
  comparators and a refractory counter: about 12 LUTs.
* Multipliers: data x weight products. Zero for LUT networks and trees.
"""
from __future__ import annotations

import math

import numpy as np

POSTPROC_LUTS = 12


def dwn_cost(exported: dict, thermometer, feature_bits: list[int], used_bits: np.ndarray) -> dict:
    neurons = sum(layer["mapping"].shape[0] for layer in exported["layers"])
    t = thermometer.thresholds
    mask = used_bits.reshape(t.shape)
    comps, comp_bits, enc_luts = 0, 0, 0
    for f in range(t.shape[0]):
        vals = t[f][mask[f]]
        k = len(np.unique(vals[np.isfinite(vals)]))
        comps += k
        comp_bits += k * feature_bits[f]
        enc_luts += k * math.ceil(feature_bits[f] / 2)
    last = exported["layers"][-1]["mapping"].shape[0]
    pop = last + math.ceil(math.log2(last + 1)) + 1
    all_comps = thermometer.distinct_comparators()
    return {"network_luts": int(neurons), "encoder_comparators": int(comps), "encoder_comparator_bits": int(comp_bits),
            "encoder_luts": int(enc_luts), "encoder_comparators_before_pruning": int(all_comps),
            "popcount_luts": int(pop), "postproc_luts": POSTPROC_LUTS,
            "total_luts": int(neurons + enc_luts + pop + POSTPROC_LUTS), "multipliers": 0}


def tree_cost(n_split_nodes: int, n_distinct_splits: int, n_leaves: int, n_trees: int, feature_bits: int = 10,
              leaf_bits: int = 8) -> dict:
    comp_luts = n_distinct_splits * math.ceil(feature_bits / 2)
    adder_luts = n_trees * leaf_bits          # one leaf_bits-wide adder per tree in the sum
    mux_luts = n_leaves                        # leaf selection logic, ~1 LUT per leaf
    return {"split_nodes": int(n_split_nodes), "distinct_comparators": int(n_distinct_splits),
            "leaves": int(n_leaves), "trees": int(n_trees), "comparator_luts": int(comp_luts),
            "leaf_luts": int(mux_luts + adder_luts),
            "total_luts": int(comp_luts + mux_luts + adder_luts + POSTPROC_LUTS), "multipliers": 0}


def linear_cost(n_inputs: int, n_outputs: int = 1, bits: int = 8) -> dict:
    return {"macs": n_inputs * n_outputs, "weights": n_inputs * n_outputs + n_outputs, "weight_bits": bits,
            "multipliers": n_inputs * n_outputs}


def mlp_cost(sizes: list[int], bits: int = 8) -> dict:
    macs = sum(a * b for a, b in zip(sizes[:-1], sizes[1:]))
    weights = macs + sum(sizes[1:])
    return {"macs": macs, "weights": weights, "weight_bits": bits, "multipliers": macs}
