# Literature survey, section C: LUT-native, weightless and logic networks

How this was checked (2026-11-08). Every entry below came up in WebSearch with a matching title, authors, venue and
year. The "Verified at" column gives the page whose search snippet confirmed it. Direct fetching was blocked in this
environment: proceedings.mlr.press, api.semanticscholar.org, dblp.org and api.crossref.org were refused by the network
proxy (one try each). Numbers in the "Hardware cost / result" column are quoted only when a search snippet of the
abstract or paper text showed them, and the column names the source. "-" means not verified.

The brief names 19 papers explicitly, and two DWN/LGN follow-ups (Light DLGN, nanoML HAR) were added, so the table
has 21 rows. To get down to 12-16, the least essential rows are LUTNet, AmigoLUT, ReducedLUT, Light DLGN and
nanoML-HAR; the gap argument does not depend on them.

## (a) Table

| Ref key | Authors (first author et al.) | Year | Title | Venue | Idea | Hardware cost / result (source) | Application domain | Limitation / gap relevant to our project | Verified at (URL) |
|---|---|---|---|---|---|---|---|---|---|
| aleksander1984wisard | Aleksander, Thomas, Bowden | 1984 | WISARD·a radical step forward in image recognition | Sensor Review 4(3):120-124 | RAM-node (n-tuple) weightless classifier: binary input tuples address RAM lookup tables; one discriminator per class; class score = count of firing RAMs | - (paywalled; only abstract seen) | Image recognition / industrial sorting | One-shot table writing, no gradient training, no learned input mapping; binary-image inputs, so there is no encoder for continuous features | https://www.emerald.com/insight/content/doi/10.1108/eb007637/full/html |
| susskind2022bthowen | Susskind et al. | 2022 | Weightless Neural Networks for Efficient Edge Inference (BTHOWeN) | PACT '22, pp. 279-290 | WiSARD + counting Bloom filters, H3 hashing, Gaussian non-linear thermometer encoding, bleaching; FPGA accelerator | Across 9 datasets: >40% lower error, >50% smaller models than prior WNNs; vs. MLP accelerators of similar accuracy ~80% less energy, ~85% lower latency (abstract via ISCTE repository / arXiv snippets) | Tabular/UCI, MNIST, edge inference | Still trained by counting (no backprop); static classifier; no biosignal or temporal task | https://repositorio.iscte-iul.pt/handle/10071/32038 ; https://arxiv.org/abs/2203.01479 |
| susskind2023uleen | Susskind et al. | 2023 | ULEEN: A Novel Architecture for Ultra Low-Energy Edge Neural Networks | ACM TACO 20(4), art. 61 | WNN with algorithmic changes and a training strategy adapted from BNNs to fix WNN accuracy and memory; FPGA accelerator | FPGA: 4.0-14.3 M inferences/s; vs. Xilinx FINN BNN 3.6x area-normalised throughput, 7.1x steady-state energy efficiency (abstract via ISCTE repository snippet) | MLPerf Tiny (4 datasets) + MNIST | Authors say it is "not universally applicable"; no physiological signals; static classifier | https://ciencia.iscte-iul.pt/publications/uleen-a-novel-architecture-for-ultra-low-energy-edge-neural-networks/98470 ; https://dl.acm.org/doi/10.1145/3629522 |
| bacellar2024dwn | Bacellar et al. | 2024 | Differentiable Weightless Neural Networks | ICML 2024, PMLR 235:2277-2295 | LUT layers trained end to end with Extended Finite Difference; Learnable Mapping, Learnable Reduction, Spectral Regularization; thermometer-encoded inputs | Abstract: better latency, throughput, energy efficiency and model area than state of the art on FPGA (Zynq Z-7045 per a review); better accuracy than XGBoost on a microcontroller under tight memory limits; average rank 2.5 vs XGBoost 3.4 / TabNet 3.6 on tabular data (search snippets of arXiv/PMLR text) | FPGA, MCU and ultra-low-cost-chip classification; tabular | Our base model. Stateless single-window classifier; not evaluated on biosignals or event-level detection; hardware cost of its thermometer encoding "not fully evaluated" (Mecik & Kumm 2025) | https://proceedings.mlr.press/v235/bacellar24a.html ; https://arxiv.org/abs/2410.11112 ; https://icml.cc/virtual/2024/poster/34511 |
| bacellar2025nanoml | Bacellar et al. | 2025 | nanoML for Human Activity Recognition | tinyML Research Symposium '25 (per paper's ACM reference format; arXiv comment says EDGE AI FOUNDATION Austin 2025) | DWNs applied to wearable-sensor HAR | 96.34% and 96.67% accuracy at 56 nJ and 104 nJ per sample; up to 926,000x energy and 260x memory reduction vs. SOTA deep models (arXiv abstract snippet) | Wearable inertial HAR | Closest DWN-on-wearable-signals work, but uses inertial signals only (single modality), with no rare-event detection and no clinical metrics | https://arxiv.org/abs/2502.12173 |
| kresse2025dwc | Kresse & Lampert | 2025 | Differentiable Weightless Controllers: Learning Logic Circuits for Continuous Control | arXiv:2512.01467 (ICML 2026 poster page exists) | Thermometer-encoded observations -> sparse Boolean LUT layers -> lightweight action heads; RL policies compiled to FPGA | Competitive returns on 4 of 5 MuJoCo tasks (HalfCheetah capacity-limited); Artix-7: 1-3 clock-cycle latency, nJ-level energy per action (arXiv abstract snippet) | Continuous control (RL) | Shows DWN+thermometer works on continuous real-valued sensor inputs; training cost much higher than deployment; per-step policy with no temporal memory | https://arxiv.org/abs/2512.01467 ; https://icml.cc/virtual/2026/poster/62491 |
| petersen2022dlgn | Petersen et al. | 2022 | Deep Differentiable Logic Gate Networks | NeurIPS 2022 (NeurIPS 35) | Each neuron is a 2-input gate; a softmax over the 16 relaxed Boolean functions is learned, then discretised | Discretised nets classify >1 M MNIST images/s on one CPU core (abstract via search snippet) | Image/tabular classification | 2-input gates with randomly chosen connections (the ConvDLGN abstract names this as the CIFAR-10 limit); speed reported as CPU throughput; no biosignals | https://proceedings.neurips.cc/paper_files/paper/2022/hash/0d3496dd0cec77a999c98d35003203ca-Abstract.html ; https://openreview.net/forum?id=vF3WefcoePW |
| petersen2024convdlgn | Petersen et al. | 2024 | Convolutional Differentiable Logic Gate Networks | NeurIPS 2024 (oral) | Logic-gate tree kernels, logical OR pooling, residual initialisation | CIFAR-10 86.29% with 61 M logic gates, 29x smaller than prior SOTA (arXiv/NeurIPS abstract; the poster page gives 86.38% / 111 M gates, a different configuration) | Image classification | Spatial (2-D) convolution, not temporal; gate counts are in the millions, too large for a small wearable FPGA | https://proceedings.neurips.cc/paper_files/paper/2024/hash/db988b089d8d97d0f159c15ed0be6a71-Abstract.html ; https://arxiv.org/abs/2411.04732 |
| buhrer2025rdlgn | Bührer et al. | 2025 | Recurrent Deep Differentiable Logic Gate Networks | arXiv:2508.06097 (preprint; no venue found) | Recurrent (stateful) LGN for sequence modelling | WMT'14 En-De: 5.00 BLEU, 30.9% accuracy during training vs GRU 5.41 BLEU; 4.39 BLEU at inference (arXiv abstract snippet) | Machine translation | Only recurrent logic network found; NLP not biosignals; no hardware numbers; no recurrent DWN/LUT-6 counterpart exists | https://arxiv.org/abs/2508.06097 |
| ruttgers2026lightdlgn | Rüttgers et al. | 2026 | Light Differentiable Logic Gate Networks | ICLR 2026 (arXiv:2510.03250) | Reparametrises logic-gate neurons so parameters grow logarithmically with gate fan-in | ~4x smaller model, up to 1.86x faster backward pass, 8.5x fewer training steps; CIFAR-100 accuracy stable (abstract snippet) | Image classification | Training-efficiency fix aimed at higher fan-in gates (relevant to 6-input LUTs), but no hardware or biosignal evaluation | https://proceedings.iclr.cc/paper_files/paper/2026/hash/6d8910336fe8a0eee83f2fa660347147-Abstract-Conference.html ; https://arxiv.org/abs/2510.03250 |
| wang2019lutnet | Wang et al. | 2019 | LUTNet: Rethinking Inference in FPGA Soft Logic | IEEE FCCM 2019, pp. 26-34 | Replace BNN XNORs with trainable K-input LUTs as inference operators, allowing heavier pruning | ~2x area efficiency vs. SOTA binarised implementation; 4-LUT area compression 2.08x (CNV/CIFAR-10) and 1.90x (AlexNet/ImageNet) (abstract snippet) | Image CNNs | Evaluated on large image CNNs (CNV, AlexNet), not ultra-small always-on detectors; no biosignals | https://arxiv.org/abs/1904.00938 ; https://spiral.imperial.ac.uk/entities/publication/5d8dbb87-0900-4d1d-8d7d-3451cfe1be49 |
| umuroglu2020logicnets | Umuroglu et al. | 2020 | LogicNets: Co-Designed Neural Networks and Circuits for Extreme-Throughput Applications | FPL 2020, pp. 291-297 | Sparse, few-bit quantised neurons enumerated as truth tables -> netlist -> pipelined FPGA circuit; fan-in cost model | <15 ns latency; hundreds of millions of inferences/s (abstract snippet) | High-energy physics jet tagging, network intrusion detection | LUT cost grows exponentially with neuron fan-in, so fan-in must stay tiny; no biosignal use | https://arxiv.org/abs/2004.03021 |
| andronic2023polylut | Andronic & Constantinides | 2023 | PolyLUT: Learning Piecewise Polynomials for Ultra-Low Latency FPGA LUT-based Inference | ICFPT 2023, pp. 60-68 | Each LUT neuron computes a multivariate polynomial of its inputs, so fewer soft-logic layers are needed | Inference ~10 ns (paper text snippet); latency reductions up to 2x / 19.38x / 3.57x on NID / jet tagging / MNIST at similar accuracy (CERN FastML workshop abstract, not the paper) | NID, LHC jet tagging, MNIST | Builds on LogicNets (equivalent at polynomial degree 1), so the fan-in limit remains; no temporal or biosignal tasks | https://arxiv.org/abs/2309.02334 ; https://indico.cern.ch/event/1283970/contributions/5550648 |
| andronic2024neuralut | Andronic & Constantinides | 2024 | NeuraLUT: Hiding Neural Network Density in Boolean Synthesizable Functions | FPL 2024, pp. 140-148 | Map a whole dense sub-network (with skip connections) into each L-LUT; sparsity/quantisation only between partitions | Up to 4.3x lower latency at equal accuracy vs prior work (abstract snippet) | Jet substructure tagging, MNIST | Hidden float sub-nets must be enumerated offline into tables; static classifier; no biosignals | https://arxiv.org/abs/2403.00849 |
| weng2025amigolut | Weng et al. | 2025 | Greater than the Sum of its LUTs: Scaling Up LUT-based Neural Networks with AmigoLUT | ACM/SIGDA FPGA '25, pp. 25-35 (pages per dblp snippet) | Ensembles of small LUT-NNs with a shared input quantiser and output requantisation; cost linear in ensemble size | Higher throughput with up to an order of magnitude fewer LUTs than the largest LUT-NNs (abstract via survey/slides snippets) | Jet tagging, MNIST and similar | Accuracy gains shrink as the ensemble grows; static classifiers | https://indico.cern.ch/event/1387540/contributions/6153611 ; https://dblp.org/pid/284/7960 |
| cassidy2025reducedlut | Cassidy et al. | 2025 | ReducedLUT: Table Decomposition with "Don't Care" Conditions | ACM/SIGDA FPGA '25, pp. 36-42 | Mark input patterns never seen in training as don't-cares to raise table-decomposition reuse | Up to 1.63x fewer physical LUTs (v1: up to 39%) with ≤0.01 accuracy-point drop (arXiv abstract snippet) | LUT-NN compression (jet tagging, MNIST) | Don't-care assumption is risky under inter-patient distribution shift, where unseen patterns are expected | https://arxiv.org/abs/2412.18579 |
| khataei2025treelut | Khataei & Bazargan | 2025 | TreeLUT: An Efficient Alternative to Deep Neural Networks for Inference Acceleration Using Gradient Boosted Decision Trees | ACM/SIGDA FPGA '25 | Quantised GBDTs mapped to LUT-only pipelined FPGA logic (no BRAM/DSP) | ~97% MNIST; 4-101x lower area-delay product than recent LUT-NNs (abstract snippet) | Tabular, MNIST, jet tagging | Strong non-neural LUT baseline; static per-window classifier; not evaluated on biosignals | https://arxiv.org/abs/2501.01511 ; https://par.nsf.gov/biblio/10586511 |
| mecik2025thermo | Mecik & Kumm | 2025 | Implementation and Analysis of Thermometer Encoding in DWN FPGA Accelerators | Asilomar 2025 (accepted; arXiv:2512.15251) | Full DWN generator incl. thermometer encoder, LUT layer and classification logic; non-uniform thresholds | Encoding raises LUT usage by up to 3.20x on JSC and dominates cost in small networks (arXiv abstract snippet) | Jet substructure classification (also MNIST) | Shows the encoder cost that most DWN/LUT-NN papers leave out; this matters most for a tiny, many-channel seizure detector | https://arxiv.org/abs/2512.15251 ; https://www.alphaxiv.org/abs/2512.15251 |
| mommen2026ecg | Mommen et al. | 2026 | Inter-patient ECG Arrhythmia Classification with LGNs and LUTNs | arXiv:2601.11433 (preprint) | LGNs and LUT networks on MIT-BIH, inter-patient protocol; LUT training via the MUX Boolean equation; rate coding of inputs | Up to 94.28% accuracy, jκ 0.683 (4-class); 2.89k-6.17k FLOPs incl. pre-processing; Artix-7: 2000-2990 LUTs; est. 50-70 pJ/inference (5-7 mW) (abstract snippets) | ECG arrhythmia (wearables, implants) | Closest biosignal precedent; single modality, beat-level, no seizures, no missing-modality handling | https://arxiv.org/abs/2601.11433 |
| dharia2026eeglgn | Dharia et al. | 2026 | Differentiable Logic Gate Networks for Low-Latency EEG Classification on Edge Devices | Canadian AI 2026, PMLR 318:377-391 (arXiv:2607.18149) | Diff-Logic (DLGN) compiled to bitwise CPU code vs. iso-parameter MLP/BNN on 4 EEG datasets | 80.2% macro-F1 on dementia detection (beats MLP; margin differs between sources, 6.8 vs 9.4 points); MLP keeps an edge on emotion; latency ~flat over 10x model scale, ~2.9x faster than MLP at largest tier, Jetson Orin Nano single CPU core (abstract/conclusion snippets) | EEG: dementia, emotion (SEED) | First LGN on EEG; CPU only (no FPGA LUT count); 2-input gates; no seizures, no event-level metrics, EEG only | https://proceedings.mlr.press/v318/dharia26a.html ; https://arxiv.org/abs/2607.18149 |
| deaguiar2015wisard | de Aguiar et al. | 2015 | Early detection of epilepsy seizures based on a weightless neural network | IEEE EMBC 2015, pp. 4470-4474 | WiSARD on pre-processed EEG; anticipation interval δ 2-30 s, sliding observation window 2-3 s | Hardest patient: 99.57% (δ=2 s, SOW=3 s) down to 72.56% (δ=30 s, SOW=2 s) accuracy (abstract snippet) | Seizure anticipation, EPILEPSIAE (4 patients) | Only weightless seizure work found: 4 patients, accuracy only (no sensitivity / false alarms per 24 h), non-differentiable WiSARD, no hardware implementation in the abstract, EEG only | https://pubmed.ncbi.nlm.nih.gov/26737287/ ; https://doi.org/10.1109/embc.2015.7319387 |

