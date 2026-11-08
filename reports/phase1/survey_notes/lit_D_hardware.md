# Literature survey, section D: hardware and low-power seizure detection, efficient inference on FPGAs

How this was checked (2026-11-08). Every entry below came up in WebSearch with a matching title, authors, venue and
year. The "Verified at" column gives the page(s) whose search snippet confirmed it. Direct fetching was blocked in this
environment: iris.unica.it and dblp.org did not resolve for WebFetch, and api.semanticscholar.org, api.crossref.org and
dblp.org were refused by the network proxy (one try each). So no full text was read. Every number below comes from an
abstract or repository snippet that a search returned, and the cell names that source. "-" means not verified. Numbers
from different papers use different units (energy per feature vector, per classification, per inference; dynamic vs.
programmable-logic power; per-classification compute time in µs vs. clinical detection delay in s), so do not
compare them directly.

The main table has 16 rows: 12 seizure-detection hardware papers (5 ASIC, 4 FPGA, 3 MCU) and the 4 key tool
references the brief asks for. Four more papers were verified but left out of the main table to stay near the 10-14
target. They are listed in a short reserve table with their BibTeX.

## (a) Table

| Ref key | Authors (first author et al.) | Year | Title | Venue | Platform (ASIC/FPGA/MCU) | Method | Data | Hardware result (source) | Detection result (source) | Limitation / gap relevant to our project | Verified at (URL) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| verma2010micro | Verma, Shoeb, Bohorquez, Dawson, Guttag, Chandrakasan | 2010 | A Micro-Power EEG Acquisition SoC With Integrated Feature Extraction Processor for a Chronic Seizure Detection System | IEEE JSSC 45(4):804-816 | ASIC (one SoC per EEG channel) | Chopper-stabilised instrumentation amplifier + ADC + digital spectral feature extractor on chip; feature vectors sent to a central device that runs the machine-learning classifier | Scalp EEG, up to 18 channels per patient (abstract) | 1 V supply; 9 µJ per feature vector, feature vectors at 0.5 Hz; local processing lowers system power 14x by cutting wireless EEG transmission (JSSC abstract via MIT DSpace) | - (classifier is off-chip) | Only feature extraction is on chip; the classifier runs elsewhere. EEG only | https://dspace.mit.edu/handle/1721.1/74119 ; https://collaborate.princeton.edu/en/publications/a-micro-power-eeg-acquisition-soc-with-integrated-feature-extract/ |
| altaf2015jssc | Bin Altaf, Zhang, Yoo | 2015 | A 16-Channel Patient-Specific Seizure Onset and Termination Detection SoC With Impedance-Adaptive Transcranial Electrical Stimulator | IEEE JSSC 50(11):2728-2740 | ASIC (0.18 µm CMOS, 25 mm²) | Non-invasive closed-loop SoC: detects seizure onset and termination with a linear SVM (index keywords), plus a transcranial electrical stimulator | Scalp EEG; CHB-MIT according to the companion CICC 2015 paper with the same figures | 2.73 µJ/classification for 16 channels (abstract via ISC index / dblp) | Sensitivity 95.7%, specificity 98%, latency 1 s (abstract snippet) | Patient-specific training. Results are epoch-level sensitivity/specificity with no FP/h. EEG only | https://dblp.uni-trier.de/rec/journals/jssc/AltafZY15.html ; https://search.isc.ac/inventory/49/3608694.htm |
| altaf2016tbcas | Bin Altaf, Yoo | 2016 | A 1.83 µJ/Classification, 8-Channel, Patient-Specific Epileptic Seizure Classification SoC Using a Non-Linear Support Vector Machine | IEEE TBioCAS 10:49- | ASIC (0.18 µm 1P6M CMOS) | Non-linear SVM with a log-linear Gaussian-basis-function engine to cut the hardware cost of the kernel | Scalp EEG, CHB-MIT (abstract snippet) | 1.83 µJ/classification at 8 channels (title and abstract snippet) | Average detection rate 95.1%, false-alarm rate 0.94%, latency <2 s (abstract snippet via researchr/scite) | Patient-specific. False alarms are given as a %, not per hour. The non-linear kernel needs a dedicated arithmetic engine | https://doi.org/10.1109/tbcas.2014.2386891 ; https://researchr.org/publication/AltafY16 |
| shoaran2018jetcas | Shoaran, Allahgholizadeh Haghi, Taghavi, Farivar, Emami-Neyestanak | 2018 | Energy-Efficient Classification for Resource-Constrained Biomedical Applications | IEEE JETCAS 8(4):693-707 | ASIC (65 nm TSMC) | Gradient-boosted decision trees with asynchronous tree operation and sequential feature extraction; the number of trees varies per patient | Intracranial EEG, 26 patients, 3074 h, 393 seizures (abstract) | 41.2 nJ/class; area 540 x 1850 µm²; 27x lower energy-area-latency product than prior art (abstract via Caltech record) | Average F1 99.23% (random split) and 87.86% (block-wise split); average detection latency 1.1 s (abstract snippet) | Implant (iEEG) setting, per-patient models. Shows that tree (comparator-only) inference reaches nJ/class; a tree is a natural LUT mapping (our note, not the paper's claim) | https://resolver.caltech.edu/CaltechAUTHORS:20190109-161530924 ; https://core.ac.uk/works/61075740 |
| shin2022neuraltree | Shin, Ding, Zhu, Vyza, Trouillet, Revol, Lacour, Shoaran | 2022 | NeuralTree: A 256-Channel 0.227-µJ/Class Versatile Neural Activity Classification and Closed-Loop Neuromodulation SoC | IEEE JSSC 57(11):3243-3257 | ASIC (65 nm CMOS) | 256-channel time-multiplexed front end, tree-structured neural-network classifier, 16-channel high-voltage neurostimulator | Human EEG and iEEG epilepsy datasets; Parkinson's LFP (abstract) | 0.227 µJ/class; 0.014 mm² per channel (arXiv abstract) | EEG: sensitivity 95.6%, specificity 96.8%; iEEG: 94% / 96.9% (arXiv abstract) | Neural signals only (no ECG/EMG/motion). Metrics are sensitivity/specificity, not event-level FP/h | https://arxiv.org/abs/2205.06090 ; https://infoscience.epfl.ch/record/297386 |
| wang2018access | Wang, Shi, Choy | 2018 | Hardware Design of Real Time Epileptic Seizure Detection Based on STFT and SVM | IEEE Access (2018) | FPGA (Xilinx Zynq-7000 XC7Z020, high-level synthesis) | STFT spectral features + SVM; two-stage patient-specific channel and feature selection | Scalp EEG, CHB-MIT (abstract) | 313 µs per classification; programmable-logic power 380 mW at 100 MHz (abstract via DOAJ/typeset) | Sensitivity 98.4%, false detection rate 0.356/h, mean detection latency 6 s (abstract) | Patient-specific. 380 mW is far above a wearable budget. LUT/DSP counts are not in the abstract | https://doaj.org/article/684afe7a583a4df7baf580dd2fbb298a ; https://typeset.io/papers/hardware-design-of-real-time-epileptic-seizure-detection-56zkbluaoy |
| elhosary2019tbcas | Elhosary, Zakhari, Elgammal, Abd El Ghany, Salama, Mostafa | 2019 | Low-Power Hardware Implementation of a Support Vector Machine Training and Classification for Neural Seizure Detection | IEEE TBioCAS 13(6):1324-1337 | FPGA (Xilinx Virtex-7) and ASIC (UMC 65 nm) | On-chip SVM training (sequential minimal optimisation), feature extraction and classification | - (not in the snippets) | ASIC power about 2x lower than the FPGA version (abstract); absolute mW not retrieved | Sensitivity about 96.77% with the linear-kernel classifier (abstract via KAUST record) | No false-alarm rate in the snippet. A high-end FPGA, not a wearable-class part. EEG only | https://archive.kaust.edu.sa/handle/10754/658642 ; https://sensors.kaust.edu.sa/articles/2019/04/25/low-power-hardware-implementation-support-vector-machine-training-and |
| razi2022tbcas | Farhang Razi, Schmid | 2022 | Epileptic Seizure Detection With Patient-Specific Feature and Channel Selection for Low-power Applications | IEEE TBioCAS 16(4):626-635 | FPGA (Intel Cyclone V on Terasic DE10-Standard) | Two-step feature ranking by maximum discrimination minimum redundancy (MDMR) plus patient-specific iEEG channel selection; classifier not confirmed from the abstract | Intracranial EEG, 12 patients, Bern Inselspital (abstract) | Average dynamic power 0.49 mW; 68% average data reduction from channel selection (abstract via PubMed) | Sensitivity 100% for all patients (abstract) | Patient-specific, iEEG (implant). False-alarm rate not in the snippet. Dynamic power only | https://www.pubmed.gov/35793304/ ; https://dblp.uni-trier.de/rec/journals/tbcas/RaziS22.html |
| busia2025fpga | Busia, Leone, Matticola, Raffo, Meloni | 2025 | Wearable Epilepsy Seizure Detection on FPGA With Spiking Neural Networks | IEEE TBioCAS 19(6):1175- | FPGA (SYNtzulu SNN processor on a Lattice iCE40UP5K) | Lightweight spiking neural network on raw EEG with a simple sparse spike encoding | Scalp EEG, CHB-MIT, 4 temporal channels (abstract and ResearchGate preview) | 0.5 µs inference time, 4.55 nJ energy per inference on SYNtzulu (abstract) | 100% of tested seizure events detected; 99.3% average segment accuracy; 0.3 FP/h; AUC 96% (abstract). Lower accuracy and sensitivity on its generalisation test records (paper text snippet) | Closest to our Phase 2 (low-cost FPGA, few temporal channels). Still EEG only, on paediatric CHB-MIT; LUT count not retrieved | https://doi.org/10.1109/tbcas.2025.3575327 ; https://iris.unica.it/handle/11584/447645 ; https://zenodo.org/records/15731140 |
| sopic2018eglass | Sopic, Aminifar, Atienza | 2018 | e-Glass: A Wearable System for Real-Time Detection of Epileptic Seizures | IEEE ISCAS 2018 | MCU (wearable embedded system in an eyeglasses frame; MCU model not in the abstract) | Feature extraction + classification on 4 EEG electrodes (F7-T3, F8-T4) worn in the temples of the glasses | Scalp EEG, CHB-MIT (abstract) | 2.71 days of operation on one battery charge (abstract) | Sensitivity 93.80%, specificity 93.37% (abstract) | Early wearable-form-factor work. Epoch-level metrics only; EEG only | https://infoscience.epfl.ch/entities/publication/de95687f-ce6a-4867-987a-c75b98e843be ; https://lup.lub.lu.se/search/publication/134af4fc-ffcb-4228-b301-c34ec9928694 |
| busia2024eegformer | Busia, Cossettini, Ingolfsson, Benatti, Burrello, Jung, Scherer, Scrugli, Bernini, Ducouret, Ryvlin, Meloni, Benini | 2024 | Reducing False Alarms in Wearable Seizure Detection With EEGformer: A Compact Transformer Model for MCUs | IEEE TBioCAS 18(3):608-621 | MCU (Ambiq Apollo4; GreenWaves GAP8 and GAP9) | Compact transformer on raw EEG from temporal channels only | Scalp EEG: CHB-MIT plus a second scalp-EEG dataset (abstract) | Best on GAP9: 13.7 ms and 0.31 mJ per inference (abstract) | CHB-MIT: 73% of seizures detected at 0.15 FP/h, onset latency 20% lower than prior temporal-channel model; second dataset: 88% of seizures at 0.45 FP/h (abstract) | Reports event-level FP/h, which is rare. EEG only; MAC-based (multipliers), not LUT-native | https://iris.unica.it/handle/11584/391183 ; https://serval.unil.ch/notice/serval:BIB_BA31F50F7689 |
| ingolfsson2024brainfusenet | Ingolfsson, Wang, Chakraborty, Benatti, Bernini, Ducouret, Ryvlin, Beniczky, Benini, Cossettini | 2024 | BrainFuseNet: Enhancing Wearable Seizure Detection Through EEG-PPG-Accelerometer Sensor Fusion and Efficient Edge Deployment | IEEE TBioCAS 18(4):720-733 | MCU (GreenWaves GAP9) | Lightweight network fusing EEG, PPG and accelerometer; sensitivity-specificity weighted cross-entropy loss for class imbalance | CHB-MIT (4 EEG channels); PEDESITE (EEG + PPG + ACC) (abstract) | 0.11 mJ per inference; 21.43 GMAC/s/W at 412.54 MMAC/s (abstract) | CHB-MIT: 93.5% of seizure events, 76.34% sample sensitivity. PEDESITE: EEG alone 60.66% sample sensitivity, 1.18 FP/h; EEG+PPG+ACC 64.28%, 95% of events, 0.21 FP/h sample-based, under one false alarm per day event-based (abstract via cris.unibo.it) | The closest multimodal on-device analogue. It uses PPG and accelerometer, not ECG or EMG; not SeizeIT2; MCU MAC arithmetic. Whether the split is patient-independent is not stated in the snippets | https://dblp.org/rec/journals/tbcas/IngolfssonWCBBDRBBC24.html ; https://cris.unibo.it/handle/11585/1004689 ; https://iris.unimore.it/handle/11380/1355847 |
| hubara2016bnn | Hubara, Courbariaux, Soudry, El-Yaniv, Bengio | 2016 | Binarized Neural Networks | NIPS 29 (2016), pp. 4107-4115 | Method (no platform) | Training with binary weights and activations at run time | MNIST, CIFAR-10, SVHN | - | Near state-of-the-art on MNIST, CIFAR-10 and SVHN (NeurIPS abstract) | Generic image benchmarks. Binarisation still keeps XNOR-popcount neurons, not arbitrary LUT functions | https://papers.nips.cc/paper/2016/hash/d8330f857a17c53d217014ee776bfd50-Abstract.html ; https://arxiv.org/abs/1602.02830 |
| umuroglu2017finn | Umuroglu, Fraser, Gambardella, Blott, Leong, Jahre, Vissers | 2017 | FINN: A Framework for Fast, Scalable Binarized Neural Network Inference | FPGA '17 (ACM/SIGDA ISFPGA), pp. 65-74 | FPGA (Xilinx ZC706) | Heterogeneous streaming dataflow architecture for BNNs, with per-layer compute sized to a throughput target | MNIST, CIFAR-10, SVHN | Up to 12.3 M classifications/s at 0.31 µs latency on MNIST (95.8% accuracy); 21,906 classifications/s on CIFAR-10 and SVHN (arXiv abstract) | - | Tool baseline for quantised and binarised FPGA inference; not applied to biosignals | https://researchr.org/publication/UmurogluFGBLJV17 ; https://arxiv.org/abs/1612.07119 |
| jacob2018quant | Jacob, Kligys, Chen, Zhu, Tang, Howard, Adam, Kalenichenko | 2018 | Quantization and Training of Neural Networks for Efficient Integer-Arithmetic-Only Inference | CVPR 2018, pp. 2704-2713 | Method (mobile CPUs and integer accelerators such as Qualcomm Hexagon) | Integer-only quantisation (8-bit weights and activations) with a co-designed quantisation-aware training procedure | - | About 4x smaller than 32-bit float (abstract) | Accuracy close to floating-point inference (abstract) | Standard integer baseline; still needs integer multipliers (DSPs on FPGA) | https://openaccess.thecvf.com/content_cvpr_2018/html/Jacob_Quantization_and_Training_CVPR_2018_paper.html ; https://arxiv.org/abs/1712.05877 |
| duarte2018hls4ml | Duarte, Han, Harris, Jindariani, Kreinar, Kreis, Ngadiuba, Pierini, Rivera, Tran, Wu | 2018 | Fast inference of deep neural networks in FPGAs for particle physics | JINST 13 P07027 | FPGA (high-level-synthesis tool hls4ml) | hls4ml: translates trained networks into HLS firmware, with tunable precision and reuse | Jet-substructure classification (particle physics) | About 100 ns latency for the jet-substructure model within FPGA resource limits (abstract-level snippet) | - | Dense layers map to DSP multipliers (our note); low-latency trigger domain, not biosignals | https://arxiv.org/abs/1804.06913 ; https://dspace.mit.edu/handle/1721.1/128237 |

### Reserve (verified, not in the main table)

| Ref key | Authors | Year | Title | Venue | Platform | Key verified facts (source) | Verified at (URL) |
|---|---|---|---|---|---|---|---|
| huang2020jssc | Huang, Chang, Liou, Yang | 2020 | A 1.9-mW SVM Processor With On-Chip Active Learning for Epileptic Seizure Control | IEEE JSSC 55(2):452-464 | ASIC | 1.9 mW; 96.6% accuracy, 0.28/h false alarm rate, detection within 0.71 s; on-chip SVM training (ADMM) and active learning; 22x throughput and 162x energy efficiency for SVM training vs. prior designs (abstract via NTU repository) | https://scholars.lib.ntu.edu.tw/handle/123456789/519106 |
| vittimberga2025sensors | Vittimberga, Nicolini, Scotti | 2025 | Real-Time Multi-Channel Epileptic Seizure Detection Exploiting an Ultra-Low-Complexity Algorithm-Hardware Co-Design Approach | Sensors 25(22):6889 | FPGA | Line length + instantaneous power difference, majority vote over all channels, time-multiplexed filtering and feature extraction (abstract). About 98% accuracy and >98% sensitivity on CHB-MIT and SWEC-ETHZ, and "3 DSP blocks", per the author's PhD page summary; FP/h not retrieved | https://www.mdpi.com/1424-8220/25/22/6889 ; https://phd.uniroma1.it/web/ANDREA-VITTIMBERGA_nT1555342_EN.aspx |
| kartsch2019biowolf | Kartsch, Tagliavini, Guermandi, Benatti, Rossi, Benini | 2019 | BioWolf: A Sub-10-mW 8-Channel Advanced Brain-Computer Interface Platform With a Nine-Core Processor and BLE Connectivity | IEEE TBioCAS 13(5):893-906 | MCU (Mr. Wolf PULP SoC, nine RISC-V cores, + BLE SoC) | Wearable ExG/BCI platform, sub-10 mW, 8 channels (title; repository record). A platform, not a seizure detector | https://dblp.dagstuhl.de/pid/38/10353.html ; https://iris.unimore.it/handle/11380/1264909 |
| ingolfsson2022artifact | Ingolfsson, Cossettini, Benatti, Benini | 2022 | Energy-Efficient Tree-Based EEG Artifact Detection | EMBC 2022, pp. 3723-3728 | MCU (PULP platform) | Tree models on 4 temporal EEG channels, TUH EEG Artifact Corpus: 93.95% accuracy, F1 0.838; 5.21x energy-efficiency gain over prior low-power artifact detectors; with a low-power seizure detector, 300 h on a 300 mAh battery (arXiv abstract) | https://dblp.uni-trier.de/rec/conf/embc/IngolfssonCBB22.html ; https://arxiv.org/abs/2204.09577 |

Note for the writer: the SYNtzulu processor used by busia2025fpga is described in a separate paper (Leone, Scrugli,
Badas, Martis, Raffo, Meloni, IEEE TCAS-I, on iCE40UP5K: 12.05 mW peak, 1.45 mW average with dynamic power
management, per its abstract snippet). It is not tabulated here. Cite it only after checking its volume and pages.

## (b) BibTeX

Fields that could not be confirmed (pages, issue numbers) are left out, with a `%` comment line above the entry, so
they are not guessed.

```bibtex
@article{verma2010micro,
  author  = {Verma, Naveen and Shoeb, Ali and Bohorquez, Jose and Dawson, Joel and Guttag, John and Chandrakasan, Anantha P.},
  title   = {A Micro-Power {EEG} Acquisition {SoC} With Integrated Feature Extraction Processor for a Chronic Seizure Detection System},
  journal = {IEEE Journal of Solid-State Circuits},
  volume  = {45},
  number  = {4},
  pages   = {804--816},
  year    = {2010},
  doi     = {10.1109/JSSC.2010.2042245}
}

@article{altaf2015jssc,
  author  = {Bin Altaf, Muhammad Awais and Zhang, Chen and Yoo, Jerald},
  title   = {A 16-Channel Patient-Specific Seizure Onset and Termination Detection {SoC} With Impedance-Adaptive Transcranial Electrical Stimulator},
  journal = {IEEE Journal of Solid-State Circuits},
  volume  = {50},
  number  = {11},
  pages   = {2728--2740},
  year    = {2015},
  doi     = {10.1109/JSSC.2015.2482498}
}

% start page 49 per a citing record; issue number and end page not verified
@article{altaf2016tbcas,
  author  = {Bin Altaf, Muhammad Awais and Yoo, Jerald},
  title   = {A 1.83 $\mu${J}/Classification, 8-Channel, Patient-Specific Epileptic Seizure Classification {SoC} Using a Non-Linear Support Vector Machine},
  journal = {IEEE Transactions on Biomedical Circuits and Systems},
  volume  = {10},
  year    = {2016},
  doi     = {10.1109/TBCAS.2014.2386891}
}

@article{shoaran2018jetcas,
  author  = {Shoaran, Mahsa and Allahgholizadeh Haghi, Benyamin and Taghavi, Milad and Farivar, Masoud and Emami-Neyestanak, Azita},
  title   = {Energy-Efficient Classification for Resource-Constrained Biomedical Applications},
  journal = {IEEE Journal on Emerging and Selected Topics in Circuits and Systems},
  volume  = {8},
  number  = {4},
  pages   = {693--707},
  year    = {2018},
  doi     = {10.1109/JETCAS.2018.2844733}
}

@article{shin2022neuraltree,
  author  = {Shin, Uisub and Ding, Cong and Zhu, Bingzhao and Vyza, Yashwanth and Trouillet, Alix and Revol, Emilie and Lacour, St{\'e}phanie and Shoaran, Mahsa},
  title   = {{NeuralTree}: A 256-Channel 0.227-$\mu${J}/Class Versatile Neural Activity Classification and Closed-Loop Neuromodulation {SoC}},
  journal = {IEEE Journal of Solid-State Circuits},
  volume  = {57},
  number  = {11},
  pages   = {3243--3257},
  year    = {2022},
  doi     = {10.1109/JSSC.2022.3204508},
  eprint  = {2205.06090},
  archivePrefix = {arXiv}
}

% volume (6, by year) and pages not confirmed by a source; check on IEEE Xplore
@article{wang2018access,
  author  = {Wang, Hongda and Shi, Weiwei and Choy, Chiu-Sing},
  title   = {Hardware Design of Real Time Epileptic Seizure Detection Based on {STFT} and {SVM}},
  journal = {IEEE Access},
  year    = {2018},
  doi     = {10.1109/ACCESS.2018.2870883}
}

@article{elhosary2019tbcas,
  author  = {Elhosary, Heba and Zakhari, Michael H. and Elgammal, Mohamed A. and Abd El Ghany, Mohamed A. and Salama, Khaled N. and Mostafa, Hassan},
  title   = {Low-Power Hardware Implementation of a Support Vector Machine Training and Classification for Neural Seizure Detection},
  journal = {IEEE Transactions on Biomedical Circuits and Systems},
  volume  = {13},
  number  = {6},
  pages   = {1324--1337},
  year    = {2019},
  doi     = {10.1109/TBCAS.2019.2947044}
}

@article{razi2022tbcas,
  author  = {Farhang Razi, Keyvan and Schmid, Alexandre},
  title   = {Epileptic Seizure Detection With Patient-Specific Feature and Channel Selection for Low-power Applications},
  journal = {IEEE Transactions on Biomedical Circuits and Systems},
  volume  = {16},
  number  = {4},
  pages   = {626--635},
  year    = {2022},
  doi     = {10.1109/TBCAS.2022.3188966}
}

% first page 1175 per the published PDF header; end page not verified
@article{busia2025fpga,
  author  = {Busia, Paola and Leone, Gianluca and Matticola, Andrea and Raffo, Luigi and Meloni, Paolo},
  title   = {Wearable Epilepsy Seizure Detection on {FPGA} With Spiking Neural Networks},
  journal = {IEEE Transactions on Biomedical Circuits and Systems},
  volume  = {19},
  number  = {6},
  year    = {2025},
  doi     = {10.1109/TBCAS.2025.3575327}
}

@inproceedings{sopic2018eglass,
  author    = {Sopic, Dionisije and Aminifar, Amir and Atienza, David},
  title     = {e-{Glass}: A Wearable System for Real-Time Detection of Epileptic Seizures},
  booktitle = {2018 IEEE International Symposium on Circuits and Systems (ISCAS)},
  year      = {2018},
  doi       = {10.1109/ISCAS.2018.8351728}
}

@article{busia2024eegformer,
  author  = {Busia, Paola and Cossettini, Andrea and Ingolfsson, Thorir Mar and Benatti, Simone and Burrello, Alessio and Jung, Victor J. B. and Scherer, Moritz and Scrugli, Matteo A. and Bernini, Adriano and Ducouret, Pauline and Ryvlin, Philippe and Meloni, Paolo and Benini, Luca},
  title   = {Reducing False Alarms in Wearable Seizure Detection With {EEGformer}: A Compact Transformer Model for {MCUs}},
  journal = {IEEE Transactions on Biomedical Circuits and Systems},
  volume  = {18},
  number  = {3},
  pages   = {608--621},
  year    = {2024},
  doi     = {10.1109/TBCAS.2024.3357509}
}

@article{ingolfsson2024brainfusenet,
  author  = {Ingolfsson, Thorir Mar and Wang, Xiaying and Chakraborty, Upasana and Benatti, Simone and Bernini, Adriano and Ducouret, Pauline and Ryvlin, Philippe and Beniczky, Sandor and Benini, Luca and Cossettini, Andrea},
  title   = {{BrainFuseNet}: Enhancing Wearable Seizure Detection Through {EEG-PPG}-Accelerometer Sensor Fusion and Efficient Edge Deployment},
  journal = {IEEE Transactions on Biomedical Circuits and Systems},
  volume  = {18},
  number  = {4},
  pages   = {720--733},
  year    = {2024},
  doi     = {10.1109/TBCAS.2024.3395534}
}

@inproceedings{hubara2016bnn,
  author    = {Hubara, Itay and Courbariaux, Matthieu and Soudry, Daniel and El-Yaniv, Ran and Bengio, Yoshua},
  title     = {Binarized Neural Networks},
  booktitle = {Advances in Neural Information Processing Systems 29 (NIPS 2016)},
  pages     = {4107--4115},
  year      = {2016},
  eprint    = {1602.02830},
  archivePrefix = {arXiv}
}

@inproceedings{umuroglu2017finn,
  author    = {Umuroglu, Yaman and Fraser, Nicholas J. and Gambardella, Giulio and Blott, Michaela and Leong, Philip and Jahre, Magnus and Vissers, Kees},
  title     = {{FINN}: A Framework for Fast, Scalable Binarized Neural Network Inference},
  booktitle = {Proceedings of the 2017 ACM/SIGDA International Symposium on Field-Programmable Gate Arrays (FPGA '17)},
  pages     = {65--74},
  publisher = {ACM},
  year      = {2017},
  doi       = {10.1145/3020078.3021744},
  eprint    = {1612.07119},
  archivePrefix = {arXiv}
}

@inproceedings{jacob2018quant,
  author    = {Jacob, Benoit and Kligys, Skirmantas and Chen, Bo and Zhu, Menglong and Tang, Matthew and Howard, Andrew and Adam, Hartwig and Kalenichenko, Dmitry},
  title     = {Quantization and Training of Neural Networks for Efficient Integer-Arithmetic-Only Inference},
  booktitle = {Proceedings of the IEEE Conference on Computer Vision and Pattern Recognition (CVPR)},
  pages     = {2704--2713},
  year      = {2018},
  doi       = {10.1109/CVPR.2018.00286},
  eprint    = {1712.05877},
  archivePrefix = {arXiv}
}

@article{duarte2018hls4ml,
  author  = {Duarte, Javier and Han, Song and Harris, Philip and Jindariani, Sergo and Kreinar, Edward and Kreis, Benjamin and Ngadiuba, Jennifer and Pierini, Maurizio and Rivera, Ryan and Tran, Nhan and Wu, Zhenbin},
  title   = {Fast inference of deep neural networks in {FPGAs} for particle physics},
  journal = {Journal of Instrumentation},
  volume  = {13},
  number  = {07},
  pages   = {P07027},
  year    = {2018},
  doi     = {10.1088/1748-0221/13/07/P07027},
  eprint  = {1804.06913},
  archivePrefix = {arXiv}
}

% ---- Reserve entries ----

@article{huang2020jssc,
  author  = {Huang, Shuo-An and Chang, Kai-Chieh and Liou, Horng-Huei and Yang, Chia-Hsiang},
  title   = {A 1.9-{mW} {SVM} Processor With On-Chip Active Learning for Epileptic Seizure Control},
  journal = {IEEE Journal of Solid-State Circuits},
  volume  = {55},
  number  = {2},
  pages   = {452--464},
  year    = {2020},
  doi     = {10.1109/JSSC.2019.2954775}
}

@article{vittimberga2025sensors,
  author  = {Vittimberga, Andrea and Nicolini, Giovanni and Scotti, Giuseppe},
  title   = {Real-Time Multi-Channel Epileptic Seizure Detection Exploiting an Ultra-Low-Complexity Algorithm--Hardware Co-Design Approach},
  journal = {Sensors},
  volume  = {25},
  number  = {22},
  pages   = {6889},
  year    = {2025},
  doi     = {10.3390/s25226889}
}

@article{kartsch2019biowolf,
  author  = {Kartsch, Victor and Tagliavini, Giuseppe and Guermandi, Marco and Benatti, Simone and Rossi, Davide and Benini, Luca},
  title   = {{BioWolf}: A Sub-10-{mW} 8-Channel Advanced Brain--Computer Interface Platform With a Nine-Core Processor and {BLE} Connectivity},
  journal = {IEEE Transactions on Biomedical Circuits and Systems},
  volume  = {13},
  number  = {5},
  pages   = {893--906},
  year    = {2019},
  doi     = {10.1109/TBCAS.2019.2927551}
}

% DOI not verified
@inproceedings{ingolfsson2022artifact,
  author    = {Ingolfsson, Thorir Mar and Cossettini, Andrea and Benatti, Simone and Benini, Luca},
  title     = {Energy-Efficient Tree-Based {EEG} Artifact Detection},
  booktitle = {44th Annual International Conference of the IEEE Engineering in Medicine \& Biology Society (EMBC)},
  pages     = {3723--3728},
  year      = {2022},
  eprint    = {2204.09577},
  archivePrefix = {arXiv}
}
```

## (c) Research gaps

Apart from BrainFuseNet, which adds PPG and accelerometer (not ECG or EMG), every hardware detector surveyed here
classifies EEG only, mostly paediatric scalp EEG from CHB-MIT or intracranial EEG, and none is evaluated on SeizeIT2's
behind-the-ear multimodal wearable recordings. Most ASIC and FPGA detectors are trained per patient (Bin Altaf
2015/2016, Wang 2018, Shoaran 2018, Farhang Razi 2022) and report epoch-level sensitivity/specificity, F1 or
percentage false alarms; event-level false alarms per hour on held-out patients are rare, and even the papers that give
FP/h (Wang 2018, Busia 2025, EEGformer, BrainFuseNet) rely mainly on CHB-MIT or count at segment/sample level. The arithmetic is mostly
multiply-accumulate (SVM kernels, CNNs and transformers on DSP blocks or MCU MAC units), while tree-based chips
(Shoaran 2018, NeuralTree) and the SNN on a small iCE40 FPGA (Busia 2025) show that comparator- or accumulate-only
logic can reach nJ to µJ per decision. Even so, no surveyed detector maps the whole classifier into FPGA lookup tables,
and the FPGA papers rarely give a LUT/FF/DSP breakdown in their abstracts. Hardware figures are reported in
incompatible units (energy per feature vector, per classification or per inference; programmable-logic or dynamic
power; µs compute time against seconds of detection delay), so a fair comparison needs one stated budget such as
energy per decision at a fixed decision rate together with FP/24 h. Finally, the general tools (FINN, hls4ml,
integer-only quantisation, BNNs) have not been applied to inter-patient, multimodal (EEG + ECG + EMG + motion)
wearable seizure detection, which is the gap SeizeLUT targets.
