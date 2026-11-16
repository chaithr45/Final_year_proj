// Testbench of ms_impair: loads 80 configuration words (+CFG=hex), streams +N int16 samples (+IN=hex, one per
// line) and writes the clip count followed by every output sample (decimal) to +OUT. Driven by ms/py/impair_rtl.py.
`timescale 1ns/1ps
module tb_ms_impair #(parameter SIN_HEX = "sin4096.hex");
    reg clk = 0, rst = 1, cfg_we = 0, cfg_start = 0, in_valid = 0;
    reg [6:0] cfg_addr = 0;
    reg [31:0] cfg_data = 0;
    reg signed [15:0] in_x = 0;
    wire in_ready, out_valid;
    wire signed [15:0] out_y;
    wire [31:0] clip_count;
    ms_impair #(.SIN_HEX(SIN_HEX)) dut (.clk(clk), .rst(rst), .cfg_we(cfg_we), .cfg_addr(cfg_addr), .cfg_data(cfg_data),
                   .cfg_start(cfg_start), .in_valid(in_valid), .in_x(in_x), .in_ready(in_ready),
                   .out_valid(out_valid), .out_y(out_y), .clip_count(clip_count));
    always #5 clk = ~clk;

    reg [31:0] cfgmem [0:79];
    reg [15:0] inmem [0:2097151];
    reg signed [15:0] outbuf [0:2097151];
    integer n, i, fo;
    reg [1023:0] cfg_file, in_file, out_file;

    initial begin
        if (!$value$plusargs("CFG=%s", cfg_file) || !$value$plusargs("IN=%s", in_file) ||
            !$value$plusargs("OUT=%s", out_file) || !$value$plusargs("N=%d", n)) begin
            $display("usage: +CFG= +IN= +OUT= +N="); $finish;
        end
        $readmemh(cfg_file, cfgmem);
        $readmemh(in_file, inmem, 0, n - 1);
        fo = $fopen(out_file, "w");
        repeat (3) @(posedge clk);
        rst <= 0;
        for (i = 0; i < 80; i = i + 1) begin
            @(posedge clk); cfg_we <= 1; cfg_addr <= i[6:0]; cfg_data <= cfgmem[i];
        end
        @(posedge clk); cfg_we <= 0; cfg_start <= 1;
        @(posedge clk); cfg_start <= 0;
        for (i = 0; i < n; i = i + 1) begin
            @(posedge clk);
            while (!in_ready) @(posedge clk);
            in_valid <= 1; in_x <= inmem[i];
            @(posedge clk); in_valid <= 0;
            while (!out_valid) @(posedge clk);
            outbuf[i] = out_y;
        end
        $fdisplay(fo, "%0d", clip_count);
        for (i = 0; i < n; i = i + 1) $fdisplay(fo, "%0d", $signed(outbuf[i]));
        $fclose(fo);
        $finish;
    end
endmodule
