# LEARN: concepts for the interview

One entry per concept we use: what it is in plain words, the one equation that matters, and a likely interview
question with an answer you can give. Numbers come from our own runs (marked with their source) or from the
equation itself. Entries are added as each phase uses them.

---

## Phase 0

### 1. Golden model and bit-exact verification
**Plain words.** Before building a hardware block, write a slow, simple software model of it, the "golden model".
Then feed both the same inputs and compare every output word. Equal on all inputs means the hardware does what the
software does; a single differing bit means a bug.
**Equation.** Pass if y_hw[n] == y_golden[n] for every n (exact integer equality, no tolerance).
**Our numbers.** SeizeLUT's classifier RTL equals its golden model on 431,960 windows. In the cloud on 15 Nov the
quick check passed 848 window checks and 3,592 injected faults with 0 mismatches (`ms/REPO_MAP.md` §4).
**Q: Why integers and exact equality, not "close enough"?** A: The detector's decisions are thresholds on
integers. A tolerance would hide off-by-one bugs that flip comparator bits. Integer arithmetic makes the hardware
reproducible bit for bit, so any difference is a real bug.

### 2. Thermometer encoding (where the comparators are)
**Plain words.** Each feature x is compared with a few fixed thresholds. Each comparison gives one bit, and the
pattern of bits ("thermometer") says which interval x falls in. The LUT network only sees these bits.
**Equation.** b_i = 1 if x > t_i else 0, with t_1 < t_2 < ... < t_m.
**Our numbers.** 146 comparators on 38 features (`export/n4_distill_s0/thresholds.json`).
**Q: Why does this matter for analog design?** A: A comparator with input offset V_os behaves like a comparator
with threshold t + V_os. Phase 2 asks how large a random offset per comparator the network tolerates, which sets
the comparator's size and energy.

### 3. PDK, process corners and mismatch
**Plain words.** A PDK (process design kit) is the foundry's description of its transistors: SPICE models, layout
rules, extraction rules. Process **corners** (tt, ff, ss, fs, sf) are whole-wafer shifts: all NMOS fast or slow
together. **Mismatch** is the random difference between two transistors drawn identically side by side. Corners
move everything together; mismatch makes neighbours differ. In SKY130 the library section `tt` is the typical corner
without mismatch and `tt_mm` the typical corner with mismatch switched on.
**Q: Which one sets a comparator's offset?** A: Mismatch. A global corner shift moves both input transistors of a
differential pair equally and cancels; only the random difference between them creates offset.

### 4. SPICE analyses: operating point, DC sweep, transient
**Plain words.** `op` solves the circuit's DC bias. `dc` repeats that while sweeping a source (gives transfer
curves). `tran` integrates over time (gives delays and waveforms). ngspice is the open-source SPICE we use.
**Our numbers** (SKY130A tt, 27 C, 1.8 V; `ms/analog/smoke/`): NMOS W/L = 1/0.15 um at VGS = VDS = 1.8 V conducts
501 uA; PMOS W/L = 2/0.15 um conducts 403 uA.
**Q: Why does the PMOS, twice as wide, still give less current?** A: Holes have lower mobility than electrons. In
this process a 2x wider PMOS gives about 0.8x the NMOS current (403/501).

### 5. Inverter switching threshold and delay
**Plain words.** The switching threshold V_M is the input voltage where the output equals the input. It sits below
VDD/2 if the pull-down (NMOS) is stronger than the pull-up. Delay is the time to (dis)charge the load through the
transistor's current.
**Equation.** t_p ~ C_L * (VDD/2) / I_avg (charge to move divided by average current).
**Our numbers.** V_M = 0.870 V (below 0.9 V, since the NMOS is stronger); t_pHL = 36.0 ps and t_pLH = 43.3 ps into 10 fF.
**Q: Why is t_pLH > t_pHL?** A: Rising output is driven by the weaker PMOS (403 uA vs 501 uA).

### 6. Monte Carlo mismatch and Pelgrom's law (preview of Phase 2)
**Plain words.** Monte Carlo draws many random "chips", each with new mismatch values, and simulates each. The
spread of the result (e.g. the offset of a matched pair) shows how precise the circuit is. Pelgrom found that
the mismatch spread shrinks with the square root of the transistor area: four times the area halves the offset.
**Equation (Pelgrom et al., JSSC 1989).** sigma(Delta V_T) = A_VT / sqrt(W * L), where Delta V_T is the difference between
the two transistors of a pair and A_VT is a process constant (mV*um).
**Our first number (rough).** Two NMOS W/L = 1/0.5 um at 10 uA, 40 Monte Carlo samples: sigma(Delta V_GS) = 9.5 mV
(`ms/analog/smoke/expected.json`). If it were all threshold mismatch, A_VT ~ 9.5 mV * sqrt(0.5 um^2) ~ 6.7 mV*um.
That is only an illustration: 40 samples carry about +-11 % sampling uncertainty, and Delta V_GS also contains
current-factor mismatch. Phase 2 measures it properly over many sizes.
**Q: You need 4x less offset. What does it cost?** A: 16x the gate area (sigma ~ 1/sqrt(area)), so more input
capacitance, so more energy per comparison and more kickback. That is the trade Phase 2 quantifies.

