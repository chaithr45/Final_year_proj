// End-to-end testbench of seizelut_axi (core version 3): raw samples -> feature engine in the fabric -> classifier,
// driven through the AXI4-Lite registers exactly as the board software (seizelut_kv260.py, fastio.c) drives them.
// Per second: for each 256-Hz sample the present biopotential inputs are written into the engine's register file
// (FE window) and a BIO event is started; for each 25-Hz sample the motion inputs and MOV; then SEC. After a SEC (and
// the final FLUSH) that ends a window, the core has copied the engine's 38 features into the feature registers and
// classified them; the testbench reads them back with RESULT and compares features, score, decision and alarm with
// the golden vectors of the exported model. Then it restores the engine's initial register file through the FE
// window (as the software does before every recording), replays the first seconds again and checks them again.
// Plusargs: +samples=<fe_vectors/rec.samples.hex> +vec=<vectors/rec.hex> +nsec=<s> +nwin=<windows> +pres=<4-bit>
//           +ram=<rtl/fe/fe_ram.hex> +nram=<registers> +replay=<seconds of the second pass>
`timescale 1ns/1ps
module tb_seizelut_fe;
    `include "fe_io.vh"
    localparam integer NF = 38, NW = 19, NB = 146, NL = 50, LW0 = 1 + 1 + 8 + 2 + 16 * NF, LW = LW0 + NB + NL;
    localparam integer SW = (256 * 4 + 25 * 6) * 16;
    localparam [12:0] FE_CTRL = 13'h0E4, FE_STATUS = 13'h0E8, FE_BUSYCYC = 13'h0F0, FE_NEV = 13'h0F4,
                      FE_NWIN = 13'h0F8, FE_LASTWIN = 13'h0FC, FE_WIN = 13'h1000;
    reg clk = 0, rstn = 0;
    always #5 clk = ~clk;

    reg  [12:0] awaddr = 0, araddr = 0;
    reg         awvalid = 0, wvalid = 0, bready = 1, arvalid = 0, rready = 1;
    reg  [31:0] wdata = 0;
    wire        awready, wready, bvalid, arready, rvalid;
    wire [1:0]  bresp, rresp;
    wire [31:0] rdata;
    wire [6:0]  pmod_out;
    seizelut_axi #(.DEBOUNCE_TICKS(4)) dut (.s_axi_aclk(clk), .s_axi_aresetn(rstn), .pmod_out(pmod_out), .pmod_btn(1'b1),
        .s_axi_awaddr(awaddr), .s_axi_awprot(3'b000), .s_axi_awvalid(awvalid), .s_axi_awready(awready),
        .s_axi_wdata(wdata), .s_axi_wstrb(4'hF), .s_axi_wvalid(wvalid), .s_axi_wready(wready),
        .s_axi_bresp(bresp), .s_axi_bvalid(bvalid), .s_axi_bready(bready),
        .s_axi_araddr(araddr), .s_axi_arprot(3'b000), .s_axi_arvalid(arvalid), .s_axi_arready(arready),
        .s_axi_rdata(rdata), .s_axi_rresp(rresp), .s_axi_rvalid(rvalid), .s_axi_rready(rready));

    task axi_write(input [12:0] a, input [31:0] d);
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
    task axi_read(input [12:0] a, output [31:0] d);
        begin
            @(negedge clk); araddr = a; arvalid = 1;
            @(posedge clk); while (!arready) @(posedge clk);
            @(negedge clk); arvalid = 0;
            while (!rvalid) @(posedge clk);
            d = rdata;
            @(posedge clk);
        end
    endtask

    reg [SW-1:0] smp [0:4095];
    reg [LW-1:0] gold [0:4095];
    reg [39:0]   ram_img [0:1023];
    reg [8*1024-1:0] sfile, vfile, rfile;
    integer nsec, nwin, pres, nram, replay, errors, nchecked, b, i, k, w, polls, drops_seen, pass;
    reg [31:0] r, res, seq, st;
    reg [15:0] nev;
    reg [63:0] t_start;

    function [31:0] s16(input [15:0] x); s16 = {{16{x[15]}}, x}; endfunction
    task fe_wr(input integer reg_i, input [31:0] v); axi_write(FE_WIN + 4 * reg_i, v); endtask

    // start an event and wait until the core has started it (event count) and finished everything it triggered
    task fe_event(input [1:0] ev);
        begin
            axi_write(FE_CTRL, {30'd0, ev});
            nev = nev + 16'd1;
            polls = 0;
            st = 0;
            axi_read(FE_STATUS, st);
            while (!(st[31:16] == nev && !st[0]) && polls < 200000) begin axi_read(FE_STATUS, st); polls = polls + 1; end
            if (polls >= 200000) begin
                errors = errors + 1;
                $display("TIMEOUT event %0d: FE_STATUS %h (expected events %0d), engine state %0d pc %0d busy %b", ev, st, nev,
                         dut.u_fe.state, dut.u_fe.pc, dut.u_fe.busy);
                $finish;
            end
        end
    endtask

    // after SEC / FLUSH: if a window ended, check the fabric's features and the classifier's result
    task check_window;
        reg [LW-1:0] line;
        begin
            if (st[1]) begin
                axi_read(FE_LASTWIN, r); w = r;
                axi_read(13'h014, res);
                if (!(res[15] && res[31:16] == seq[15:0] + 16'd1)) begin
                    errors = errors + 1;
                    if (errors < 10) $display("NO RESULT for window %0d (RESULT %h, seq %0d)", w, res, seq);
                end
                seq = res[31:16];
                line = gold[w];
                for (k = 0; k < NW; k = k + 1) begin
                    axi_read(13'h100 + 4 * k, r);
                    if (r !== {line[16 * (2 * k + 1) +: 16], line[16 * (2 * k) +: 16]}) begin
                        errors = errors + 1;
                        if (errors < 10) $display("FEATURE MISMATCH window %0d word %0d: got %h expected %h", w, k, r,
                                                  {line[16 * (2 * k + 1) +: 16], line[16 * (2 * k) +: 16]});
                    end
                end
                if (res[7:0] !== line[16 * NF + 2 +: 8] || res[8] !== line[LW0 - 2] || res[9] !== line[LW0 - 1]) begin
                    errors = errors + 1;
                    if (errors < 10) $display("RESULT MISMATCH window %0d: score %0d dec %b alarm %b, expected %0d %b %b",
                                              w, $signed(res[7:0]), res[8], res[9], $signed(line[16 * NF + 2 +: 8]),
                                              line[LW0 - 2], line[LW0 - 1]);
                end
                // the engine's own WIN_INDEX, read through the FE window
                axi_read(FE_WIN + 4 * FE_WIN_INDEX, r);
                if (r != w) begin errors = errors + 1; if (errors < 10) $display("WIN_INDEX %0d != %0d", r, w); end
                nchecked = nchecked + 1;
            end
        end
    endtask

    // one second of samples: present inputs only (absent ones stay at their initial value 0), then SEC
    task push_second(input integer bb);
        begin
            for (i = 0; i < 256; i = i + 1) begin
                fe_wr(FE_IN_EEG1, s16(smp[bb][64 * i +: 16]));
                fe_wr(FE_IN_EEG2, s16(smp[bb][64 * i + 16 +: 16]));
                if (pres[0]) fe_wr(FE_IN_ECG, s16(smp[bb][64 * i + 32 +: 16]));
                if (pres[1]) fe_wr(FE_IN_EMG, s16(smp[bb][64 * i + 48 +: 16]));
                fe_event(2'd0);
            end
            for (i = 0; i < 25; i = i + 1) begin
                if (pres[2]) begin
                    fe_wr(FE_IN_AX, s16(smp[bb][16384 + 96 * i +: 16]));
                    fe_wr(FE_IN_AY, s16(smp[bb][16384 + 96 * i + 16 +: 16]));
                    fe_wr(FE_IN_AZ, s16(smp[bb][16384 + 96 * i + 32 +: 16]));
                end
                if (pres[3]) begin
                    fe_wr(FE_IN_GX, s16(smp[bb][16384 + 96 * i + 48 +: 16]));
                    fe_wr(FE_IN_GY, s16(smp[bb][16384 + 96 * i + 64 +: 16]));
                    fe_wr(FE_IN_GZ, s16(smp[bb][16384 + 96 * i + 80 +: 16]));
                end
                fe_event(2'd1);
            end
            fe_event(2'd2);
            check_window;
        end
    endtask

    task start_recording;
        begin
            axi_write(13'h008, 32'h3);                    // soft reset + clear counters (classifier history)
            axi_read(13'h014, res); seq = res[31:16];
            fe_wr(FE_PRES_ECG, pres[0]); fe_wr(FE_PRES_EMG, pres[1]);
            fe_wr(FE_PRES_ACC, pres[2]); fe_wr(FE_PRES_GYR, pres[3]);
        end
    endtask

    initial begin
        if (!$value$plusargs("samples=%s", sfile)) sfile = "samples.hex";
        if (!$value$plusargs("vec=%s", vfile)) vfile = "vectors.hex";
        if (!$value$plusargs("ram=%s", rfile)) rfile = "fe_ram.hex";
        if (!$value$plusargs("nsec=%d", nsec)) nsec = 0;
        if (!$value$plusargs("nwin=%d", nwin)) nwin = 0;
        if (!$value$plusargs("pres=%d", pres)) pres = 15;
        if (!$value$plusargs("nram=%d", nram)) nram = 0;
        if (!$value$plusargs("replay=%d", replay)) replay = 30;
        $readmemh(sfile, smp, 0, nsec - 1);
        $readmemh(vfile, gold, 0, nwin - 1);
        if (nram > 0) $readmemh(rfile, ram_img, 0, nram - 1);
        errors = 0; nchecked = 0; nev = 0; pass = 0;
        repeat (5) @(posedge clk); rstn = 1; repeat (2) @(posedge clk);
        axi_read(13'h004, r); $display("INFO %h", r);
        if (r[7:0] != 8'd3) begin errors = errors + 1; $display("core version %0d, expected 3", r[7:0]); end
        axi_read(13'h0EC, r); if (r !== 32'd1) begin errors = errors + 1; $display("FE_CFG reset %h", r); end

        // ---- pass 1: the whole recording from the engine's power-on state
        start_recording;
        t_start = $time;
        for (b = 0; b < nsec; b = b + 1) push_second(b);
        fe_event(2'd3);                                   // FLUSH: the last window
        check_window;
        axi_read(FE_NWIN, r);
        if (r != nwin) begin errors = errors + 1; $display("FE_NWIN %0d, expected %0d", r, nwin); end
        axi_read(13'h018, r);
        if (r != nwin) begin errors = errors + 1; $display("NWIN %0d, expected %0d", r, nwin); end
        axi_read(FE_STATUS, st);
        if (st[15:8] != 0) begin errors = errors + 1; $display("%0d accesses dropped while busy", st[15:8]); end
        axi_read(FE_BUSYCYC, r);
        $display("ENGINE %0d busy cycles for %0d seconds (%0d per second); %0d windows checked",
                 r, nsec, r / (nsec > 0 ? nsec : 1), nchecked);
        $display("BUS %0d us of simulated time per second of signal at 100 MHz", (($time - t_start) / 1000) / (nsec > 0 ? nsec : 1));
        pass = nchecked;

        // ---- pass 2: restore the engine's register file through the FE window, replay the first seconds
        if (nram > 0 && replay > 2) begin
            for (k = 0; k < nram; k = k + 1) fe_wr(k, ram_img[k][31:0]);
            for (k = 0; k < nram; k = k + 37) begin       // spot check of the restored image
                axi_read(FE_WIN + 4 * k, r);
                if (r !== ram_img[k][31:0]) begin errors = errors + 1; $display("RAM restore %0d: %h != %h", k, r, ram_img[k][31:0]); end
            end
            nchecked = 0;
            start_recording;
            for (b = 0; b < replay; b = b + 1) push_second(b);
            $display("REPLAY %0d windows checked after restoring the register file", nchecked);
            if (nchecked != replay - 2) begin errors = errors + 1; $display("replay: %0d windows, expected %0d", nchecked, replay - 2); end
        end
        if (errors == 0 && pass == nwin) $display("PASS %0d windows, 0 mismatches", pass);
        else $display("FAIL %0d errors, %0d of %0d windows checked", errors, pass, nwin);
        $finish;
    end
endmodule