Two more papers came up in the searches and are not tabulated: WARP-LUTs (arXiv:2510.15655, Walsh-Hadamard
parametrisation of higher-input LUTs) and Quasi-Weightless Transformers (Nag et al., arXiv:2411.01818, DWN layers in
place of transformer MLPs). Add them only after checking their full author lists.

Explicit negative result: searches for seizure detection with LUT networks, logic-gate networks or DWNs ("logic
gate network seizure detection FPGA lookup table EEG", "weightless neural network seizure detection EEG" in extended
mode, "LUT-based neural network ... biomedical ECG EEG") found **no** differentiable LUT or logic network for seizure
detection, on any EEG montage or wearable dataset. The only weightless seizure paper is de Aguiar et al. (2015, WiSARD,
4 patients). A search for multimodal or missing-modality LUT/logic/weightless networks also returned nothing; all the
missing-modality work it found is float deep learning. A search for recurrent or stateful weightless (DWN) models
returned nothing either. The only recurrent logic network found is Bührer et al. (LGN, NLP).

## (b) BibTeX

```bibtex
@article{aleksander1984wisard,
  author  = {Aleksander, Igor and Thomas, W. V. and Bowden, P. A.},
  title   = {{WISARD}$\cdot$a radical step forward in image recognition},
  journal = {Sensor Review},
  volume  = {4},
  number  = {3},
  pages   = {120--124},
  year    = {1984},
  doi     = {10.1108/eb007637}
}

@inproceedings{susskind2022bthowen,
  author    = {Susskind, Zachary and Arora, Aman and Miranda, Igor D. S. and Villon, Luis A. Q. and Katopodis, Rafael F. and de Ara{\'u}jo, Leandro S. and Dutra, Diego L. C. and Lima, Priscila M. V. and Fran{\c{c}}a, Felipe M. G. and Breternitz Jr., Mauricio and John, Lizy K.},
  title     = {Weightless Neural Networks for Efficient Edge Inference},
  booktitle = {Proceedings of the International Conference on Parallel Architectures and Compilation Techniques (PACT '22)},
  pages     = {279--290},
  publisher = {ACM},
  year      = {2022},
  doi       = {10.1145/3559009.3569680},
  eprint    = {2203.01479},
  archivePrefix = {arXiv}
}

@article{susskind2023uleen,
  author  = {Susskind, Zachary and Arora, Aman and Miranda, Igor D. S. and Bacellar, Alan T. L. and Villon, Luis A. Q. and Katopodis, Rafael F. and de Ara{\'u}jo, Leandro S. and Dutra, Diego L. C. and Lima, Priscila M. V. and Fran{\c{c}}a, Felipe M. G. and Breternitz Jr., Mauricio and John, Lizy K.},
  title   = {{ULEEN}: A Novel Architecture for Ultra Low-Energy Edge Neural Networks},
  journal = {ACM Transactions on Architecture and Code Optimization},
  volume  = {20},
  number  = {4},
  pages   = {61},
  year    = {2023},
  doi     = {10.1145/3629522},
  eprint  = {2304.10618},
  archivePrefix = {arXiv},
  note    = {Author list as given in the authors' ULEEN code repository; check it against the ACM DL record before submission}
}

@inproceedings{bacellar2024dwn,
  author    = {Bacellar, Alan T. L. and Susskind, Zachary and Breternitz Jr., Mauricio and John, Eugene and John, Lizy K. and Lima, Priscila M. V. and Fran{\c{c}}a, Felipe M. G.},
  title     = {Differentiable Weightless Neural Networks},
  booktitle = {Proceedings of the 41st International Conference on Machine Learning (ICML)},
  series    = {Proceedings of Machine Learning Research},
  volume    = {235},
  pages     = {2277--2295},
  publisher = {PMLR},
  year      = {2024},
  url       = {https://proceedings.mlr.press/v235/bacellar24a.html},
  eprint    = {2410.11112},
  archivePrefix = {arXiv}
}

@inproceedings{bacellar2025nanoml,
  author    = {Bacellar, Alan T. L. and Jadhao, Mugdha P. and Nag, Shashank and Lima, Priscila M. V. and Fran{\c{c}}a, Felipe M. G. and John, Lizy K.},
  title     = {nano{ML} for Human Activity Recognition},
  booktitle = {tinyML Research Symposium},
  year      = {2025},
  eprint    = {2502.12173},
  archivePrefix = {arXiv},
  note      = {The arXiv comment names the 2025 EDGE AI FOUNDATION Austin event; the paper's ACM reference format names tinyML Research Symposium '25}
}

@misc{kresse2025dwc,
  author  = {Kresse, Fabian and Lampert, Christoph H.},
  title   = {Differentiable Weightless Controllers: Learning Logic Circuits for Continuous Control},
  year    = {2025},
  eprint  = {2512.01467},
  archivePrefix = {arXiv},
  primaryClass  = {cs.LG},
  note    = {An ICML 2026 poster page exists (icml.cc/virtual/2026/poster/62491); cite the proceedings version once published}
}

@inproceedings{petersen2022dlgn,
  author    = {Petersen, Felix and Borgelt, Christian and Kuehne, Hilde and Deussen, Oliver},
  title     = {Deep Differentiable Logic Gate Networks},
  booktitle = {Advances in Neural Information Processing Systems (NeurIPS)},
  volume    = {35},
  year      = {2022},
  url       = {https://openreview.net/forum?id=vF3WefcoePW},
  eprint    = {2210.08277},
  archivePrefix = {arXiv}
}

@inproceedings{petersen2024convdlgn,
  author    = {Petersen, Felix and Kuehne, Hilde and Borgelt, Christian and Welzel, Julian and Ermon, Stefano},
  title     = {Convolutional Differentiable Logic Gate Networks},
  booktitle = {Advances in Neural Information Processing Systems (NeurIPS)},
  volume    = {37},
  year      = {2024},
  doi       = {10.52202/079017-3851},
  eprint    = {2411.04732},
  archivePrefix = {arXiv},
  note      = {The DOI comes from a BibTeX/proceedings search snippet; check it at doi.org}
}

@misc{buhrer2025rdlgn,
  author  = {B{\"u}hrer, Simon and Plesner, Andreas and Aczel, Till and Wattenhofer, Roger},
  title   = {Recurrent Deep Differentiable Logic Gate Networks},
  year    = {2025},
  eprint  = {2508.06097},
  archivePrefix = {arXiv},
  primaryClass  = {cs.LG}
}

@inproceedings{ruttgers2026lightdlgn,
  author    = {R{\"u}ttgers, Lukas and Aczel, Till and Plesner, Andreas and Wattenhofer, Roger},
  title     = {Light Differentiable Logic Gate Networks},
  booktitle = {International Conference on Learning Representations (ICLR)},
  year      = {2026},
  eprint    = {2510.03250},
  archivePrefix = {arXiv}
}

@inproceedings{wang2019lutnet,
  author    = {Wang, Erwei and Davis, James J. and Cheung, Peter Y. K. and Constantinides, George A.},
  title     = {{LUTNet}: Rethinking Inference in {FPGA} Soft Logic},
  booktitle = {IEEE 27th Annual International Symposium on Field-Programmable Custom Computing Machines (FCCM)},
  pages     = {26--34},
  year      = {2019},
  doi       = {10.1109/FCCM.2019.00014},
  eprint    = {1904.00938},
  archivePrefix = {arXiv}
}

@inproceedings{umuroglu2020logicnets,
  author    = {Umuroglu, Yaman and Akhauri, Yash and Fraser, Nicholas J. and Blott, Michaela},
  title     = {{LogicNets}: Co-Designed Neural Networks and Circuits for Extreme-Throughput Applications},
  booktitle = {30th International Conference on Field-Programmable Logic and Applications (FPL)},
  pages     = {291--297},
  year      = {2020},
  doi       = {10.1109/FPL50879.2020.00055},
  eprint    = {2004.03021},
  archivePrefix = {arXiv}
}

@inproceedings{andronic2023polylut,
  author    = {Andronic, Marta and Constantinides, George A.},
  title     = {{PolyLUT}: Learning Piecewise Polynomials for Ultra-Low Latency {FPGA} {LUT}-based Inference},
  booktitle = {International Conference on Field Programmable Technology (ICFPT)},
  pages     = {60--68},
  year      = {2023},
  doi       = {10.1109/ICFPT59805.2023.00012},
  eprint    = {2309.02334},
  archivePrefix = {arXiv}
}

@inproceedings{andronic2024neuralut,
  author    = {Andronic, Marta and Constantinides, George A.},
  title     = {{NeuraLUT}: Hiding Neural Network Density in Boolean Synthesizable Functions},
  booktitle = {34th International Conference on Field-Programmable Logic and Applications (FPL)},
  pages     = {140--148},
  year      = {2024},
  doi       = {10.1109/FPL64840.2024.00028},
  eprint    = {2403.00849},
  archivePrefix = {arXiv}
}

@inproceedings{weng2025amigolut,
  author    = {Weng, Olivia and Andronic, Marta and Zuberi, Danial and Chen, Jiaqing and Geniesse, Caleb and Constantinides, George A. and Tran, Nhan and Fraser, Nicholas J. and Duarte, Javier Mauricio and Kastner, Ryan},
  title     = {Greater than the Sum of its {LUTs}: Scaling Up {LUT}-based Neural Networks with {AmigoLUT}},
  booktitle = {Proceedings of the 2025 ACM/SIGDA International Symposium on Field Programmable Gate Arrays (FPGA '25)},
  pages     = {25--35},
  publisher = {ACM},
  year      = {2025},
  note      = {DOI not verified (Crossref/dblp unreachable here); look it up before submission}
}

@inproceedings{cassidy2025reducedlut,
  author    = {Cassidy, Oliver and Andronic, Marta and Coward, Samuel and Constantinides, George A.},
  title     = {{ReducedLUT}: Table Decomposition with ``Don't Care'' Conditions},
  booktitle = {Proceedings of the 2025 ACM/SIGDA International Symposium on Field Programmable Gate Arrays (FPGA '25)},
  pages     = {36--42},
  publisher = {ACM},
  year      = {2025},
  doi       = {10.1145/3706628.3708823},
  eprint    = {2412.18579},
  archivePrefix = {arXiv}
}

@inproceedings{khataei2025treelut,
  author    = {Khataei, Alireza and Bazargan, Kia},
  title     = {{TreeLUT}: An Efficient Alternative to Deep Neural Networks for Inference Acceleration Using Gradient Boosted Decision Trees},
  booktitle = {Proceedings of the 2025 ACM/SIGDA International Symposium on Field Programmable Gate Arrays (FPGA '25)},
  publisher = {ACM},
  year      = {2025},
  doi       = {10.1145/3706628.3708877},
  eprint    = {2501.01511},
  archivePrefix = {arXiv}
}

@inproceedings{mecik2025thermo,
  author    = {Mecik, Michael and Kumm, Martin},
  title     = {Implementation and Analysis of Thermometer Encoding in {DWN} {FPGA} Accelerators},
  booktitle = {Asilomar Conference on Signals, Systems, and Computers},
  year      = {2025},
  eprint    = {2512.15251},
  archivePrefix = {arXiv},
  note      = {Accepted at Asilomar 2025 per arXiv; proceedings DOI not yet verified}
}

@misc{mommen2026ecg,
  author  = {Mommen, Wout and Keuninckx, Lars and Detterer, Paul and Colpaert, Achiel and Wambacq, Piet},
  title   = {Inter-patient {ECG} Arrhythmia Classification with {LGNs} and {LUTNs}},
  year    = {2026},
  eprint  = {2601.11433},
  archivePrefix = {arXiv},
  primaryClass  = {cs.LG}
}

@inproceedings{dharia2026eeglgn,
  author    = {Dharia, Shyamal and Smith, Stephen and Valderrama, Camilo},
  title     = {Differentiable Logic Gate Networks for Low-Latency {EEG} Classification on Edge Devices},
  booktitle = {Proceedings of the 39th Canadian Conference on Artificial Intelligence},
  series    = {Proceedings of Machine Learning Research},
  volume    = {318},
  pages     = {377--391},
  publisher = {PMLR},
  year      = {2026},
  url       = {https://proceedings.mlr.press/v318/dharia26a.html},
  eprint    = {2607.18149},
  archivePrefix = {arXiv}
}

@inproceedings{deaguiar2015wisard,
  author    = {de Aguiar, Kleber and Fran{\c{c}}a, Felipe M. G. and Barbosa, Valmir C. and Teixeira, C{\'e}sar A. D.},
  title     = {Early detection of epilepsy seizures based on a weightless neural network},
  booktitle = {37th Annual International Conference of the IEEE Engineering in Medicine and Biology Society (EMBC)},
  pages     = {4470--4474},
  year      = {2015},
  doi       = {10.1109/EMBC.2015.7319387},
  pmid      = {26737287}
}
```