### 7. Quantisation noise and SQNR
**Plain words.** An ADC rounds the signal to steps of size q (the LSB). The rounding error behaves like noise,
uniformly spread over +-q/2.
**Equation.** quantisation noise rms = q / sqrt(12); for a full-scale sine, SQNR = 6.02 N + 1.76 dB (N bits).
**Our numbers.** The pipeline's grid is q = 0.25 uV, so the quantisation noise is 0.072 uV rms. The median EEG channel
RMS in SeizeIT2 is 9.9 uV (`results/audit/signal_channels.csv`), so the grid is far finer than the signal.
**Q: Why not just say "16 bits"?** A: Bits mean nothing without the full-scale range. The detector cares about the
input-referred step q (uV) and the clipping level C. A front end sets C with its gain and N with its ADC, and
N = log2(2C/q).

### 8. Aliasing
**Plain words.** Sampling at f_s cannot tell a tone at f from one at |f - k f_s|. Anything above f_s/2 that is not
filtered out before the ADC folds back into the band.
**Equation.** f_alias = |f - round(f/f_s) * f_s|.
**Our numbers.** At f_s = 256 Hz, the 250 Hz mains harmonic appears at **6 Hz**, inside the theta band that 7 of
the detector's 38 features (30 of 146 comparators) read. The digital 50 Hz notch cannot remove it.
**Q: How do you protect the detector?** A: With an analog anti-alias low-pass in front of the ADC, specified to
attenuate 250 Hz enough. Phase 1 measures what "enough" is for this detector.

---

## Phase 1 (preview; equations checked, values to be read from the papers in Phase 1)

### 9. Input-referred noise, density and rms
**Plain words.** Amplifier noise is quoted as if it were added at the input, so it compares directly with the
signal. White noise is described by its density e_n (V/sqrt(Hz)); the rms over a band grows with the square root
of the bandwidth.
**Equation.** v_rms = e_n * sqrt(BW) (white noise).
**Example.** 1 uV rms over 100 Hz is 100 nV/sqrt(Hz).
**Q: Why does the signal band matter for the noise spec?** A: Halving the bandwidth lowers the rms noise by
sqrt(2) for free. So the front end's band should be as narrow as the detector allows, which Phase 1 measures.

### 10. Noise efficiency factor (NEF)
**Plain words.** It measures how much supply current an amplifier spends for its noise level, relative to an ideal
single bipolar transistor (NEF = 1). Lower is better.
**Equation (Steyaert & Sansen 1987; form as used in later work).** NEF = v_ni,rms * sqrt( 2 I_tot / (pi * U_T * 4kT * BW) ),
with v_ni,rms the input-referred rms noise, I_tot the total supply current, U_T = kT/q the thermal voltage, BW the bandwidth.
Solved for current: I_tot = NEF^2 * pi * U_T * 4kT * BW / (2 v_ni,rms^2), so **current ~ 1/noise^2**.
**Q: Halving the noise costs how much power?** A: Four times the current at the same NEF. The input transistor's
thermal noise power falls as 1/g_m, and g_m is proportional to current at best (weak inversion).

