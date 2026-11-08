## 2.5 Hardware seizure detectors and efficient inference

**ASICs.** The first micro-power seizure-detection chips put the analogue front end and feature extraction on chip:
Verma et al. [@verma2010micro] extracted spectral EEG features at 9 µJ per feature vector and sent them to a central
classifier, which cut system power 14 times by avoiding raw-EEG transmission. Later systems-on-chip ran the
classifier too: a 16-channel patient-specific SVM chip at 2.73 µJ per classification [@altaf2015jssc], a non-linear
SVM chip at 1.83 µJ per classification [@altaf2016tbcas], and an SVM processor with on-chip learning at 1.9 mW
[@huang2020jssc]. Tree-based classifiers proved particularly cheap: gradient-boosted trees on intracranial EEG at
41.2 nJ per classification [@shoaran2018jetcas], and the NeuralTree chip at 0.227 µJ per classification across
256 channels [@shin2022neuraltree]. Trees only compare and add, which is also why they map well to lookup tables.

**FPGAs.** FPGA detectors include an STFT + SVM design on a Zynq-7000 at 380 mW of programmable-logic power
[@wang2018access], SVM training and classification on a Virtex-7 [@elhosary2019tbcas], a patient-specific iEEG
detector on a Cyclone V at 0.49 mW dynamic power [@razi2022tbcas], an ultra-low-complexity line-length detector
[@vittimberga2025sensors], and a spiking neural network on a small Lattice iCE40UP5K [@busia2025fpga], which reported
4.55 nJ and 0.5 µs per inference with 0.3 false positives per hour on CHB-MIT using four temporal EEG channels.
The last is the closest to our Phase 2 target: a low-cost FPGA and few channels near the ear.

**Microcontrollers.** e-Glass [@sopic2018eglass] put four EEG electrodes in a glasses frame and ran detection on an
embedded processor for 2.71 days per charge. EEGformer [@busia2024eegformer] ran a compact transformer on temporal
EEG channels on GAP9 at 0.31 mJ per inference and detected 73 % of CHB-MIT seizures at 0.15 false positives per
hour. BrainFuseNet [@ingolfsson2024brainfusenet] fused EEG, PPG and accelerometry on the same microcontroller at
0.11 mJ per inference. Tree-based EEG artefact detection on a low-power processor [@ingolfsson2022artifact] and the
BioWolf ExG platform [@kartsch2019biowolf] show the same push towards wearable, always-on processing.

**Tools for efficient inference.** Binarised neural networks [@hubara2016bnn] reduce weights and activations to one
bit; FINN [@umuroglu2017finn] compiles them into streaming FPGA dataflow (up to 12.3 million MNIST classifications
per second); integer-only quantisation [@jacob2018quant] made 8-bit inference standard; hls4ml
[@duarte2018hls4ml] translates trained networks into FPGA firmware with latencies around 100 ns for particle-physics
triggers. Quantised networks still need integer multipliers (FPGA DSP blocks); our INT8 MLP baseline represents this
approach.

| Work | Year | Platform | Signals | Hardware (as reported) | Detection (as reported) | Gap for our problem |
|---|---|---|---|---|---|---|
| Verma et al. [@verma2010micro] | 2010 | ASIC | scalp EEG | 9 µJ / feature vector | classifier off-chip | EEG only |
| Bin Altaf et al. [@altaf2015jssc] | 2015 | ASIC | scalp EEG | 2.73 µJ / class. | 95.7 % sens., epoch-level | patient-specific |
| Shoaran et al. [@shoaran2018jetcas] | 2018 | ASIC | iEEG | 41.2 nJ / class. | F1 87.9 % (block split) | implant, per patient |
| NeuralTree [@shin2022neuraltree] | 2022 | ASIC | EEG, iEEG | 0.227 µJ / class. | 95.6 % sens. (EEG) | neural signals only |
| Wang et al. [@wang2018access] | 2018 | FPGA (Zynq) | scalp EEG | 380 mW | 98.4 %, 0.356 FD/h | per patient, high power |
| Farhang Razi & Schmid [@razi2022tbcas] | 2022 | FPGA (Cyclone V) | iEEG | 0.49 mW dynamic | 100 % sens. | per patient, implant |
| Busia et al. [@busia2025fpga] | 2025 | FPGA (iCE40UP5K) | scalp EEG, 4 ch | 4.55 nJ / inference | 0.3 FP/h | EEG only, CHB-MIT |
| e-Glass [@sopic2018eglass] | 2018 | MCU | scalp EEG, 4 ch | 2.71 days / charge | 93.8 % sens. (epoch) | EEG only |
| EEGformer [@busia2024eegformer] | 2024 | MCU (GAP9) | scalp EEG | 0.31 mJ / inference | 73 %, 0.15 FP/h | multipliers, EEG only |
| BrainFuseNet [@ingolfsson2024brainfusenet] | 2024 | MCU (GAP9) | EEG + PPG + ACC | 0.11 mJ / inference | 0.21 FP/h | multipliers, no ECG/EMG |

Hardware figures are reported in different units (per feature vector, per classification or per inference; dynamic
or total power), so they are not directly comparable; we will report energy and LUTs per decision at a fixed
decision rate (one per second) together with false alarms per 24 h.

**Gap.** Almost every hardware detector classifies EEG alone, mostly on paediatric scalp EEG (CHB-MIT) or implanted
electrodes, and most are trained per patient and report epoch-level metrics. None maps the whole classifier into FPGA
lookup tables, and none is evaluated on multimodal wearable recordings of unseen patients.
