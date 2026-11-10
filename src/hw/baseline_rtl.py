"""Verilog of the two LUT-native baselines, built like the DWN classifier (src/hw/verilog.py) so that one synthesis
flow measures all three on equal terms: registered integer features, integer comparators, the model's logic,
an integer score, decision = score >= threshold, and the k-of-10 alarm.

  TreeLUT  inputs are quantised in software as q = clip(floor((x - lo) * scale), 0, 2^w - 1) and split as q < t;
           q is monotone in x, so every split is one integer comparator x < x*(t) on the raw integer feature
           (x* found exactly by evaluating the quantiser on every integer of the feature's range).
           Each tree is a multiplexer tree over its comparator bits; score = sum of the 5-bit leaves.
  LGN      thermometer bits x > t (float t) are x > floor(t) for integer x; two layers of two-input gates
           (16 Boolean functions); score = popcount(second half) - popcount(first half).
Both are checked against their software models (TreeLUTModel.score_int, lgn_integer_forward) by simulation.
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np

from ..features import spec as S


def _w(n: int) -> int:
    return max(1, math.ceil(math.log2(n + 1)))


def _ports(names, widths, module):
    tw = int(sum(widths))
    L = ["`timescale 1ns/1ps", f"module {module} (", "    input  wire clk,", "    input  wire rst,",
         "    input  wire valid_in,", f"    input  wire [{tw - 1}:0] features,   // packed signed features, feature 0 in the LSBs"]
    return L, tw


def _feature_wires(L, names, widths):
    pos = 0
    for i, (n, w) in enumerate(zip(names, widths)):
        L.append(f"    wire signed [{w - 1}:0] x{i} = f_r[{pos + w - 1}:{pos}];   // {n}")
        pos += w


def _alarm_tail(L, sw, thr, k, n=10):
    lit = f"-{sw}'sd{abs(thr)}" if thr < 0 else f"{sw}'sd{thr}"
    cw = _w(n)
    L += [f"    wire dec_c = (score_c >= {lit});",
          f"    reg [{n - 1}:0] hist;",
          f"    function [{cw - 1}:0] ones; input [{n - 1}:0] v; integer i; begin",
          f"        ones = 0; for (i = 0; i < {n}; i = i + 1) ones = ones + v[i]; end endfunction",
          f"    wire [{n - 1}:0] hist_next = {{hist[{n - 2}:0], dec_c}};",
          "    always @(posedge clk) begin",
          "        if (rst) begin score <= 0; decision <= 1'b0; alarm <= 1'b0; out_valid <= 1'b0; hist <= 0; end",
          "        else begin out_valid <= v1;",
          "            if (v1) begin score <= score_c; decision <= dec_c; hist <= hist_next;",
          f"                alarm <= (ones(hist_next) >= {cw}'d{k}); end",
          "        end", "    end", "endmodule"]


# ---------------------------------------------------------------------------------------------- TreeLUT
def treelut_split_thresholds(model, cols, widths):
    """For every (input column, t) split: integer x* with  q(x) < t  <=>  x < x*  (None: never / always)."""
    out = {}
    for t_nodes in model.trees:
        for nd in t_nodes.values():
            if nd[0] != "split":
                continue
            key = (nd[1], nd[2])
            if key in out:
                continue
            j, t = key
            w = widths[j]
            xs = np.arange(-(1 << (w - 1)), 1 << (w - 1), dtype=np.int64)
            q = np.clip(np.floor((xs.astype(np.float64) - model.lo[j]) * model.scale[j]), 0, (1 << model.wf) - 1)
            yes = q < t
            if yes.all():
                out[key] = ("always", None)
            elif not yes.any():
                out[key] = ("never", None)
            else:
                first_no = int(xs[np.argmax(~yes)])
                assert (~yes[xs >= first_no]).all() and yes[xs < first_no].all(), "quantiser not monotone"
                out[key] = ("lt", first_no)
    return out


def generate_treelut(model, feature_names, op_threshold: float, k: int, out_path: Path,
                     module: str = "treelut_classifier") -> dict:
    widths = [S.FEATURE_BITS.get(n, 16) for n in feature_names]
    thr_int = model.int_threshold(op_threshold)
    splits = treelut_split_thresholds(model, None, widths)
    keys = sorted(splits)
    L, tw = _ports(feature_names, widths, module)
    max_sum = sum(max(nd[1] for nd in t.values() if nd[0] == "leaf") for t in model.trees)
    sw = _w(max_sum) + 1                          # signed score, room for the threshold comparison
    L += [f"    output reg  signed [{sw - 1}:0] score,", "    output reg  decision,", "    output reg  alarm,",
          "    output reg  out_valid", ");",
          f"    reg [{tw - 1}:0] f_r;", "    reg v0;",
          "    always @(posedge clk) begin",
          "        if (rst) begin v0 <= 1'b0; f_r <= 0; end",
          "        else begin v0 <= valid_in; f_r <= features; end", "    end"]
    _feature_wires(L, feature_names, widths)
    L.append(f"    wire [{len(keys) - 1}:0] c;   // c = (q < t), i.e. x < x*")
    cidx = {}
    for i, key in enumerate(keys):
        kind, xs = splits[key]
        j = key[0]
        cidx[key] = i
        if kind == "always":
            L.append(f"    assign c[{i}] = 1'b1;")
        elif kind == "never":
            L.append(f"    assign c[{i}] = 1'b0;")
        else:
            wd = widths[j]
            lit = f"-{wd}'sd{abs(xs)}" if xs < 0 else f"{wd}'sd{xs}"
            L.append(f"    assign c[{i}] = (x{j} < {lit});")
    lw = model.wt
    nt = len(model.trees)
    L.append(f"    wire [{lw - 1}:0] leaf [0:{nt - 1}];")

    def expr(nodes, nid):
        nd = nodes[nid]
        if nd[0] == "leaf":
            return f"{lw}'d{nd[1]}"
        return f"(c[{cidx[(nd[1], nd[2])]}] ? {expr(nodes, nd[3])} : {expr(nodes, nd[4])})"

    for t, nodes in enumerate(model.trees):
        L.append(f"    assign leaf[{t}] = {expr(nodes, 0)};")
    uw = _w(max_sum)
    flat = ", ".join(f"leaf[{t}]" for t in range(nt - 1, -1, -1))
    L += [f"    reg [{nt * lw - 1}:0] leaf_r;   // leaf t in bits [{lw}t + {lw - 1} : {lw}t]", "    reg v1;",
          "    always @(posedge clk) begin",
          "        if (rst) begin v1 <= 1'b0; leaf_r <= 0; end",
          f"        else begin v1 <= v0; leaf_r <= {{{flat}}}; end", "    end",
          f"    function [{uw - 1}:0] leaf_sum; input [{nt * lw - 1}:0] v; integer q; begin",
          f"        leaf_sum = 0; for (q = 0; q < {nt}; q = q + 1) leaf_sum = leaf_sum + v[q * {lw} +: {lw}]; end endfunction",
          f"    wire signed [{sw - 1}:0] score_c = $signed({{1'b0, leaf_sum(leaf_r)}});"]
    _alarm_tail(L, sw, thr_int, k)
    Path(out_path).write_text("\n".join(L) + "\n")
    return {"module": module, "widths": widths, "score_bits": sw, "threshold_int": thr_int, "latency_cycles": 3,
            "comparators": len(keys), "constant_comparators": sum(1 for v in splits.values() if v[0] != "lt"),
            "trees": nt, "feature_bus_bits": tw}


# ---------------------------------------------------------------------------------------------- LGN
_GATE = ["1'b0", "A & B", "A & ~B", "A", "~A & B", "B", "A ^ B", "A | B", "~(A | B)", "~(A ^ B)", "~B", "A | ~B",
         "~A", "~A | B", "~(A & B)", "1'b1"]


def generate_lgn(model, feature_names, op_threshold: float, k: int, out_path: Path,
                 module: str = "lgn_classifier") -> dict:
    widths = [S.FEATURE_BITS.get(n, 16) for n in feature_names]
    th = model.therm.thresholds
    th = th.detach().cpu().numpy() if hasattr(th, "detach") else np.asarray(th)
    nf, nb = th.shape
    L, tw = _ports(feature_names, widths, module)
    layers = model.exported["layers"]
    n_out = len(layers[-1]["op"])
    half = (n_out + 1) // 2
    pw = _w(max(half, n_out - half))
    sw = pw + 1
    thr_int = int(math.ceil(op_threshold))
    L += [f"    output reg  signed [{sw - 1}:0] score,", "    output reg  decision,", "    output reg  alarm,",
          "    output reg  out_valid", ");",
          f"    reg [{tw - 1}:0] f_r;", "    reg v0;",
          "    always @(posedge clk) begin",
          "        if (rst) begin v0 <= 1'b0; f_r <= 0; end",
          "        else begin v0 <= valid_in; f_r <= features; end", "    end"]
    _feature_wires(L, feature_names, widths)
    L.append(f"    wire [{nf * nb - 1}:0] g0;   // thermometer bits, feature-major (x_f > t_f,i)")
    for f in range(nf):
        wd = widths[f]
        lo, hi = -(1 << (wd - 1)), (1 << (wd - 1)) - 1
        for i in range(nb):
            t = int(math.floor(float(th[f, i])))
            b = f * nb + i
            if t >= hi:
                L.append(f"    assign g0[{b}] = 1'b0;")
            elif t < lo:
                L.append(f"    assign g0[{b}] = 1'b1;")
            else:
                lit = f"-{wd}'sd{abs(t)}" if t < 0 else f"{wd}'sd{t}"
                L.append(f"    assign g0[{b}] = (x{f} > {lit});")
    prev = "g0"
    for li, layer in enumerate(layers):
        a, bb, op = layer["a"], layer["b"], layer["op"]
        name = f"g{li + 1}"
        L.append(f"    wire [{len(op) - 1}:0] {name};")
        for j in range(len(op)):
            e = _GATE[int(op[j])].replace("A", f"{prev}[{int(a[j])}]").replace("B", f"{prev}[{int(bb[j])}]")
            L.append(f"    assign {name}[{j}] = {e};")
        prev = name
    L += [f"    reg [{n_out - 1}:0] h_r;", "    reg v1;",
          "    always @(posedge clk) begin",
          "        if (rst) begin v1 <= 1'b0; h_r <= 0; end",
          f"        else begin v1 <= v0; h_r <= {prev}; end", "    end",
          f"    function [{pw - 1}:0] pop; input [{max(half, n_out - half) - 1}:0] v; input integer n; integer i; begin",
          "        pop = 0; for (i = 0; i < n; i = i + 1) pop = pop + v[i]; end endfunction",
          f"    wire signed [{sw - 1}:0] score_c = $signed({{1'b0, pop(h_r[{n_out - 1}:{half}], {n_out - half})}}) - "
          f"$signed({{1'b0, pop(h_r[{half - 1}:0], {half})}});"]
    _alarm_tail(L, sw, thr_int, k)
    Path(out_path).write_text("\n".join(L) + "\n")
    return {"module": module, "widths": widths, "score_bits": sw, "threshold_int": thr_int, "latency_cycles": 3,
            "thermometer_bits": nf * nb, "gates": [len(layer["op"]) for layer in layers], "feature_bus_bits": tw}


def pack_hex(X: np.ndarray, widths, extra: list[tuple[np.ndarray, int]]) -> list[str]:
    """Lines {extra fields (MSB first in the order given) , features}: features packed with feature 0 in the LSBs."""
    out = []
    for t in range(len(X)):
        v, pos = 0, 0
        for c, wd in enumerate(widths):
            v |= (int(X[t, c]) & ((1 << wd) - 1)) << pos
            pos += wd
        for arr, wd in reversed(extra):
            v |= (int(arr[t]) & ((1 << wd) - 1)) << pos
            pos += wd
        out.append(f"{v:0{(pos + 3) // 4}x}")
    return out