### 11. ADC figures of merit (Walden and Schreier)
**Plain words.** Both normalise ADC power by speed and resolution, so designs of different specs can be compared.
**Equations (as computed in the cells of Murmann's ADC survey).**
FOM_W = P / (f_snyq * 2^ENOB) (J per conversion step), with ENOB = (SNDR - 1.76)/6.02;
FOM_S = SNDR + 10 log10( (f_snyq/2) / P ) (dB), with f_snyq = f_s / OSR.
**Q: Why two FOMs?** A: Walden assumes power doubles per extra bit; Schreier assumes 4x per bit (6 dB of SNDR),
which is what thermal noise demands. So FOM_W suits low-resolution designs and FOM_S high-resolution ones (Murmann's
survey readme makes the same point).

### 12. Gain error on a log-domain feature
**Plain words.** Most of SeizeLUT's compared features are log2 of signal sums with 3 fractional bits. Multiplying
the signal by (1 + eps) adds log2(1 + eps) to such a feature.
**Equation.** Delta feature = log2(1 + eps) * 8 LSB.
**Example.** eps = 4.4 % shifts the feature by 0.5 LSB. Features relative to a running baseline (`_ctx`) should
cancel a constant gain error (to be tested in Phase 1).
**Q: Which analog error is the detector likely most robust to?** A: Constant gain error, for the baseline-relative
features. Phase 1 tests this rather than assuming it.

### 13. Gaussian noise in hardware, and why the variance is not enough
**Plain words.** Hardware random generators give uniform bits. Adding n uniform numbers gives an approximately
Gaussian number (central limit theorem). The sum has the right mean and variance for any n, but its tails converge
slowly: it can never exceed sqrt(3n) sigma, and big excursions are too rare. A generator validated only by its
variance can be badly wrong where it matters for rare events.
**Equation.** Sum of n uniforms on [0, 1): mean n/2, variance n/12, support +-sqrt(3n) sigma, excess kurtosis -6/(5n).
**Our numbers** (exact convolution, LOG L12). Share of the true Gaussian's probability beyond 4 sigma:
41 % for n = 16, 83 % for n = 64, 96 % for n = 256. We use n = 64 (16 steps of xoroshiro128+, four 12-bit fields each).
The uniform source is checked bit-exact against an independent implementation (randomgen) and the sum against
its exact distribution. A software-only A/B run with an exact Gaussian will show whether the tail deficit changes any
detection result.
**Q: How would you validate a hardware noise generator?** A: Three levels. (1) The uniform source equals a
reference implementation bit for bit. (2) The output distribution matches its exact theoretical distribution
(CDF and tails, not just mean and variance). (3) The effect of its known deviation from the ideal on the actual
application is measured with an A/B run against an ideal generator.

### 14. 1/f (flicker) noise and the Voss-McCartney generator
**Plain words.** Amplifier noise has a white part and a 1/f part that dominates below the corner frequency f_c.
Voss-McCartney makes 1/f noise by summing random values that are held for 2, 4, 8, ... samples. Each held row
covers one octave, and together they give a roughly 1/f spectrum with only adders and registers.
**Equation.** Noise PSD S(f) = S_white (1 + f_c / f).
**Our numbers.** Our 16-row generator follows 1/f within about +-5 % from fs/8192 to fs/64 (0.03-4 Hz at 256 Hz),
and is 8 % and 20 % low in the two octaves below fs/8 (measured, `impair.py`).
**Q: Why does 1/f noise matter more for EEG than for audio?** A: EEG's useful band starts near 0.5 Hz, where 1/f
noise is largest. CMOS amplifiers often have 1/f corners of tens of Hz or more unless chopped.

### 15. Co-verification with a negative control
**Plain words.** Comparing RTL against a golden model only proves something if the comparison can fail. A
negative control deliberately breaks one thing and checks that the comparison reports it.
**Our numbers.** The emulator RTL equals `impair.py` on 11 configurations x 70,000 samples (0 mismatches, equal clip
counts); flipping one bit of one noise seed gives 65,702 mismatches (`ms/results/phase1/impair_rtl_check.json`).
**Q: Your testbench says 0 mismatches. How do you know it works?** A: Because a corrupted configuration makes it
report mismatches. Also because each case reports how many samples the impairment actually changed: an impairment that
changes nothing would "match" trivially.

### 16. ADC power at 256 samples per second: where FOM scaling stops working
**Plain words.** A figure of merit says how much energy a converter spends per conversion step. Multiplying it by
our tiny rate (256 S/s) predicts picowatts. Real converters at low rates do not get there, because their static
power (bias currents, references, leakage) does not scale down with the clock. Also, a FOM is only comparable
between designs of similar resolution: the Schreier FOM grows with SNDR, so a 120 dB champion's FOM says nothing about
a 50 dB converter.
**Our numbers** (`python ms/py/adc_power.py`, Murmann survey rev 20260801, 763 designs; FOM population = designs
within 20 dB above the required SNDR). At 60 dB SNDR and fsnyq = 256 Hz: best-Walden scaling 0.13 nW, best-Schreier
0.03 nW; the lowest-power design in the survey with fsnyq <= 20 kHz that reaches 60 dB uses 180 nW (ISSCC 2018, 17.3, at
6 kHz). At 48 dB the lowest is 2.7 nW (ISSCC 2017, 21.6, at 1 kS/s).
**Why it matters here.** A biopotential amplifier needs microwatts per channel (item 10). Even the measured low-rate
floor puts the ADC well below that, so the detector's noise tolerance, not its resolution tolerance, is what sets
front-end power. To be confirmed with the measured tolerance limits.
**Q: Your ADC power estimate is 30 pW. Do you believe it?** A: No. It is a FOM extrapolated down to a rate where
static power dominates; I quote the lowest power that a real low-rate design has achieved beside it.