## (c) Research gaps

1. No differentiable LUT-native or logic-gate seizure detector exists. The biosignal work is ECG arrhythmia
   (Mommen et al. 2026), EEG dementia/emotion classification on a CPU (Dharia et al. 2026) and wearable inertial HAR
   (Bacellar et al. 2025). The only weightless seizure work is a non-differentiable WiSARD tested on 4 EPILEPSIAE
   patients, with accuracy as the only metric (de Aguiar et al. 2015). None reports the event-level sensitivity and
   false alarms per 24 h that seizure detection on SeizeIT2 needs.
2. Every LUT, weightless and logic network found is single-modality. None fuses EEG with ECG, EMG or motion, and none
   handles a missing or dropped modality, which wearable recordings make routine.
3. The input encoder's hardware cost is rarely measured. Mecik & Kumm (2025) state that the hardware cost of DWN
   thermometer encoding "has not been fully evaluated", and show it can raise LUT usage by up to 3.20x and dominate
   small networks. None of the other abstracts read here reports encoder cost separately. A multi-channel,
   multimodal detector multiplies that cost.
4. All DWNs and LUT-NNs found are stateless per-window classifiers. The only recurrent logic network is an NLP
   preprint (Bührer et al. 2025), so a stateful DWN for biosignal events, with temporal smoothing or hysteresis done
   in LUT logic, is open.
5. The FPGA LUT-NN papers (LogicNets, PolyLUT, NeuraLUT, AmigoLUT, ReducedLUT, TreeLUT) benchmark jet tagging,
   intrusion detection, MNIST and tabular data. Mommen et al. are the only ones found to test inter-patient
   generalisation, and they classify ECG beats. No LUT or logic network has been evaluated on long continuous
   recordings with rare events, where shortcuts such as ReducedLUT's "don't care" entries for unseen patterns may not
   hold. Gap 1 is the one this project fills directly. Claim gaps
   2-5 only as far as the project's experiments cover them (e.g. a missing-modality test, encoder LUTs counted in
   the cost).
