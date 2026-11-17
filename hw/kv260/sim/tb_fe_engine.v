// Testbench of fe_engine: streams a recording second by second (256 biopotential samples, 25 motion samples, end of
// second) through the host port exactly as a sensor interface would, reads the 38 features of every window and
// compares them with the C front end's (hw/kv260/sim/fe_vectors/<rec>.feats.hex, from scripts/verify_fe_engine.py).
// Plusargs: +samples=<file> +feats=<file> +nsec=<seconds> +nwin=<windows> +pres=<4-bit ecg,emg,acc,gyr>
`timescale 1ns/1ps
module tb_fe_engine;
    `include "fe_io.vh"
    localparam integer DW = FE_DW, AW = 10, PW = 12;
    localparam integer SW = (256 * 4 + 25 * 6) * 16;     // bits per second of samples
    localparam integer FW = FE_NFEAT * 16;                 // bits per window of features
    reg clk = 0, rst = 1, start = 0, host_we = 0;
    reg [PW-1:0] entry = 0;
    reg [AW-1:0] host_addr = 0;
    reg [DW-1:0] host_wdata = 0;
    wire [DW-1:0] host_rdata;
    wire busy;
    always #5 clk = ~clk;
    fe_engine #(.DW(DW), .AW(AW), .PW(PW), .ROM_FILE("fe_rom.hex"), .RAM_FILE("fe_ram.hex")) dut (
        .clk(clk), .rst(rst), .start(start), .entry(entry), .busy(busy), .host_we(host_we), .host_addr(host_addr),
        .host_wdata(host_wdata), .host_rdata(host_rdata));

    reg [SW-1:0] smp [0:4095];
    reg [FW-1:0] exp_f [0:4095];
    reg [8*1024-1:0] sfile, ffile;
    integer nsec, nwin, pres, b, i, j, errors, nchecked, w;
    reg [63:0] cycles;
    reg [DW-1:0] r;
    always @(posedge clk) if (busy) cycles <= cycles + 1;

    task wr(input integer a, input integer v);
        begin
            @(negedge clk); host_we = 1; host_addr = a; host_wdata = {{(DW-32){v[31]}}, v[31:0]};
            @(negedge clk); host_we = 0;
        end
    endtask
    task rd(input integer a, output reg [DW-1:0] v);
        begin
            @(negedge clk); host_addr = a;
            @(negedge clk); v = host_rdata;
        end
    endtask
    task run(input integer e);
        begin
            @(negedge clk); entry = e; start = 1;
            @(negedge clk); start = 0;
            while (busy) @(negedge clk);
        end
    endtask
    function integer s16(input [15:0] x); s16 = {{16{x[15]}}, x}; endfunction

    task check_window;
        reg [DW-1:0] v;
        begin
            rd(FE_WIN_VALID, v);
            if (v[0]) begin
                rd(FE_WIN_INDEX, v);
                w = v;
                for (j = 0; j < FE_NFEAT; j = j + 1) begin
                    rd(FE_FEAT0 + j, v);
                    if (v[15:0] !== exp_f[w][16*j +: 16] || (v[DW-1:15] != 0 && v[DW-1:15] != {(DW-15){1'b1}})) begin
                        errors = errors + 1;
                        if (errors < 10) $display("MISMATCH window %0d feature %0d: got %0d expected %0d", w, j,
                                                  $signed(v), $signed(exp_f[w][16*j +: 16]));
                    end
                end
                nchecked = nchecked + 1;
            end
        end
    endtask

    initial begin
        if (!$value$plusargs("samples=%s", sfile)) sfile = "samples.hex";
        if (!$value$plusargs("feats=%s", ffile)) ffile = "feats.hex";
        if (!$value$plusargs("nsec=%d", nsec)) nsec = 0;
        if (!$value$plusargs("nwin=%d", nwin)) nwin = 0;
        if (!$value$plusargs("pres=%d", pres)) pres = 15;
        $readmemh(sfile, smp, 0, nsec - 1);
        $readmemh(ffile, exp_f, 0, nwin - 1);
        errors = 0; nchecked = 0; cycles = 0;
        repeat (4) @(negedge clk); rst = 0;
        wr(FE_PRES_ECG, pres[0]); wr(FE_PRES_EMG, pres[1]); wr(FE_PRES_ACC, pres[2]); wr(FE_PRES_GYR, pres[3]);
        for (b = 0; b < nsec; b = b + 1) begin
            for (i = 0; i < 256; i = i + 1) begin
                wr(FE_IN_EEG1, s16(smp[b][64*i +: 16]));
                wr(FE_IN_EEG2, s16(smp[b][64*i + 16 +: 16]));
                wr(FE_IN_ECG, s16(smp[b][64*i + 32 +: 16]));
                wr(FE_IN_EMG, s16(smp[b][64*i + 48 +: 16]));
                run(FE_ENTRY_BIO);
            end
            for (i = 0; i < 25; i = i + 1) begin
                wr(FE_IN_AX, s16(smp[b][16384 + 96*i +: 16]));
                wr(FE_IN_AY, s16(smp[b][16384 + 96*i + 16 +: 16]));
                wr(FE_IN_AZ, s16(smp[b][16384 + 96*i + 32 +: 16]));
                wr(FE_IN_GX, s16(smp[b][16384 + 96*i + 48 +: 16]));
                wr(FE_IN_GY, s16(smp[b][16384 + 96*i + 64 +: 16]));
                wr(FE_IN_GZ, s16(smp[b][16384 + 96*i + 80 +: 16]));
                run(FE_ENTRY_MOV);
            end
            run(FE_ENTRY_SEC);
            check_window;
        end
        run(FE_ENTRY_FLUSH);
        check_window;
        $display("CYCLES %0d busy cycles for %0d seconds (%0d per second)", cycles, nsec, cycles / (nsec > 0 ? nsec : 1));
        if (errors == 0 && nchecked == nwin) $display("PASS %0d windows, 0 mismatches", nchecked);
        else $display("FAIL %0d errors, %0d of %0d windows checked", errors, nchecked, nwin);
        $finish;
    end
endmodule
