"""KV260 (Zynq UltraScale+ K26) packaging of an exported LUT-native classifier (Phase 2 hardware kit).

Generates, from an export package (src/hw/export.py) and its golden test vectors:
  seizelut_axi.v        AXI4-Lite slave around the generated classifier (src/hw/verilog.py): feature registers,
                        commit/result registers, counters, a cycle-accurate latency counter and a built-in
                        self-test (BIST) that streams on-chip vectors through the classifier at one window per clock
                        and compares score, decision and alarm with the golden model in hardware
  seizelut_bist_rom.v   the BIST vectors as an initialised dual-port ROM (block RAM)
  lutnet_classifier.v   the classifier itself (unchanged generator output)
  seizelut_regs.json    register map, feature order and widths, for the board software
The wrapper is plain Verilog-2001 in one clock domain (the AXI clock, 100 MHz on the KV260 design).

Register map (byte offsets, 32-bit registers):
  0x000 ID        RO  0x534C5554 ("SLUT")
  0x004 INFO      RO  {latency[7:0], n_luts[7:0], n_features[7:0], version[7:0]}
  0x008 CTRL      RW  bit0 soft reset (pulse), bit1 clear counters (pulse), bit2 BIST start (pulse), bit3 BIST loop
  0x00C STATUS    RO  bit0 result valid, bit1 BIST busy, bit2 BIST done, bit3 BIST pass (last completed pass)
  0x010 COMMIT    WO  bits[1:0] EEG artefact flags; classifies the feature registers once
  0x014 RESULT    RO  [7:0] score (two's complement), [8] decision, [9] alarm, [15] valid, [31:16] result count
  0x018 NWIN      RO  windows committed            0x01C NDEC  decisions = 1     0x020 NALARM  alarm = 1
  0x024 LATENCY   RO  clock cycles from commit to result (last window)
  0x028 CYCLES    RO  free-running cycle counter (low 32 bits)
  0x02C SCRATCH   RW  read/write test register
  0x030 BIST_N    RO  number of BIST vectors       0x034 BIST_OK   matches (all passes)
  0x038 BIST_ERR  RO  mismatches (all passes)      0x03C BIST_CYC  cycles of the last pass (first input to last output)
  0x040 BIST_RUNS RO  completed passes             0x044 BIST_FIRSTERR  index of the first mismatch (0xFFFFFFFF: none)
  0x048 OP_THR    RW  programmable decision threshold (signed 8 bit; reset value = the frozen model's)
  0x04C OP_K      RW  programmable alarm count k of the last n decisions (reset value = the frozen model's)
  0x050 NDEC2     RO  decisions of the programmable path       0x054 NALARM2  alarms of the programmable path
  RESULT bits [10] / [11]: decision / alarm of the programmable operating point (the frozen outputs are unchanged;
  the programmable path ignores the artefact gate, which the exported model does not use)
  0x058 IO_CTRL   RW  demo I/O: bit0 automatic LEDs (1), bit1 LEDs follow the programmable path, bit2 buzzer enable,
                      bit3 buzzer active-low
  0x05C IO_MANUAL RW  PMOD outputs [6:0] when automatic mode is off (LED walk test)
  0x060 BTN       RO  bit0 button pressed (debounced), [31:16] number of presses
  0x064 IO_STATE  RO  PMOD outputs [6:0] now
  0x070 + 4 k     RO  comparator bits of the last result (k = 0..4, bit 32k + j)
  0x084 + 4 k     RO  LUT outputs of the last result (k = 0..1)
  Fault injection (version 2; all zero = no fault; for the on-board fault campaign, see board/fault_campaign.py):
  0x0A0 + 4 k     RW  FI_B0: force comparator output 32k + j to 0 (k = 0..4)
  0x0B4 + 4 k     RW  FI_B1: force comparator output 32k + j to 1
  0x0C8 + 4 k     RW  FI_L0: force LUT output 32k + j to 0 (k = 0..1)
  0x0D0 + 4 k     RW  FI_L1: force LUT output 32k + j to 1
  0x0D8 + 4 k     RW  FI_TT: flip truth-table entry FI_ADDR of LUT 32k + j
  0x0E0 FI_ADDR   RW  the truth-table entry (LUT address, 6 bits) flipped by FI_TT
  PMOD outputs (KV260 J2): [0] A1 score bar low, [1] A2 score bar mid, [2] A3 score bar high, [3] A4 decision,
  [4] B1 ALARM, [5] B2 buzzer (pulsed ~3 Hz while the alarm is on), [6] B3 heartbeat (toggles per result);
  input B4 = push button to GND (pull-up).
  0x100 + 4 i     RW  feature word i: feature 2i in bits [15:0], feature 2i+1 in bits [31:16] (int16, model order)
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import numpy as np

from .verilog import generate

ID_WORD = 0x534C5554
VERSION = 2          # 1: kit v3/v4 core; 2: fault injection and the coverage-selected self-test (kit v5)
REGS = {"ID": 0x000, "INFO": 0x004, "CTRL": 0x008, "STATUS": 0x00C, "COMMIT": 0x010, "RESULT": 0x014,
        "NWIN": 0x018, "NDEC": 0x01C, "NALARM": 0x020, "LATENCY": 0x024, "CYCLES": 0x028, "SCRATCH": 0x02C,
        "BIST_N": 0x030, "BIST_OK": 0x034, "BIST_ERR": 0x038, "BIST_CYC": 0x03C, "BIST_RUNS": 0x040,
        "BIST_FIRSTERR": 0x044, "OP_THR": 0x048, "OP_K": 0x04C, "NDEC2": 0x050, "NALARM2": 0x054,
        "IO_CTRL": 0x058, "IO_MANUAL": 0x05C, "BTN": 0x060, "IO_STATE": 0x064, "DBG_BITS0": 0x070, "DBG_LUTS0": 0x084,
        "FI_B0": 0x0A0, "FI_B1": 0x0B4, "FI_L0": 0x0C8, "FI_L1": 0x0D0, "FI_TT": 0x0D8, "FI_ADDR": 0x0E0,
        "FEAT0": 0x100}


def model_features(X117: np.ndarray, pkg: dict) -> np.ndarray:
    """(n, 117) golden features in spec order -> (n, n_model_features) int16 in the classifier's order."""
    idx = [f["spec_index"] for f in pkg["thresholds"]["features"]]
    return X117[:, idx].astype(np.int16)


