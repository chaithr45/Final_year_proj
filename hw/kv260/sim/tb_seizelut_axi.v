// AXI4-Lite testbench of seizelut_axi: drives the registers exactly as the board software does
// (soft reset, 19 feature words + COMMIT per window, poll RESULT), compares score/decision/alarm with
// the golden model for every window of one recording, then checks the counters, the latency register,
// the ID/INFO/SCRATCH registers and one BIST pass. Plusargs: +vec=<hex file> +n=<windows> [+bist=1]
// Vector line: {alarm, decision, score[7:0], artefact[1:0], feature37[15:0] ... feature0[15:0]}.
`timescale 1ns/1ps
module tb_seizelut_axi;
    localparam integer NF = 38, NW = 19, LW = 1 + 1 + 8 + 2 + 16 * NF;
    reg clk = 0, rstn = 0;
    always #5 clk = ~clk;

    reg  [11:0] awaddr = 0, araddr = 0;
    reg         awvalid = 0, wvalid = 0, bready = 1, arvalid = 0, rready = 1;
    reg  [31:0] wdata = 0;
    wire        awready, wready, bvalid, arready, rvalid;
    wire [1:0]  bresp, rresp;
    wire [31:0] rdata;

    seizelut_axi dut (.s_axi_aclk(clk), .s_axi_aresetn(rstn),
        .s_axi_awaddr(awaddr), .s_axi_awprot(3'b000), .s_axi_awvalid(awvalid), .s_axi_awready(awready),
        .s_axi_wdata(wdata), .s_axi_wstrb(4'hF), .s_axi_wvalid(wvalid), .s_axi_wready(wready),
        .s_axi_bresp(bresp), .s_axi_bvalid(bvalid), .s_axi_bready(bready),
        .s_axi_araddr(araddr), .s_axi_arprot(3'b000), .s_axi_arvalid(arvalid), .s_axi_arready(arready),
        .s_axi_rdata(rdata), .s_axi_rresp(rresp), .s_axi_rvalid(rvalid), .s_axi_rready(rready));

    task axi_write(input [11:0] a, input [31:0] d);
        reg aw_done, w_done;
        begin
            @(negedge clk); awaddr = a; wdata = d; awvalid = 1; wvalid = 1; aw_done = 0; w_done = 0;
            while (!(aw_done && w_done)) begin
                @(posedge clk);
                if (awready && awvalid) aw_done = 1;
                if (wready && wvalid) w_done = 1;
                @(negedge clk);
                if (aw_done) awvalid = 0;
                if (w_done) wvalid = 0;
            end
            while (!bvalid) @(posedge clk);
            @(posedge clk);
        end
    endtask

    task axi_read(input [11:0] a, output [31:0] d);
        begin
            @(negedge clk); araddr = a; arvalid = 1;
            @(posedge clk); while (!arready) @(posedge clk);
            @(negedge clk); arvalid = 0;
            while (!rvalid) @(posedge clk);
            d = rdata;
            @(posedge clk);
        end
    endtask

    reg [LW-1:0] mem [0:200000];
    reg [LW-1:0] line;
    reg [31:0] r, res, seq_prev;
    integer n, t, k, errors, exp_dec_sum, exp_alarm_sum, polls, bist;
    reg [7:0] exp_score;
    reg exp_dec, exp_alarm;
    reg [8*1024-1:0] vecfile;
    integer thr2, k2, exp_dec2_sum, exp_alarm2_sum, q, ones;
    reg [9:0] hist2;
    reg exp_dec2, exp_alarm2;

    initial begin
        if (!$value$plusargs("vec=%s", vecfile)) vecfile = "vectors.hex";
        if (!$value$plusargs("n=%d", n)) n = 0;
        if (!$value$plusargs("bist=%d", bist)) bist = 1;
        if (!$value$plusargs("thr2=%d", thr2)) thr2 = 2;
        if (!$value$plusargs("k2=%d", k2)) k2 = 10;
        exp_dec2_sum = 0; exp_alarm2_sum = 0; hist2 = 0;
        if (n > 0) $readmemh(vecfile, mem, 0, n - 1);
        errors = 0; exp_dec_sum = 0; exp_alarm_sum = 0;
        repeat (5) @(posedge clk); rstn = 1; repeat (2) @(posedge clk);

        axi_read(12'h000, r); if (r !== 32'h534C5554) begin errors = errors + 1; $display("ID %h", r); end
        axi_read(12'h004, r); $display("INFO %h", r);
        axi_write(12'h02C, 32'hA5A5_1234); axi_read(12'h02C, r);
        if (r !== 32'hA5A5_1234) begin errors = errors + 1; $display("SCRATCH %h", r); end
        axi_read(12'h048, r); if (r !== 32'd9) begin errors = errors + 1; $display("OP_THR reset %h", r); end
        axi_read(12'h04C, r); if (r !== 32'd10) begin errors = errors + 1; $display("OP_K reset %h", r); end
        axi_write(12'h048, thr2); axi_write(12'h04C, k2);
        axi_read(12'h048, r); if ($signed(r) != thr2) begin errors = errors + 1; $display("OP_THR %h", r); end

        // ---------------- golden replay of one recording through the registers
        axi_write(12'h008, 32'h3);                       // soft reset + clear counters
        axi_read(12'h014, r); seq_prev = r[31:16];
        for (t = 0; t < n; t = t + 1) begin
            line = mem[t];
            if (^line === 1'bx) begin
                errors = errors + 1;
                if (errors < 10) $display("BAD VECTOR (X) at %0d: vector file missing or short", t);
            end
            for (k = 0; k < NW; k = k + 1)
                axi_write(12'h100 + 4 * k, {line[16 * (2 * k + 1) +: 16], line[16 * (2 * k) +: 16]});
            axi_write(12'h010, {30'd0, line[16 * NF +: 2]});
            polls = 0;
            res = 0;
            while (!(res[15] && res[31:16] == seq_prev[15:0] + 16'd1) && polls < 100) begin
                axi_read(12'h014, res); polls = polls + 1;
            end
            seq_prev = res[31:16];
            exp_score = line[16 * NF + 2 +: 8]; exp_dec = line[LW - 2]; exp_alarm = line[LW - 1];
            exp_dec_sum = exp_dec_sum + exp_dec; exp_alarm_sum = exp_alarm_sum + exp_alarm;
            exp_dec2 = ($signed(exp_score) >= thr2);
            hist2 = {hist2[8:0], exp_dec2};
            ones = 0; for (q = 0; q < 10; q = q + 1) ones = ones + hist2[q];
            exp_alarm2 = (ones >= k2);
            exp_dec2_sum = exp_dec2_sum + exp_dec2; exp_alarm2_sum = exp_alarm2_sum + exp_alarm2;
            if (res[10] !== exp_dec2 || res[11] !== exp_alarm2) begin
                errors = errors + 1;
                if (errors < 10) $display("MISMATCH2 t=%0d dec2 %b exp %b alarm2 %b exp %b", t, res[10], exp_dec2, res[11], exp_alarm2);
            end
            if (res[7:0] !== exp_score || res[8] !== exp_dec || res[9] !== exp_alarm || polls >= 100
                || ^res[9:0] === 1'bx) begin
                errors = errors + 1;
                if (errors < 10) $display("MISMATCH t=%0d score %0d exp %0d dec %b exp %b alarm %b exp %b polls %0d",
                    t, $signed(res[7:0]), $signed(exp_score), res[8], exp_dec, res[9], exp_alarm, polls);
            end
        end
        if (n > 0) begin
            axi_read(12'h018, r); if (r != n) begin errors = errors + 1; $display("NWIN %0d", r); end
            axi_read(12'h01C, r); if (r != exp_dec_sum) begin errors = errors + 1; $display("NDEC %0d exp %0d", r, exp_dec_sum); end
            axi_read(12'h020, r); if (r != exp_alarm_sum) begin errors = errors + 1; $display("NALARM %0d exp %0d", r, exp_alarm_sum); end
            axi_read(12'h050, r); if (r != exp_dec2_sum) begin errors = errors + 1; $display("NDEC2 %0d exp %0d", r, exp_dec2_sum); end
            axi_read(12'h054, r); if (r != exp_alarm2_sum) begin errors = errors + 1; $display("NALARM2 %0d exp %0d", r, exp_alarm2_sum); end
            $display("OP2 thr=%0d k=%0d: decisions %0d alarms %0d", thr2, k2, exp_dec2_sum, exp_alarm2_sum);
            axi_read(12'h024, r); $display("LATENCY %0d cycles", r);
            if (r != 3) begin errors = errors + 1; end
        end

        // ---------------- built-in self-test (one pass), result must match the golden model
        if (bist) begin
            axi_write(12'h008, 32'h4);
            r = 0; polls = 0;
            while (!r[2] && polls < 10000) begin axi_read(12'h00C, r); polls = polls + 1; end
            $display("BIST status %b", r[3:0]);
            axi_read(12'h034, r); $display("BIST_OK %0d", r);
            axi_read(12'h038, res); $display("BIST_ERR %0d", res);
            if (!(res == 0 && r == 1024)) errors = errors + 1;
            axi_read(12'h03C, r); $display("BIST_CYC %0d", r);
            axi_read(12'h044, r); $display("BIST_FIRSTERR %h", r);
            // an AXI classification after BIST still works (soft reset first)
        end
        if (errors == 0) $display("PASS %0d windows, 0 mismatches", n);
        else $display("FAIL %0d errors", errors);
        $finish;
    end
endmodule
