// AXI4-Lite wrapper of the SeizeLUT-MS impairment emulator (ms_impair, one channel), for the separate "ms1" kit
// (MS_SPEC.md D-MS6 (a)): the ARM writes raw int16 samples, the fabric impairs them, the ARM reads them back.
// The FCCM kit is not touched. Handshake as the Xilinx AXI4-Lite slave template (as hw/kv260/rtl/seizelut_axi.v).
//
// Register map (byte addresses; 32-bit words):
//   0x000 INFO      RO  32'h4D530100 ("MS", wrapper version 1.0)
//   0x004 CTRL      WO  bit0: start (load run state from the configuration words; empties both FIFOs)
//   0x008 STATUS    RO  bit0 input FIFO has room, bit1 output FIFO not empty, bit2 core busy,
//                       [15:8] reserved, [25:16] output FIFO level (0..512)
//   0x00C CLIPS     RO  samples clipped since start
//   0x010 DATA_IN   WO  [15:0] one input sample (dropped, and DROPS incremented, if the input FIFO is full)
//   0x018 DATA_OUT  RO  pops one output sample: bit16 valid, [15:0] sample (bit16 = 0: FIFO was empty)
// One AXI write per sample is enough: the core needs a few hundred clocks per sample (one write port per FIFO, so
// both FIFOs map to block RAM).
//   0x01C N_OUT     RO  output samples produced since start
//   0x020 DROPS     RO  input samples dropped since start (must stay 0; software checks it)
//   0x100..0x23C CFG WO  configuration word i at 0x100 + 4 i, i = 0..79 (layout: ms/py/impair_rtl.py config_words)
`timescale 1ns/1ps
module ms_impair_axi #(
    parameter integer C_S_AXI_ADDR_WIDTH = 12,
    parameter SIN_HEX = "sin4096.hex",
    parameter integer FIFO_AW = 9                     // 512-entry FIFOs
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
    input  wire                          s_axi_rready
);
    localparam [31:0] INFO = 32'h4D530100;
    localparam integer DEPTH = 1 << FIFO_AW;
    wire clk = s_axi_aclk;
    wire rstn = s_axi_aresetn;

    // ------------------------------------------------------------------ AXI4-Lite write channel
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
    wire [C_S_AXI_ADDR_WIDTH-1:0] waddr = s_axi_awaddr;
    wire [31:0] wdata = s_axi_wdata;

    // ------------------------------------------------------------------ core
    reg cfg_we, cfg_start;
    reg [6:0] cfg_addr;
    reg [31:0] cfg_data;
    reg core_in_valid;
    reg signed [15:0] core_in_x;
    wire core_in_ready, core_out_valid;
    wire signed [15:0] core_out_y;
    wire [31:0] clip_count;
    ms_impair #(.SIN_HEX(SIN_HEX)) u_core (
        .clk(clk), .rst(!rstn), .cfg_we(cfg_we), .cfg_addr(cfg_addr), .cfg_data(cfg_data), .cfg_start(cfg_start),
        .in_valid(core_in_valid), .in_x(core_in_x), .in_ready(core_in_ready),
        .out_valid(core_out_valid), .out_y(core_out_y), .clip_count(clip_count));

    // ------------------------------------------------------------------ FIFOs (block RAM inferred)
    reg [15:0] ifm [0:DEPTH-1];
    reg [15:0] ofm [0:DEPTH-1];
    reg [FIFO_AW:0] iw, ir, ow, orp;                 // one extra bit: full/empty
    wire [FIFO_AW:0] ilev = iw - ir, olev = ow - orp;
    wire i_room1 = ilev <= DEPTH - 1;
    reg [31:0] n_out, drops;
    reg busy;                                        // a sample is inside the core

    // reads: pop on the DATA_OUT read
    wire rd_go = s_axi_arready && s_axi_arvalid && !s_axi_rvalid;
    wire pop = rd_go && (s_axi_araddr[7:0] == 8'h18) && (s_axi_araddr[C_S_AXI_ADDR_WIDTH-1:8] == 0) && (olev != 0);

    // core feed: one sample from the input FIFO whenever the core is ready and nothing is in flight
    reg [15:0] ifm_q;
    reg feed_pend;                                   // ifm_q holds the next sample (BRAM read latency 1)
    always @(posedge clk) begin
        cfg_we <= 1'b0; cfg_start <= 1'b0; core_in_valid <= 1'b0;
        if (!rstn) begin
            iw <= 0; ir <= 0; ow <= 0; orp <= 0; n_out <= 0; drops <= 0; busy <= 1'b0; feed_pend <= 1'b0;
        end else begin
            // writes from the bus
            if (wr_en) begin
                if (waddr >= 12'h100 && waddr < 12'h240) begin
                    cfg_we <= 1'b1; cfg_addr <= (waddr - 12'h100) >> 2; cfg_data <= wdata;
                end else case (waddr[7:0])
                    8'h04: if (wdata[0]) begin
                        cfg_start <= 1'b1; iw <= 0; ir <= 0; ow <= 0; orp <= 0; n_out <= 0; drops <= 0;
                        busy <= 1'b0; feed_pend <= 1'b0;
                    end
                    8'h10: if (i_room1) begin ifm[iw[FIFO_AW-1:0]] <= wdata[15:0]; iw <= iw + 1; end
                           else drops <= drops + 1;
                    default: ;
                endcase
            end
            if (!(wr_en && waddr[7:0] == 8'h04 && wdata[0] && waddr < 12'h100)) begin
                // input FIFO -> core (one sample in flight at a time; the output FIFO must have room for it)
                if (!busy && !feed_pend && ilev != 0 && olev < DEPTH) begin
                    ifm_q <= ifm[ir[FIFO_AW-1:0]]; ir <= ir + 1; feed_pend <= 1'b1;
                end else if (feed_pend && core_in_ready) begin
                    core_in_valid <= 1'b1; core_in_x <= ifm_q; feed_pend <= 1'b0; busy <= 1'b1;
                end
                // core -> output FIFO
                if (core_out_valid && busy) begin
                    ofm[ow[FIFO_AW-1:0]] <= core_out_y; ow <= ow + 1; n_out <= n_out + 1; busy <= 1'b0;
                end
                if (pop) orp <= orp + 1;
            end
        end
    end

    // ------------------------------------------------------------------ AXI4-Lite read channel
    always @(posedge clk) begin
        if (!rstn) begin
            s_axi_arready <= 1'b0; s_axi_rvalid <= 1'b0; s_axi_rresp <= 2'b00; s_axi_rdata <= 32'd0;
        end else begin
            if (!s_axi_arready && s_axi_arvalid) s_axi_arready <= 1'b1;
            else s_axi_arready <= 1'b0;
            if (rd_go) begin
                s_axi_rvalid <= 1'b1; s_axi_rresp <= 2'b00;
                case (s_axi_araddr[7:0])
                    8'h00: s_axi_rdata <= INFO;
                    8'h08: s_axi_rdata <= {6'd0, olev, 8'd0, 5'd0, busy | feed_pend, olev != 0, i_room1};
                    8'h0C: s_axi_rdata <= clip_count;
                    8'h18: s_axi_rdata <= (olev != 0) ? {15'd0, 1'b1, ofm[orp[FIFO_AW-1:0]]} : 32'd0;
                    8'h1C: s_axi_rdata <= n_out;
                    8'h20: s_axi_rdata <= drops;
                    default: s_axi_rdata <= 32'd0;
                endcase
                if (s_axi_araddr[C_S_AXI_ADDR_WIDTH-1:8] != 0) s_axi_rdata <= 32'd0;
            end else if (s_axi_rvalid && s_axi_rready) s_axi_rvalid <= 1'b0;
        end
    end
endmodule