def alarm_from_reset(decision: np.ndarray, k: int, n: int = 10) -> np.ndarray:
    """k-of-last-n alarm of a decision sequence that starts from a reset (no earlier decisions)."""
    d = np.concatenate([np.zeros(n - 1, np.int64), decision.astype(np.int64)])
    c = np.cumsum(np.concatenate([[0], d]))
    return ((c[n:] - c[:-n]) >= k).astype(np.uint8)


def _pack(feats: np.ndarray, art: np.ndarray, score: np.ndarray, dec: np.ndarray, alarm: np.ndarray,
          widths: list[int], sw: int) -> list[int]:
    """One integer per window: {alarm, decision, score[sw], artefact[2], packed features (feature 0 in the LSBs)}."""
    out = []
    for t in range(len(feats)):
        v, pos = 0, 0
        for c, wd in enumerate(widths):
            v |= (int(feats[t, c]) & ((1 << wd) - 1)) << pos
            pos += wd
        v |= (int(art[t, 0]) | (int(art[t, 1]) << 1)) << pos
        pos += 2
        v |= (int(score[t]) & ((1 << sw) - 1)) << pos
        pos += sw
        v |= int(dec[t]) << pos
        pos += 1
        v |= int(alarm[t]) << pos
        out.append(v)
    return out


def write_bist_rom(path: Path, words: list[int], width: int) -> None:
    """Initialised dual-port ROM (Vivado infers block RAM; plain Verilog-2001, Icarus/Verilator compatible)."""
    n = len(words)
    aw = max(1, (n - 1).bit_length())
    hexw = (width + 3) // 4
    L = ["// Generated by src/hw/kv260.py -- do not edit. BIST vectors {alarm, decision, score, artefact, features}.",
         "`timescale 1ns/1ps",
         "module seizelut_bist_rom (",
         "    input  wire clk,",
         f"    input  wire [{aw - 1}:0] addr_a,",
         f"    output reg  [{width - 1}:0] dout_a",
         ");",
         f"    (* rom_style = \"block\" *) reg [{width - 1}:0] rom [0:{n - 1}];",
         "    initial begin"]
    L += [f"        rom[{i}] = {width}'h{w:0{hexw}x};" for i, w in enumerate(words)]
    L += ["    end",
          "    always @(posedge clk) dout_a <= rom[addr_a];",
          "endmodule"]
    path.write_text("\n".join(L) + "\n")


