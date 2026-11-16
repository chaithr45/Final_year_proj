// SeizeLUT-MS analog impairment emulator, one channel (Phase 1, MS_SPEC.md 1.1 and D-MS6/D-MS7).
// Bit-exact RTL twin of ms/py/impair.py: same operations, same order, same rounding. No multipliers: every
// constant product is a sum of signed powers of two, evaluated one term per clock by one 64-bit adder.
//
// Per input sample (int16 on the detector's input grid) the FSM computes, in internal units (input LSB / 16):
//   v = x<<4 + mains + offset + drift + white + pink;  v += round(v*gain);  v = HP(v);  v = LP(v);
//   code = clip(round(v / q), -2^(N-1), 2^(N-1)-1);  y = code * q
// and raises out_valid with y. A few hundred clocks per sample (real time needs ~1.2 k samples/s in total).
//
// Configuration: 80 words of 32 bits written through cfg_we/cfg_addr/cfg_data while idle (layout in
// ms/py/impair_rtl.py, function config_words). cfg_start resets the per-run state (sample counter, filters,
// noise generators loaded from their seed words, Voss rows, drift, mains phases).
`timescale 1ns/1ps
module ms_impair #(
    parameter SIN_HEX = "sin4096.hex"
) (
    input  wire        clk,
    input  wire        rst,
    input  wire        cfg_we,
    input  wire [6:0]  cfg_addr,
    input  wire [31:0] cfg_data,
    input  wire        cfg_start,          // pulse: (re)initialise run state from the configuration
    input  wire        in_valid,
    input  wire signed [15:0] in_x,
    output wire        in_ready,
    output reg         out_valid,
    output reg  signed [15:0] out_y,
    output reg  [31:0] clip_count
);
    // ------------------------------------------------------------------ configuration words
    reg [31:0] cfg [0:79];
    always @(posedge clk) if (cfg_we) cfg[cfg_addr] <= cfg_data;

    localparam W_Q = 0, W_OFF = 1, W_SEEDW = 2, W_SEEDP = 6, W_SEEDD = 10, W_DK = 14, W_NM = 15,
               W_PH = 16, W_INC = 23, W_TERMS = 30, W_FLAGS = 72;
    // products (2 words of 4 term bytes each)
    localparam P_WHITE = 0, P_PINK = 1, P_DRIFT = 2, P_GAIN = 3, P_MAINS = 4, P_HP = 11, P_LP = 16;
    wire [3:0] q_shift  = cfg[W_Q][3:0];
    wire [4:0] clip_sh  = cfg[W_Q][12:8];                  // clip_code = 2^clip_sh
    wire signed [31:0] offset_i = cfg[W_OFF];
    wire [5:0] drift_k  = cfg[W_DK][5:0];
    wire [2:0] n_mains  = cfg[W_NM][2:0];
    wire f_hp = cfg[W_FLAGS][0], f_lp = cfg[W_FLAGS][1], f_white = cfg[W_FLAGS][2], f_pink = cfg[W_FLAGS][3],
         f_drift = cfg[W_FLAGS][4], f_gain = cfg[W_FLAGS][5];

    // ------------------------------------------------------------------ sine ROM (round(32767 sin(2 pi i/4096)))
    reg signed [15:0] sin_rom [0:4095];
    initial $readmemh(SIN_HEX, sin_rom);
    reg [11:0] rom_addr;
    reg signed [15:0] rom_q;
    always @(posedge clk) rom_q <= sin_rom[rom_addr];

    // ------------------------------------------------------------------ xoroshiro128+ streams: 0 white, 1 pink, 2 drift
    reg [63:0] s0 [0:2];
    reg [63:0] s1 [0:2];
    function [63:0] rotl64; input [63:0] x; input integer k; begin rotl64 = (x << k) | (x >> (64 - k)); end endfunction

    // ------------------------------------------------------------------ run state
    reg [31:0] n_done;                    // samples processed since cfg_start
    reg [31:0] phase [0:6];
    reg signed [63:0] held [0:15];        // Voss rows
    reg signed [63:0] pink_total;
    reg signed [63:0] drift_d;            // 8 extra fractional bits
    reg signed [63:0] hx1, hx2, hy1, hy2, he1, he2;   // HP biquad
    reg signed [63:0] lx1, lx2, ly1, ly2, le1, le2;   // LP biquad
    reg pink_init_done;

    // ------------------------------------------------------------------ datapath registers
    reg signed [63:0] v, acc, opnd, prod, z;
    reg [5:0] state, ret;                 // ret: state to return to after GAUSS / PROD
    reg [3:0] gcnt;                       // Gaussian step counter
    reg [1:0] gstream;
    reg signed [63:0] gacc;
    reg [4:0] prod_id;
    reg [3:0] tcnt;                       // product term counter (0..7)
    reg [2:0] h;                          // mains harmonic / biquad coefficient index
    reg [3:0] row, init_row;              // Voss rows
    reg bq_sec;                           // biquad section: 0 = HP, 1 = LP

    localparam S_IDLE = 0,
               S_M_ADDR = 1, S_M_WAIT = 2, S_M_PROD = 3, S_M_FIN = 4,
               S_OFF = 5,
               S_D_G = 6, S_D_P = 7, S_D_F = 8,
               S_W_G = 9, S_W_P = 10, S_W_F = 11,
               S_PI_CHK = 12, S_PI_P = 13, S_PI_F = 14,
               S_PU_CHK = 15, S_PU_P = 16, S_PU_F = 17, S_P_ADD = 18,
               S_G_S = 19, S_G_F = 20,
               S_BQ_S = 21, S_BQ_P = 22, S_BQ_END = 23,
               S_QUANT = 24,
               S_GAUSS = 30, S_PROD = 31;

    assign in_ready = (state == S_IDLE);

    // term byte k (0..7) of product p: valid bit 7, negative bit 6, shift 5:0; terms packed from k = 0
    function [7:0] term_of; input [4:0] p; input [3:0] k; reg [31:0] w; begin
        w = cfg[W_TERMS + 2 * p + (k >> 2)];
        term_of = w[8 * (k & 3) +: 8];
    end endfunction

    // count trailing zeros of a 32-bit value (32 if zero)
    function [5:0] ctz32; input [31:0] x; integer i; reg found; begin
        ctz32 = 6'd32; found = 0;
        for (i = 0; i < 32; i = i + 1) if (!found && x[i]) begin ctz32 = i[5:0]; found = 1; end
    end endfunction

    // round(p / 2^24): the rounding shift of every signed-power-of-two product (impair._scale)
    function signed [63:0] rnd24; input signed [63:0] p; begin rnd24 = (p + (64'sd1 <<< 23)) >>> 24; end endfunction

    wire signed [63:0] bq_x1 = bq_sec ? lx1 : hx1, bq_x2 = bq_sec ? lx2 : hx2,
                       bq_y1 = bq_sec ? ly1 : hy1, bq_y2 = bq_sec ? ly2 : hy2,
                       bq_e1 = bq_sec ? le1 : he1, bq_e2 = bq_sec ? le2 : he2;
    localparam signed [63:0] SAT_HI = (64'sd1 <<< 47) - 1, SAT_LO = -(64'sd1 <<< 47);

    integer i;
    reg [5:0] r_ctz;
    reg [63:0] rr, s_x;
    reg signed [63:0] code, half, vq, e_new, sat_v, val, dn;
    reg [7:0] t;

    // start helpers (used as statements inside the FSM)
    task start_gauss; input [1:0] stream; input [5:0] back; begin
        gstream <= stream; gcnt <= 0; gacc <= 0; ret <= back; state <= S_GAUSS;
    end endtask
    task start_prod; input signed [63:0] operand; input [4:0] pid; input [5:0] back; begin
        opnd <= operand; prod_id <= pid; tcnt <= 0; prod <= 0; ret <= back; state <= S_PROD;
    end endtask

    always @(posedge clk) begin
        out_valid <= 1'b0;
        if (rst) begin
            state <= S_IDLE; n_done <= 0; clip_count <= 0; pink_init_done <= 0;
        end else if (cfg_start) begin
            state <= S_IDLE; n_done <= 0; clip_count <= 0; pink_init_done <= 0; init_row <= 0;
            for (i = 0; i < 3; i = i + 1) begin
                s0[i] <= {cfg[W_SEEDW + 4 * i + 1], cfg[W_SEEDW + 4 * i]};
                s1[i] <= {cfg[W_SEEDW + 4 * i + 3], cfg[W_SEEDW + 4 * i + 2]};
            end
            for (i = 0; i < 7; i = i + 1) phase[i] <= cfg[W_PH + i];
            for (i = 0; i < 16; i = i + 1) held[i] <= 0;
            pink_total <= 0; drift_d <= 0;
            hx1 <= 0; hx2 <= 0; hy1 <= 0; hy2 <= 0; he1 <= 0; he2 <= 0;
            lx1 <= 0; lx2 <= 0; ly1 <= 0; ly2 <= 0; le1 <= 0; le2 <= 0;
        end else begin
            case (state)
            S_IDLE: if (in_valid) begin
                v <= $signed({{48{in_x[15]}}, in_x}) <<< 4;
                h <= 0;
                state <= S_M_ADDR;
            end
            // ---------------- mains: v += round(sin[phase >> 20] * c_h / 2^24); phase += inc  (h = 0 .. n_mains-1)
            S_M_ADDR: if ({1'b0, h} < {1'b0, n_mains}) begin rom_addr <= phase[h][31:20]; state <= S_M_WAIT; end
                      else state <= S_OFF;
            S_M_WAIT: state <= S_M_PROD;                            // ROM read latency
            S_M_PROD: begin
                phase[h] <= phase[h] + cfg[W_INC + h];
                start_prod($signed({{48{rom_q[15]}}, rom_q}), P_MAINS + {2'b0, h}, S_M_FIN);
            end
            S_M_FIN: begin v <= v + rnd24(prod); h <= h + 1; state <= S_M_ADDR; end
            // ---------------- offset
            S_OFF: begin v <= v + $signed({{32{offset_i[31]}}, offset_i}); state <= S_D_G; end
            // ---------------- drift (Ornstein-Uhlenbeck): d = d - round(d / 2^k) + (w << 8); v += round(d / 2^8)
            S_D_G: if (f_drift) start_gauss(2, S_D_P); else state <= S_W_G;
            S_D_P: start_prod(z, P_DRIFT, S_D_F);
            S_D_F: begin
                half = 64'sd1 <<< (drift_k - 1);
                dn = drift_d - ((drift_d + half) >>> drift_k) + (rnd24(prod) <<< 8);
                drift_d <= dn;
                v <= v + ((dn + 64'sd128) >>> 8);
                state <= S_W_G;
            end
            // ---------------- white: v += round(z * c / 2^24)
            S_W_G: if (f_white) start_gauss(0, S_W_P); else state <= S_PI_CHK;
            S_W_P: start_prod(z, P_WHITE, S_W_F);
            S_W_F: begin v <= v + rnd24(prod); state <= S_PI_CHK; end
            // ---------------- pink (Voss-McCartney): 16 rows initialised before the first sample, then row
            //                  ctz(n+1) takes a new value when ctz(n+1) < 16; v += sum of the rows
            S_PI_CHK: if (!f_pink) state <= S_G_S;
                      else if (!pink_init_done) start_gauss(1, S_PI_P);
                      else state <= S_PU_CHK;
            S_PI_P: start_prod(z, P_PINK, S_PI_F);
            S_PI_F: begin
                val = rnd24(prod);
                held[init_row] <= val; pink_total <= pink_total + val;
                if (init_row == 4'd15) begin pink_init_done <= 1'b1; state <= S_PU_CHK; end
                else begin init_row <= init_row + 1; state <= S_PI_CHK; end
            end
            S_PU_CHK: begin
                r_ctz = ctz32(n_done + 1);
                if (r_ctz < 16) begin row <= r_ctz[3:0]; start_gauss(1, S_PU_P); end
                else state <= S_P_ADD;
            end
            S_PU_P: start_prod(z, P_PINK, S_PU_F);
            S_PU_F: begin
                val = rnd24(prod);
                pink_total <= pink_total + val - held[row];
                held[row] <= val;
                state <= S_P_ADD;
            end
            S_P_ADD: begin v <= v + pink_total; state <= S_G_S; end
            // ---------------- gain: v += round(v * c / 2^24)
            S_G_S: begin bq_sec <= 1'b0; if (f_gain) start_prod(v, P_GAIN, S_G_F); else state <= S_BQ_S; end
            S_G_F: begin v <= v + rnd24(prod); state <= S_BQ_S; end
            // ---------------- biquads, HP (bq_sec 0) then LP (bq_sec 1): direct form I, error feedback, F = 24
            //   acc = b0 x0 + b1 x1 + b2 x2 - a1 y1 - a2 y2 + 2 e1 - e2; y = acc >> 24 (floor); e1' = acc - (y << 24)
            S_BQ_S: begin
                if ((bq_sec == 1'b0 && f_hp) || (bq_sec == 1'b1 && f_lp)) begin
                    acc <= 2 * bq_e1 - bq_e2; h <= 0;
                    start_prod(v, (bq_sec ? P_LP : P_HP), S_BQ_P);
                end else if (bq_sec == 1'b0) bq_sec <= 1'b1;
                else state <= S_QUANT;
            end
            S_BQ_P: begin
                acc <= (h < 3) ? acc + prod : acc - prod;
                if (h == 3'd4) state <= S_BQ_END;
                else begin
                    h <= h + 1;
                    start_prod((h == 0) ? bq_x1 : (h == 1) ? bq_x2 : (h == 2) ? bq_y1 : bq_y2,
                               (bq_sec ? P_LP : P_HP) + {2'b0, h} + 5'd1, S_BQ_P);
                end
            end
            S_BQ_END: begin
                vq = acc >>> 24;
                e_new = acc - (vq <<< 24);
                sat_v = (vq > SAT_HI) ? SAT_HI : (vq < SAT_LO) ? SAT_LO : vq;
                if (bq_sec == 1'b0) begin
                    he2 <= he1; he1 <= e_new; hx2 <= hx1; hx1 <= v; hy2 <= hy1; hy1 <= sat_v;
                end else begin
                    le2 <= le1; le1 <= e_new; lx2 <= lx1; lx1 <= v; ly2 <= ly1; ly1 <= sat_v;
                end
                v <= sat_v;
                if (bq_sec == 1'b0) begin bq_sec <= 1'b1; state <= S_BQ_S; end else state <= S_QUANT;
            end
            // ---------------- clip and quantise: code = clip(round(v / 2^(q+4))), y = code << q
            S_QUANT: begin
                half = 64'sd1 <<< (q_shift + 3);
                code = (v + half) >>> (q_shift + 4);
                if (code > (64'sd1 <<< clip_sh) - 1) begin code = (64'sd1 <<< clip_sh) - 1; clip_count <= clip_count + 1; end
                else if (code < -(64'sd1 <<< clip_sh)) begin code = -(64'sd1 <<< clip_sh); clip_count <= clip_count + 1; end
                out_y <= code[15:0] << q_shift;
                out_valid <= 1'b1;
                n_done <= n_done + 1;
                state <= S_IDLE;
            end
            // ---------------- Gaussian: 16 xoroshiro128+ steps, four 12-bit fields each; z = 2*sum - 64*4095
            S_GAUSS: begin
                rr = s0[gstream] + s1[gstream];
                s_x = s1[gstream] ^ s0[gstream];
                s1[gstream] <= rotl64(s_x, 37);
                s0[gstream] <= rotl64(s0[gstream], 24) ^ s_x ^ (s_x << 16);
                gacc <= gacc + $signed({52'd0, rr[63:52]}) + $signed({52'd0, rr[51:40]})
                             + $signed({52'd0, rr[39:28]}) + $signed({52'd0, rr[27:16]});
                gcnt <= gcnt + 1;
                if (gcnt == 4'd15) begin
                    z <= 2 * (gacc + $signed({52'd0, rr[63:52]}) + $signed({52'd0, rr[51:40]})
                                   + $signed({52'd0, rr[39:28]}) + $signed({52'd0, rr[27:16]})) - 64'sd262080;
                    state <= ret;
                end
            end
            // ---------------- constant product: prod = sum of +-(opnd << shift) over the valid terms
            S_PROD: begin
                t = term_of(prod_id, tcnt);
                if (t[7]) prod <= t[6] ? prod - (opnd <<< t[5:0]) : prod + (opnd <<< t[5:0]);
                tcnt <= tcnt + 1;
                if (tcnt == 4'd7 || !t[7]) state <= ret;
            end
            default: state <= S_IDLE;
            endcase
        end
    end
endmodule
