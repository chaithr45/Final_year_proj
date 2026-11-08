## 2.4 LUT-native, weightless and logic networks

**Weightless neural networks.** A weightless network replaces weighted sums with memory lookups. WiSARD
[@aleksander1984wisard] split a binary input into small tuples, each addressing a RAM node, with one discriminator
per class whose score is the number of RAM nodes that fire. Such networks are trained by writing tables, not by
gradient descent, and their inputs must already be binary. BTHOWeN [@susskind2022bthowen] added Bloom filters,
hashing and a Gaussian thermometer encoding of continuous inputs, with an FPGA accelerator; ULEEN
[@susskind2023uleen] borrowed training techniques from binarised networks and reported 3.6 times the area-normalised
throughput and 7.1 times the energy efficiency of a FINN binarised network on FPGA (abstract).

**Differentiable Weightless Neural Networks** (DWN) [@bacellar2024dwn] made the lookup tables themselves trainable
end to end: thermometer-encoded inputs, LUT layers trained with an Extended Finite Difference gradient, and a
learnable input mapping that decides which bits each LUT reads. The authors report better latency, throughput,
energy and area than earlier FPGA designs, and better accuracy than XGBoost on a microcontroller under tight memory
limits. DWNs have since been applied to wearable inertial human-activity recognition [@bacellar2025nanoml], reaching
96.3–96.7 % accuracy at 56–104 nJ per sample (abstract), and to continuous control with thermometer-encoded sensor
inputs compiled to FPGA logic [@kresse2025dwc]. The DWN is the base model of this project.

**Logic-gate networks.** Deep Differentiable Logic Gate Networks (LGN) [@petersen2022dlgn] learn, for every neuron,
which of the 16 two-input Boolean functions to compute, and after training run as pure logic (over a million MNIST
images per second on one CPU core, abstract). Convolutional LGNs [@petersen2024convdlgn] reach about 86 % on
CIFAR-10 with tens of millions of gates; Light LGNs [@ruttgers2026lightdlgn] reduce the parameters of higher-fan-in
gates; a recurrent LGN [@buhrer2025rdlgn] is the only stateful logic network we found, evaluated on machine
translation (5.00 BLEU against 5.41 for a GRU on WMT'14 English–German, abstract).

**LUT-based networks for FPGAs.** LUTNet [@wang2019lutnet] replaced the XNOR operations of binarised networks with
trainable K-input LUTs, roughly doubling area efficiency. LogicNets [@umuroglu2020logicnets] trains sparse networks
with few-bit activations so that every neuron can be enumerated as a truth table and synthesised directly into FPGA
logic, with latencies below 15 ns; its cost grows exponentially with fan-in, which keeps fan-in tiny. PolyLUT
[@andronic2023polylut] lets each LUT neuron compute a polynomial of its inputs, and NeuraLUT [@andronic2024neuralut]
hides a small dense sub-network inside each LUT (up to 4.3 times lower latency at equal accuracy, abstract).
AmigoLUT [@weng2025amigolut] scales LUT networks through ensembles, and ReducedLUT [@cassidy2025reducedlut] compresses
the tables by treating input patterns never seen in training as "don't care" (up to 1.63 times fewer LUTs, abstract),
an assumption that is risky when a new patient produces patterns the training patients did not. TreeLUT
[@khataei2025treelut] maps quantised gradient-boosted trees into LUT-only logic with 4–101 times lower area-delay
product than recent LUT networks (abstract); we use it as a strong non-neural LUT baseline.

**The cost of the encoder.** Mecik and Kumm [@mecik2025thermo] built a complete DWN hardware generator and found that
the thermometer encoder can raise LUT usage by up to 3.2 times and dominates the cost of small networks. Our own cost
estimate agrees: in our 50-LUT base model the encoder accounts for about 850 of about 960 LUTs (Chapter 4), which
is why we treat encoder design (N2) as a first-class question.

**LUT and logic networks on biosignals.** Three recent works come closest to ours. Mommen et al.
[@mommen2026ecg] classified ECG arrhythmias inter-patient with LGNs and LUT networks, up to 94.3 % accuracy on
MIT-BIH with 2,000–2,990 LUTs on an Artix-7 FPGA (about 5–7 mW, estimated). Dharia et al. [@dharia2026eeglgn]
applied LGNs to EEG classification (dementia and emotion) on an embedded CPU. The only weightless network applied to
seizures is a WiSARD model for seizure anticipation evaluated on 4 patients with accuracy as the only metric
[@deaguiar2015wisard].

| Work | Year | Model | Domain | Hardware / result (as reported) | Gap for our problem |
|---|---|---|---|---|---|
| WiSARD [@aleksander1984wisard] | 1984 | RAM-node weightless net | images | — | no gradient training, binary inputs |
| BTHOWeN [@susskind2022bthowen] | 2022 | weightless + Bloom filters | tabular, MNIST | FPGA accelerator | counting-based training, static |
| ULEEN [@susskind2023uleen] | 2023 | weightless | MLPerf Tiny | 7.1× energy efficiency vs FINN | no biosignals |
| DWN [@bacellar2024dwn] | 2024 | differentiable LUT6 network | tabular | FPGA, MCU | stateless; no biosignal events |
| nanoML HAR [@bacellar2025nanoml] | 2025 | DWN | wearable inertial HAR | 56–104 nJ / sample | single modality, no rare events |
| LGN [@petersen2022dlgn] | 2022 | 2-input logic gates | images | >1 M images/s on CPU | random connections, no biosignals |
| Recurrent LGN [@buhrer2025rdlgn] | 2025 | stateful logic gates | translation | — | not biosignals, no hardware |
| LogicNets [@umuroglu2020logicnets] | 2020 | sparse quantised LUT net | jet tagging, NID | < 15 ns latency | tiny fan-in, static |
| NeuraLUT [@andronic2024neuralut] | 2024 | dense sub-nets in LUTs | jet tagging, MNIST | 4.3× lower latency | static |
| TreeLUT [@khataei2025treelut] | 2025 | quantised GBDT in LUTs | tabular, MNIST | 4–101× lower area-delay | static per-window |
| Mecik & Kumm [@mecik2025thermo] | 2025 | DWN hardware generator | jet tagging | encoder up to 3.2× LUTs | — |
| Mommen et al. [@mommen2026ecg] | 2026 | LGN, LUT network | ECG arrhythmia | 2.0–3.0k LUTs, 5–7 mW (est.) | single modality, beat-level |
| Dharia et al. [@dharia2026eeglgn] | 2026 | LGN | EEG (dementia, emotion) | embedded CPU | no FPGA, no seizures |
| de Aguiar et al. [@deaguiar2015wisard] | 2015 | WiSARD | seizure anticipation, 4 patients | — | accuracy only, tiny cohort |

**Gap.** We found no differentiable LUT-native or logic-gate seizure detector. Every LUT, weightless or logic network
we found is single-modality and stateless (except one recurrent LGN for language), none handles a missing sensor,
and only one [@mommen2026ecg] tests generalisation to unseen patients. The encoder's hardware cost is rarely
reported, although it dominates small networks.