WRAPPER = r"""// Generated by src/hw/kv260.py -- do not edit. AXI4-Lite wrapper of the LUT-native seizure classifier
// with a built-in self-test. Register map: see the module docstring of src/hw/kv260.py and seizelut_regs.json.
`timescale 1ns/1ps
module seizelut_axi #(
    parameter integer C_S_AXI_ADDR_WIDTH = 12,
    parameter integer DEBOUNCE_TICKS = 100000     // button sampled every 1 ms at 100 MHz
) (
    (* X_INTERFACE_INFO = "xilinx.com:signal:clock:1.0 s_axi_aclk CLK" *)
    (* X_INTERFACE_PARAMETER = "ASSOCIATED_BUSIF s_axi, ASSOCIATED_RESET s_axi_aresetn" *)
    input  wire                          s_axi_aclk,
    (* X_INTERFACE_INFO = "xilinx.com:signal:reset:1.0 s_axi_aresetn RST" *)
    (* X_INTERFACE_PARAMETER = "POLARITY ACTIVE_LOW" *)
    input  wire                          s_axi_aresetn,
    input  wire [C_S_AXI_ADDR_WIDTH-1:0] s_axi_awaddr,
    input  wire [2:0]                    s_axi_awprot,
    input  wire                          s_axi_awvalid,
    output reg                           s_axi_awready,
    input  wire [31:0]                   s_axi_wdata,
    input  wire [3:0]                    s_axi_wstrb,
    input  wire                          s_axi_wvalid,
    output reg                           s_axi_wready,
    output reg  [1:0]                    s_axi_bresp,
    output reg                           s_axi_bvalid,
    input  wire                          s_axi_bready,
    input  wire [C_S_AXI_ADDR_WIDTH-1:0] s_axi_araddr,
    input  wire [2:0]                    s_axi_arprot,
    input  wire                          s_axi_arvalid,
    output reg                           s_axi_arready,
    output reg  [31:0]                   s_axi_rdata,
    output reg  [1:0]                    s_axi_rresp,
    output reg                           s_axi_rvalid,
    input  wire                          s_axi_rready,
    output wire [6:0]                    pmod_out,   // KV260 PMOD A1-A4, B1-B3: LEDs and buzzer
    input  wire                          pmod_btn    // KV260 PMOD B4: push button to GND (pull-up)
);
    localparam integer NF   = @NF@;        // model features
    localparam integer NW   = @NW@;        // feature words (two int16 per word)
    localparam integer FW   = @FW@;        // packed feature bus width
    localparam integer SW   = @SW@;        // score width
    localparam integer LAT  = @LAT@;       // classifier latency (cycles)
    localparam integer NB   = @NB@;        // BIST vectors
    localparam integer BAW  = @BAW@;       // BIST address width
    localparam integer RW   = FW + 2 + SW + 2;   // BIST ROM word
    localparam [31:0]  INFO = 32'h@INFO@;
    localparam signed [7:0] OP_THR0 = @OPTHR@;   // frozen decision threshold
    localparam [3:0]   OP_K0 = @OPK@;           // frozen k (of the last @OPN@ decisions)

    wire clk = s_axi_aclk;
    wire rstn = s_axi_aresetn;

    // ------------------------------------------------------------------ AXI4-Lite (Xilinx template handshake)
    reg [C_S_AXI_ADDR_WIDTH-1:0] awaddr_l, araddr_l;
    reg aw_en;
    wire wr_en = s_axi_wready && s_axi_wvalid && s_axi_awready && s_axi_awvalid;
    always @(posedge clk) begin
        if (!rstn) begin
            s_axi_awready <= 1'b0; s_axi_wready <= 1'b0; s_axi_bvalid <= 1'b0; s_axi_bresp <= 2'b00;
            aw_en <= 1'b1; awaddr_l <= 0;
        end else begin
            if (!s_axi_awready && s_axi_awvalid && s_axi_wvalid && aw_en) begin
                s_axi_awready <= 1'b1; aw_en <= 1'b0; awaddr_l <= s_axi_awaddr;
            end else if (s_axi_bready && s_axi_bvalid) begin
                aw_en <= 1'b1; s_axi_awready <= 1'b0;
            end else begin
                s_axi_awready <= 1'b0;
            end
            if (!s_axi_wready && s_axi_wvalid && s_axi_awvalid && aw_en) s_axi_wready <= 1'b1;
            else s_axi_wready <= 1'b0;
            if (wr_en && !s_axi_bvalid) begin s_axi_bvalid <= 1'b1; s_axi_bresp <= 2'b00; end
            else if (s_axi_bready && s_axi_bvalid) s_axi_bvalid <= 1'b0;
        end
    end
    wire [C_S_AXI_ADDR_WIDTH-1:0] waddr = s_axi_awaddr;   // valid while wr_en (awready set only with awvalid)

    // ------------------------------------------------------------------ registers
    reg [31:0] featw [0:NW-1];
    reg [31:0] scratch;
    reg signed [7:0] op_thr;
    reg [3:0]  op_k;
    reg [3:0]  io_ctrl;
    reg [6:0]  io_manual;
    reg        bist_loop;
    reg        soft_rst, clr_cnt, bist_start, commit;
    reg [1:0]  commit_art;
    reg [159:0] fi_b0, fi_b1;              // fault injection masks (zero: no fault)
    reg [63:0]  fi_l0, fi_l1, fi_tt;
    reg [5:0]   fi_addr;
    integer i;
    always @(posedge clk) begin
        soft_rst <= 1'b0; clr_cnt <= 1'b0; bist_start <= 1'b0; commit <= 1'b0;
        if (!rstn) begin
            for (i = 0; i < NW; i = i + 1) featw[i] <= 32'd0;
            scratch <= 32'd0; bist_loop <= 1'b0; commit_art <= 2'b00; op_thr <= OP_THR0; op_k <= OP_K0;
            io_ctrl <= 4'b0101; io_manual <= 7'd0;
            fi_b0 <= 160'd0; fi_b1 <= 160'd0; fi_l0 <= 64'd0; fi_l1 <= 64'd0; fi_tt <= 64'd0; fi_addr <= 6'd0;
        end else if (wr_en) begin
            if (waddr[C_S_AXI_ADDR_WIDTH-1:8] != 0) begin
                if (waddr[7:2] < NW) featw[waddr[7:2]] <= s_axi_wdata;
            end else begin
                case (waddr[7:0])
                    8'h08: begin soft_rst <= s_axi_wdata[0]; clr_cnt <= s_axi_wdata[1];
                                 bist_start <= s_axi_wdata[2]; bist_loop <= s_axi_wdata[3]; end
                    8'h10: begin commit <= 1'b1; commit_art <= s_axi_wdata[1:0]; end
                    8'h2C: scratch <= s_axi_wdata;
                    8'h48: op_thr <= s_axi_wdata[7:0];
                    8'h4C: op_k <= s_axi_wdata[3:0];
                    8'h58: io_ctrl <= s_axi_wdata[3:0];
                    8'h5C: io_manual <= s_axi_wdata[6:0];
                    8'hA0: fi_b0[31:0] <= s_axi_wdata;    8'hA4: fi_b0[63:32] <= s_axi_wdata;
                    8'hA8: fi_b0[95:64] <= s_axi_wdata;   8'hAC: fi_b0[127:96] <= s_axi_wdata;
                    8'hB0: fi_b0[159:128] <= s_axi_wdata;
                    8'hB4: fi_b1[31:0] <= s_axi_wdata;    8'hB8: fi_b1[63:32] <= s_axi_wdata;
                    8'hBC: fi_b1[95:64] <= s_axi_wdata;   8'hC0: fi_b1[127:96] <= s_axi_wdata;
                    8'hC4: fi_b1[159:128] <= s_axi_wdata;
                    8'hC8: fi_l0[31:0] <= s_axi_wdata;    8'hCC: fi_l0[63:32] <= s_axi_wdata;
                    8'hD0: fi_l1[31:0] <= s_axi_wdata;    8'hD4: fi_l1[63:32] <= s_axi_wdata;
                    8'hD8: fi_tt[31:0] <= s_axi_wdata;    8'hDC: fi_tt[63:32] <= s_axi_wdata;
                    8'hE0: fi_addr <= s_axi_wdata[5:0];
                    default: ;
                endcase
            end
        end
    end

    // packed feature bus from the int16 registers (low width bits of each, two's complement)
    wire [FW-1:0] axi_feat;
@ASSIGNS@

    // ------------------------------------------------------------------ BIST
    localparam [2:0] B_IDLE = 3'd0, B_RST = 3'd1, B_FEED = 3'd2, B_DRAIN = 3'd3;
    reg [2:0]      bstate;
    reg [BAW-1:0]  baddr;
    reg [31:0]     bcount_in, bcount_out;
    reg            bfeed_d;
    wire [RW-1:0]  brom;
    seizelut_bist_rom u_bist_rom (.clk(clk), .addr_a(baddr), .dout_a(brom));
    reg [7:0]      exp_pipe [0:LAT];       // {alarm, decision, score} aligned with the classifier pipeline
    reg [31:0]     bist_ok, bist_err, bist_cyc, bist_runs, bist_firsterr, bist_t0;
    reg            bist_done, bist_pass, bist_pass_cur;
    wire           bist_busy = (bstate != B_IDLE);

    // ------------------------------------------------------------------ classifier
    wire           cls_rst = (!rstn) | soft_rst | (bstate == B_RST);
    wire           cls_valid = bist_busy ? bfeed_d : (commit & ~bist_busy);
    wire [FW-1:0]  cls_feat  = bist_busy ? brom[FW-1:0] : axi_feat;
    wire [1:0]     cls_art   = bist_busy ? brom[FW+1:FW] : commit_art;
    wire signed [SW-1:0] score;
    wire decision, alarm, out_valid;
    (* keep_hierarchy = "yes" *)
    wire [@NBITS@-1:0] dbg_bits;
    wire [@NLUT@-1:0]  dbg_luts;
    lutnet_classifier u_cls (.clk(clk), .rst(cls_rst), .valid_in(cls_valid), .features(cls_feat),
                             .fi_b0(fi_b0[@NBITS@-1:0]), .fi_b1(fi_b1[@NBITS@-1:0]), .fi_l0(fi_l0[@NLUT@-1:0]),
                             .fi_l1(fi_l1[@NLUT@-1:0]), .fi_tt(fi_tt[@NLUT@-1:0]), .fi_addr(fi_addr),
                             .dbg_bits(dbg_bits), .dbg_luts(dbg_luts),
                             .artefact(cls_art), .score(score), .decision(decision), .alarm(alarm),
                             .out_valid(out_valid));

    // expected outputs travel with the vectors through a LAT-deep delay line
    integer j;
    always @(posedge clk) begin
        exp_pipe[0] <= @EXPEXPR@;
        for (j = 1; j <= LAT; j = j + 1) exp_pipe[j] <= exp_pipe[j-1];
    end
    wire [7:0] exp_now = exp_pipe[LAT-1];
    wire bist_match = (score == exp_now[SW-1:0]) && (decision == exp_now[6]) && (alarm == exp_now[7]);

    reg [31:0] cycles;
    always @(posedge clk) begin
        if (!rstn) cycles <= 32'd0; else cycles <= cycles + 32'd1;
    end

    always @(posedge clk) begin
        if (!rstn) begin
            bstate <= B_IDLE; baddr <= 0; bfeed_d <= 1'b0; bcount_in <= 0; bcount_out <= 0;
            bist_ok <= 0; bist_err <= 0; bist_cyc <= 0; bist_runs <= 0; bist_firsterr <= 32'hFFFFFFFF;
            bist_t0 <= 0; bist_done <= 1'b0; bist_pass <= 1'b0; bist_pass_cur <= 1'b1;
        end else begin
            bfeed_d <= (bstate == B_FEED);
            case (bstate)
                B_IDLE: if (bist_start) begin
                    bstate <= B_RST; bist_ok <= 0; bist_err <= 0; bist_runs <= 0; bist_firsterr <= 32'hFFFFFFFF;
                    bist_done <= 1'b0;
                end
                B_RST: begin
                    bstate <= B_FEED; baddr <= 0; bcount_in <= 0; bcount_out <= 0; bist_pass_cur <= 1'b1;
                    bist_t0 <= cycles + 32'd1;
                end
                B_FEED: begin
                    bcount_in <= bcount_in + 32'd1;
                    if (bcount_in == NB - 1) bstate <= B_DRAIN; else baddr <= baddr + 1'b1;
                end
                B_DRAIN: if (bcount_out == NB) begin
                    bist_runs <= bist_runs + 32'd1; bist_cyc <= cycles - bist_t0;
                    bist_pass <= bist_pass_cur; bist_done <= 1'b1;
                    bstate <= bist_loop ? B_RST : B_IDLE;
                end
                default: bstate <= B_IDLE;
            endcase
            if (bist_busy && bstate != B_RST && out_valid) begin
                bcount_out <= bcount_out + 32'd1;
                if (bist_match) bist_ok <= bist_ok + 32'd1;
                else begin
                    bist_err <= bist_err + 32'd1; bist_pass_cur <= 1'b0;
                    if (bist_firsterr == 32'hFFFFFFFF) bist_firsterr <= bcount_out;
                end
            end
        end
    end

    // ------------------------------------------------------------------ results and counters (AXI path)
    reg [7:0]  res_score;
    reg        res_dec, res_alarm, res_valid, res_dec2, res_alarm2;
    reg [15:0] res_seq;
    reg [31:0] nwin, ndec, nalarm, latency, lat_cnt, ndec2, nalarm2;
    reg [@OPN@-1:0] hist2;
    wire signed [7:0] score8 = {{(8-SW){score[SW-1]}}, score};
    wire       dec2_c = (score8 >= op_thr);
    wire [@OPN@-1:0] hist2_next = {hist2[@OPN@-2:0], dec2_c};
    function [4:0] ones2; input [@OPN@-1:0] v; integer q; begin
        ones2 = 5'd0; for (q = 0; q < @OPN@; q = q + 1) ones2 = ones2 + {4'd0, v[q]}; end endfunction
    wire       alarm2_c = (ones2(hist2_next) >= {1'b0, op_k});
    reg        lat_run;
    always @(posedge clk) begin
        if (!rstn || soft_rst) begin
            res_score <= 0; res_dec <= 1'b0; res_alarm <= 1'b0; res_valid <= 1'b0; lat_run <= 1'b0; lat_cnt <= 0;
            res_dec2 <= 1'b0; res_alarm2 <= 1'b0; hist2 <= 0; res_seen <= 1'b0;
            if (!rstn) begin res_seq <= 0; nwin <= 0; ndec <= 0; nalarm <= 0; latency <= 0; ndec2 <= 0; nalarm2 <= 0; end
        end else begin
            if (clr_cnt) begin res_seq <= 0; nwin <= 0; ndec <= 0; nalarm <= 0; ndec2 <= 0; nalarm2 <= 0; end
            if (commit && !bist_busy) begin
                res_valid <= 1'b0; nwin <= nwin + 32'd1; lat_run <= 1'b1; lat_cnt <= 32'd1;
            end else if (lat_run) lat_cnt <= lat_cnt + 32'd1;
            if (out_valid && !bist_busy) begin
                res_score <= {{(8-SW){score[SW-1]}}, score}; res_dec <= decision; res_alarm <= alarm;   // SW < 8
                res_valid <= 1'b1; res_seq <= res_seq + 16'd1; lat_run <= 1'b0; latency <= lat_cnt;
                if (decision) ndec <= ndec + 32'd1;
                if (alarm) nalarm <= nalarm + 32'd1;
                res_dec2 <= dec2_c; res_alarm2 <= alarm2_c; hist2 <= hist2_next;
                res_bits <= dbg_bits; res_luts <= dbg_luts; res_seen <= 1'b1; heartbeat <= ~heartbeat;
                if (dec2_c) ndec2 <= ndec2 + 32'd1;
                if (alarm2_c) nalarm2 <= nalarm2 + 32'd1;
            end
        end
    end

    // ------------------------------------------------------------------ demo I/O: LEDs, buzzer, button
    reg [@NBITS@-1:0] res_bits;
    reg [@NLUT@-1:0]  res_luts;
    reg               res_seen, heartbeat;
    wire [159:0] res_bits_pad = {{(160-@NBITS@){1'b0}}, res_bits};
    wire [63:0]  res_luts_pad = {{(64-@NLUT@){1'b0}}, res_luts};
    initial begin res_bits = 0; res_luts = 0; heartbeat = 1'b0; end
    wire signed [8:0] thr_sel = io_ctrl[1] ? {op_thr[7], op_thr} : {OP_THR0[7], OP_THR0};
    wire signed [8:0] s9 = {res_score[7], res_score};
    wire dec_sel = io_ctrl[1] ? res_dec2 : res_dec;
    wire alarm_sel = io_ctrl[1] ? res_alarm2 : res_alarm;
    wire buzz_on = alarm_sel & io_ctrl[2] & cycles[24];          // pulsed ~3 Hz while the alarm is on
    wire [6:0] auto_out = {heartbeat, buzz_on ^ io_ctrl[3], alarm_sel, dec_sel,
                           res_seen & (s9 >= thr_sel - 9'sd3), res_seen & (s9 >= thr_sel - 9'sd6),
                           res_seen & (s9 >= thr_sel - 9'sd9)};
    reg [6:0] pmod_q;
    always @(posedge clk) begin
        if (!rstn) pmod_q <= {1'b0, io_ctrl[3], 5'd0};
        else pmod_q <= io_ctrl[0] ? auto_out : io_manual;
    end
    assign pmod_out = pmod_q;
    // button: two-flop synchroniser, sampled every DEBOUNCE_TICKS, pressed after 4 equal samples
    reg [1:0]  btn_sync;
    reg [31:0] btn_tick;
    reg [3:0]  btn_hist;
    reg        btn_pressed;
    reg [15:0] btn_count;
    always @(posedge clk) begin
        btn_sync <= {btn_sync[0], ~pmod_btn};          // 1 = pressed (pin pulled low)
        if (!rstn) begin btn_tick <= 0; btn_hist <= 0; btn_pressed <= 1'b0; btn_count <= 0; end
        else if (btn_tick >= DEBOUNCE_TICKS - 1) begin
            btn_tick <= 0;
            btn_hist <= {btn_hist[2:0], btn_sync[1]};
            if (&{btn_hist[2:0], btn_sync[1]} && !btn_pressed) begin btn_pressed <= 1'b1; btn_count <= btn_count + 16'd1; end
            else if (~|{btn_hist[2:0], btn_sync[1]}) btn_pressed <= 1'b0;
        end else btn_tick <= btn_tick + 32'd1;
    end

    // ------------------------------------------------------------------ AXI read
    reg [31:0] rdata_c;
    always @(*) begin
        rdata_c = 32'd0;
        if (araddr_l[C_S_AXI_ADDR_WIDTH-1:8] != 0) begin
            if (araddr_l[7:2] < NW) rdata_c = featw[araddr_l[7:2]];
        end else begin
            case (araddr_l[7:0])
                8'h00: rdata_c = 32'h@ID@;
                8'h04: rdata_c = INFO;
                8'h08: rdata_c = {28'd0, bist_loop, 3'b000};
                8'h0C: rdata_c = {28'd0, bist_pass, bist_done, bist_busy, res_valid};
                8'h14: rdata_c = {res_seq, res_valid, 3'd0, res_alarm2, res_dec2, res_alarm, res_dec, res_score};
                8'h18: rdata_c = nwin;
                8'h1C: rdata_c = ndec;
                8'h20: rdata_c = nalarm;
                8'h24: rdata_c = latency;
                8'h28: rdata_c = cycles;
                8'h2C: rdata_c = scratch;
                8'h30: rdata_c = NB;
                8'h34: rdata_c = bist_ok;
                8'h38: rdata_c = bist_err;
                8'h3C: rdata_c = bist_cyc;
                8'h40: rdata_c = bist_runs;
                8'h44: rdata_c = bist_firsterr;
                8'h48: rdata_c = {{24{op_thr[7]}}, op_thr};
                8'h4C: rdata_c = {28'd0, op_k};
                8'h50: rdata_c = ndec2;
                8'h54: rdata_c = nalarm2;
                8'h58: rdata_c = {28'd0, io_ctrl};
                8'h5C: rdata_c = {25'd0, io_manual};
                8'h60: rdata_c = {btn_count, 15'd0, btn_pressed};
                8'h64: rdata_c = {25'd0, pmod_out};
                8'h70: rdata_c = res_bits_pad[31:0];
                8'h74: rdata_c = res_bits_pad[63:32];
                8'h78: rdata_c = res_bits_pad[95:64];
                8'h7C: rdata_c = res_bits_pad[127:96];
                8'h80: rdata_c = res_bits_pad[159:128];
                8'h84: rdata_c = res_luts_pad[31:0];
                8'h88: rdata_c = res_luts_pad[63:32];
                8'hA0: rdata_c = fi_b0[31:0];    8'hA4: rdata_c = fi_b0[63:32];   8'hA8: rdata_c = fi_b0[95:64];
                8'hAC: rdata_c = fi_b0[127:96];  8'hB0: rdata_c = fi_b0[159:128];
                8'hB4: rdata_c = fi_b1[31:0];    8'hB8: rdata_c = fi_b1[63:32];   8'hBC: rdata_c = fi_b1[95:64];
                8'hC0: rdata_c = fi_b1[127:96];  8'hC4: rdata_c = fi_b1[159:128];
                8'hC8: rdata_c = fi_l0[31:0];    8'hCC: rdata_c = fi_l0[63:32];
                8'hD0: rdata_c = fi_l1[31:0];    8'hD4: rdata_c = fi_l1[63:32];
                8'hD8: rdata_c = fi_tt[31:0];    8'hDC: rdata_c = fi_tt[63:32];
                8'hE0: rdata_c = {26'd0, fi_addr};
                default: rdata_c = 32'hDEADBEEF;
            endcase
        end
    end
    reg rd_pend;
    always @(posedge clk) begin
        if (!rstn) begin
            s_axi_arready <= 1'b0; s_axi_rvalid <= 1'b0; s_axi_rresp <= 2'b00; s_axi_rdata <= 32'd0;
            araddr_l <= 0; rd_pend <= 1'b0;
        end else begin
            if (!s_axi_arready && s_axi_arvalid && !rd_pend && !s_axi_rvalid) begin
                s_axi_arready <= 1'b1; araddr_l <= s_axi_araddr; rd_pend <= 1'b1;
            end else s_axi_arready <= 1'b0;
            if (rd_pend && !s_axi_arready && !s_axi_rvalid) begin
                s_axi_rvalid <= 1'b1; s_axi_rresp <= 2'b00; s_axi_rdata <= rdata_c; rd_pend <= 1'b0;
            end else if (s_axi_rvalid && s_axi_rready) s_axi_rvalid <= 1'b0;
        end
    end
endmodule
"""


