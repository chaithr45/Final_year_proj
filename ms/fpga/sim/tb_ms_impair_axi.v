// Testbench of ms_impair_axi through its AXI4-Lite port, as the ARM software would drive it: write the 80
// configuration words, start, stream +N samples (+IN) into DATA_IN while popping DATA_OUT, then read CLIPS,
// N_OUT and DROPS. Writes the clip count followed by every output sample (decimal) to +OUT, the format of
// tb_ms_impair.v, so ms/py/impair_rtl.py --axi compares it with the golden model the same way.
`timescale 1ns/1ps
module tb_ms_impair_axi #(parameter SIN_HEX = "sin4096.hex");
    reg clk = 0, rstn = 0;
    always #5 clk = ~clk;
    reg  [11:0] awaddr = 0, araddr = 0;
    reg  awvalid = 0, wvalid = 0, bready = 0, arvalid = 0, rready = 0;
    reg  [31:0] wdata = 0;
    wire awready, wready, bvalid, arready, rvalid;
    wire [1:0] bresp, rresp;
    wire [31:0] rdata;
    ms_impair_axi #(.SIN_HEX(SIN_HEX)) dut (
        .s_axi_aclk(clk), .s_axi_aresetn(rstn),
        .s_axi_awaddr(awaddr), .s_axi_awprot(3'd0), .s_axi_awvalid(awvalid), .s_axi_awready(awready),
        .s_axi_wdata(wdata), .s_axi_wstrb(4'hF), .s_axi_wvalid(wvalid), .s_axi_wready(wready),
        .s_axi_bresp(bresp), .s_axi_bvalid(bvalid), .s_axi_bready(bready),
        .s_axi_araddr(araddr), .s_axi_arprot(3'd0), .s_axi_arvalid(arvalid), .s_axi_arready(arready),
        .s_axi_rdata(rdata), .s_axi_rresp(rresp), .s_axi_rvalid(rvalid), .s_axi_rready(rready));

    task axi_write(input [11:0] a, input [31:0] d);
        begin
            awaddr = a; wdata = d; awvalid = 1; wvalid = 1; bready = 1;
            @(posedge clk); #1;
            while (!(awready && wready)) begin @(posedge clk); #1; end
            @(posedge clk); #1;                 // the slave takes the write on this edge
            awvalid = 0; wvalid = 0;
            while (!bvalid) begin @(posedge clk); #1; end
            @(posedge clk); #1;
            bready = 0;
        end
    endtask

    task axi_read(input [11:0] a, output [31:0] d);
        begin
            araddr = a; arvalid = 1; rready = 1;
            @(posedge clk); #1;
            while (!arready) begin @(posedge clk); #1; end
            @(posedge clk); #1;                 // the slave captures the read on this edge
            arvalid = 0;
            while (!rvalid) begin @(posedge clk); #1; end
            d = rdata;
            @(posedge clk); #1;
            rready = 0;
        end
    endtask

    reg [31:0] cfgmem [0:79];
    reg [15:0] inmem [0:2097151];
    reg signed [15:0] outbuf [0:2097151];
    integer n, i, fo, wr, rd;
    reg [31:0] d, clips, nout, drops, info;
    reg [1023:0] cfg_file, in_file, out_file;

    initial begin
        if (!$value$plusargs("CFG=%s", cfg_file) || !$value$plusargs("IN=%s", in_file) ||
            !$value$plusargs("OUT=%s", out_file) || !$value$plusargs("N=%d", n)) begin
            $display("usage: +CFG= +IN= +OUT= +N="); $finish;
        end
        $readmemh(cfg_file, cfgmem);
        $readmemh(in_file, inmem, 0, n - 1);
        repeat (4) @(posedge clk);
        #1 rstn = 1;
        axi_read(12'h000, info);
        if (info !== 32'h4D530100) $fatal(1, "INFO %h", info);
        for (i = 0; i < 80; i = i + 1) axi_write(12'h100 + 4 * i, cfgmem[i]);
        axi_write(12'h004, 32'd1);
        wr = 0; rd = 0;
        while (rd < n) begin
            if (wr < n && (wr - rd) < 400) begin           // stays below the 512-entry FIFOs: no drops
                axi_write(12'h010, {16'd0, inmem[wr]}); wr = wr + 1;
            end else begin
                axi_read(12'h018, d);
                if (d[16]) begin outbuf[rd] = d[15:0]; rd = rd + 1; end
            end
        end
        axi_read(12'h00C, clips);
        axi_read(12'h01C, nout);
        axi_read(12'h020, drops);
        axi_read(12'h018, d);
        if (drops != 0 || nout != n || d[16]) $fatal(1, "drops %0d n_out %0d (want %0d) extra output %0d", drops,
                                                     nout, n, d[16]);
        fo = $fopen(out_file, "w");
        $fdisplay(fo, "%0d", clips);
        for (i = 0; i < n; i = i + 1) $fdisplay(fo, "%0d", $signed(outbuf[i]));
        $fclose(fo);
        $finish;
    end
endmodule