def reference(pkg: dict, F: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Score and decision of the exported classifier (one LUT layer) for features F in model order."""
    th, mp, lt, hd = pkg["thresholds"], pkg["mapping"], pkg["luts"], pkg["head"]
    col = {f["name"]: i for i, f in enumerate(th["features"])}
    bc = np.array([col[b["feature"]] for b in th["input_bits"]])
    bt = np.array([b["threshold"] for b in th["input_bits"]], dtype=np.int64)
    h = (F.astype(np.int64)[:, bc] > bt).astype(np.int64)
    for layer, tabs in zip(mp["layers"], lt["layers"]):
        m = np.array(layer["inputs"], dtype=np.int64)
        tt = np.array([[(int(t, 16) >> a) & 1 for a in range(1 << m.shape[1])] for t in tabs], dtype=np.int64)
        addr = np.zeros((len(h), m.shape[0]), np.int64)
        for lb in range(m.shape[1]):
            addr |= h[:, m[:, lb]] << lb
        h = tt[np.arange(m.shape[0])[None, :], addr]
    a0, a1 = hd["groups"]["background"]
    b0, b1 = hd["groups"]["seizure"]
    score = h[:, b0:b1].sum(1) - h[:, a0:a1].sum(1)
    return score, (score >= int(hd["decision_threshold"])).astype(np.uint8)


def build(export_dir: Path, vec_dir: Path, out_dir: Path, bist_run: str, bist_n: int = 1024,
          bist_selected: Path | None = None) -> dict:
    """Write the KV260 RTL kit into out_dir; returns the configuration (also written as seizelut_regs.json).
    bist_selected: npz with 'feats' (model order) and 'art' of coverage-selected self-test vectors
    (scripts/fault_analysis.py); they open the BIST ROM, and a seizure stretch of bist_run fills the rest."""
    from .export import load_export
    pkg = load_export(Path(export_dir))
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    info = generate(pkg, out_dir / "lutnet_classifier.v", debug=True, fi=True)
    generate(pkg, out_dir / "lutnet_classifier_plain.v", module="lutnet_classifier_plain")   # cost (no test logic)
    feats = pkg["thresholds"]["features"]
    widths = info["widths"]
    nf, sw, lat, fw = len(feats), info["score_bits"], info["latency_cycles"], info["feature_bus_bits"]
    nw = (nf + 1) // 2
    hd = pkg["head"]
    n_luts = sum(layer["n_luts"] for layer in pkg["mapping"]["layers"])
    n_last = pkg["mapping"]["layers"][-1]["n_luts"]
    assert len(pkg["thresholds"]["input_bits"]) <= 160 and n_last <= 64, "debug registers hold 160 bits and 64 LUTs"

    # packed bus assigns
    lines, pos = [], 0
    for c, wd in enumerate(widths):
        word, half = c // 2, c % 2
        lines.append(f"    assign axi_feat[{pos + wd - 1}:{pos}] = featw[{word}][{16 * half + wd - 1}:{16 * half}];"
                     f"   // {feats[c]['name']}")
        pos += wd
    assert pos == fw

    # BIST vectors: the coverage-selected vectors (if any), then consecutive windows of one recording around its
    # first alarm; expected outputs from the reference model, alarm from reset over the whole sequence
    rec = Path(vec_dir) / bist_run
    n_spec = len(json.loads((Path(vec_dir) / "manifest.json").read_text())["feature_names"])
    X117 = np.fromfile(rec / "features.i16", dtype=np.int16).reshape(-1, n_spec)
    art = np.fromfile(rec / "artefact.u8", dtype=np.uint8).reshape(-1, 2)
    score = np.fromfile(rec / "score.i32", dtype=np.int32)
    dec = np.fromfile(rec / "decision.u8", dtype=np.uint8)
    alarm = np.fromfile(rec / "alarm.u8", dtype=np.uint8)
    n_sel = 0
    if bist_selected is not None:
        d = np.load(bist_selected)
        Fs, As = d["feats"].astype(np.int16), d["art"].astype(np.uint8)
        n_sel = len(Fs)
        assert n_sel < bist_n
    n_rec = bist_n - n_sel
    first = int(np.argmax(alarm)) if alarm.any() else int(np.argmax(dec)) if dec.any() else 0
    start = int(min(max(0, first - n_rec // 2), max(0, len(dec) - n_rec)))
    sl = slice(start, start + n_rec)
    F = model_features(X117[sl], pkg)
    A = art[sl]
    sc_ref, dec_ref = reference(pkg, F)
    assert np.array_equal(sc_ref, score[sl]) and np.array_equal(dec_ref, dec[sl]), "reference model != export vectors"
    if n_sel:
        F, A = np.concatenate([Fs, F]), np.concatenate([As, A])
    sc_all, dec_all = reference(pkg, F)
    exp_alarm = alarm_from_reset(dec_all, hd["k"], hd["n"])
    words = _pack(F, A, sc_all, dec_all, exp_alarm, widths, sw)
    np.savez_compressed(out_dir / "seizelut_bist_vectors.npz", feats=F.astype(np.int16), art=A.astype(np.uint8),
                        score=sc_all.astype(np.int16), decision=dec_all, alarm=exp_alarm, n_selected=np.int64(n_sel))
    rw = fw + 2 + sw + 2
    write_bist_rom(out_dir / "seizelut_bist_rom.v", words, rw)

    assert 2 <= sw <= 6, "score must fit the 8-bit {alarm, decision, score} expectation word"
    pad = "" if sw == 6 else f"{6 - sw}'d0, "
    exp_expr = f"{{brom[RW-1], brom[RW-2], {pad}brom[FW+2+SW-1:FW+2]}}"
    info_word = (lat << 24) | (n_luts << 16) | (nf << 8) | VERSION
    v = (WRAPPER.replace("@NF@", str(nf)).replace("@NW@", str(nw)).replace("@FW@", str(fw))
         .replace("@SW@", str(sw)).replace("@LAT@", str(lat)).replace("@NB@", str(len(words)))
         .replace("@BAW@", str(max(1, (len(words) - 1).bit_length())))
         .replace("@INFO@", f"{info_word:08X}").replace("@ID@", f"{ID_WORD:08X}")
         .replace("@ASSIGNS@", "\n".join(lines)).replace("@EXPEXPR@", exp_expr)
         .replace("@OPTHR@", f"{'-' if hd['decision_threshold'] < 0 else ''}8'sd{abs(int(hd['decision_threshold']))}")
         .replace("@OPK@", f"4'd{int(hd['k'])}").replace("@OPN@", str(int(hd['n'])))
         .replace("@NBITS@", str(len(pkg["thresholds"]["input_bits"]))).replace("@NLUT@", str(n_last)))
    (out_dir / "seizelut_axi.v").write_text(v)
    cfg = {"id": ID_WORD, "version": VERSION, "info": info_word, "registers": REGS, "n_features": nf,
           "n_feature_words": nw, "features": [{"name": f["name"], "width_bits": w, "spec_index": f["spec_index"]}
                                               for f, w in zip(feats, widths)],
           "score_bits": sw, "latency_cycles": lat, "n_luts": n_luts, "k": hd["k"], "n": hd["n"],
           "decision_threshold": int(hd["decision_threshold"]), "artefact_gate": hd["artefact_gate"],
           "n_bits": len(pkg["thresholds"]["input_bits"]), "n_last_luts": n_last,
           "pmod": {"outputs": ["A1 score bar low", "A2 score bar mid", "A3 score bar high", "A4 decision",
                                "B1 ALARM", "B2 buzzer", "B3 heartbeat"], "input": "B4 button to GND"},
           "bist": {"recording": bist_run, "start_window": start, "n": len(words), "selected": n_sel,
                    "composition": (f"{n_sel} coverage-selected training windows, then " if n_sel else "")
                    + f"{n_rec} windows of {bist_run} from {start}",
                    "decisions": int(dec_all.sum()), "alarms": int(exp_alarm.sum())},
           "export": str(export_dir)}
    (out_dir / "seizelut_regs.json").write_text(json.dumps(cfg, indent=1))
    return cfg


def copy_rtl(src_dir: Path, dst_dir: Path) -> None:
    for f in ("lutnet_classifier.v", "lutnet_classifier_plain.v", "seizelut_bist_rom.v", "seizelut_axi.v",
              "seizelut_regs.json", "seizelut_bist_vectors.npz"):
        shutil.copy(Path(src_dir) / f, Path(dst_dir) / f)
