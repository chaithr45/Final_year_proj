## 2.3 Seizure detection algorithms and their evaluation

**Feature-based detectors.** Shoeb and Guttag [@shoeb2010icml] trained a patient-specific support vector machine on
EEG spectral features and detected 96 % of 173 test seizures on the CHB-MIT scalp EEG database, with a median
latency of 3 s and 2 false detections per 24 h. Patient-specific training needs seizures of the same patient,
which a wearable for new patients does not have. On wearable behind-the-ear EEG, the winner of the ICASSP 2023 Grand
Challenge, SeizFt [@alhussaini2023seizft], used hand-crafted features, Fourier-transform-surrogate augmentation and a
gradient-boosted tree ensemble (CatBoost); a random forest on band-power features reached 73.6 % sensitivity and
96.7 % specificity in the same challenge [@huang2023lightweight]. Tree ensembles are the strongest published
approach on SeizeIT data, which is why LightGBM, XGBoost and CatBoost are our software references.

**Deep-learning detectors.** ChronoNet [@roy2019chrononet] stacks multi-scale one-dimensional convolutions and
densely connected GRU layers on raw EEG; it was designed for abnormal-EEG classification and is the deep baseline
of SeizeIT2. In the ICASSP 2023 challenge, ChronoNet trained on SeizeIT1 reached only 15.2 % sensitivity on the
SeizeIT2 validation patients [@huang2023lightweight]. EEGNet [@lawhern2018eegnet] is a compact convolutional network
for EEG with depthwise and separable convolutions; EEGWaveNet [@thuwajit2022eegwavenet] extracts multiscale features
with trainable depthwise convolutions and improves subject-independent detection on CHB-MIT and TUSZ; graph neural
networks with self-supervised pre-training [@tang2022gnnssl] reached a detection AUROC of 0.875 on TUSZ but need a
full electrode montage to build the graph; U-Net transformers [@wu2025seizuretransformer] and multi-signal
transformers such as BIOT [@yang2023biot] push accuracy further with much larger models. These networks are
floating-point and multiplier-based; their size is reported in parameters, not in hardware cost.

**Learning from imperfect labels.** Seizure onset and offset are uncertain even for experts. Weak supervision with
noisy clinical labels [@saab2020weak], attention-based multiple-instance learning when only time periods are labelled
[@isaev2020mil], and uncertainty-aware training with noisy labels (BUNDL) [@shama2026bundl] address this on scalp EEG.
Knowledge distillation from a full-montage teacher into a two-channel student [@zheng2023kdgnn] keeps detection
competitive with very few channels. These ideas motivate our extensions N4 (distillation) and N5 (noise-robust and
multiple-instance losses), applied for the first time to a LUT network.

**Datasets and evaluation.** Most detectors are developed on scalp EEG: CHB-MIT and the TUH Seizure Corpus
(315 subjects in its 2018 release) [@shah2018tusz]. How a detector is scored changes its numbers: epoch-based
scoring, any-overlap event scoring (OVLP) and time-aligned event scoring (TAES) give different results for the same
system [@ziyabari2017metrics]. SzCORE [@dan2024szcore] standardised data formats, cross-validation and event-based
metrics (sensitivity, precision, F1, false positives per day, any-overlap matching) with an open-source scorer. In the
first blind SzCORE challenge [@dan2025szcorechallenge], on 65 unseen subjects and 4,360 hours of EEG, the best
algorithm reached an event-F1 of 43 % (sensitivity 37 %, precision 45 %), and reported results did not hold up on
blind data. Data leakage, letting a subject's data appear in both training and test sets, is common in EEG deep
learning and inflates results [@brookshire2024leakage].

| Work | Year | Method | Data | Result (as reported) | Gap for our problem |
|---|---|---|---|---|---|
| Shoeb & Guttag [@shoeb2010icml] | 2010 | patient-specific SVM | CHB-MIT | 96 % of seizures, 2 FD/24 h | patient-specific, scalp EEG |
| SeizFt [@alhussaini2023seizft] | 2023 | features + CatBoost | SeizeIT1/2 | ICASSP 2023 winner | EEG only, no hardware cost |
| Huang et al. [@huang2023lightweight] | 2023 | random forest; ChronoNet | SeizeIT1/2 | RF 73.6 % sens.; ChronoNet 15.2 % | EEG only |
| ChronoNet [@roy2019chrononet] | 2019 | CNN + GRU | TUH abnormal EEG | new benchmark at the time | large, multiplier-based |
| EEGWaveNet [@thuwajit2022eegwavenet] | 2022 | multiscale CNN | CHB-MIT, TUSZ | better subject-independent | scalp EEG, float CNN |
| Tang et al. [@tang2022gnnssl] | 2022 | self-supervised GNN | TUSZ | AUROC 0.875 | needs full montage |
| BUNDL [@shama2026bundl] | 2026 | noisy-label training | TUH, CHB-MIT | more robust to label noise | scalp EEG |
| Zheng et al. [@zheng2023kdgnn] | 2023 | distilled GNN | TUSZ | competitive with 2 channels | float GNN student |
| SzCORE [@dan2024szcore] | 2024 | evaluation framework | scalp EEG | standard event metrics | not for wearables |
| SzCORE challenge [@dan2025szcorechallenge] | 2025 | blind benchmark | 65 subjects | best event-F1 43 % | scalp EEG |

**Gap.** Strong detectors are mostly patient-specific or scalp-EEG based, floating-point and large, and they are
scored in ways that cannot be compared. On blind, unseen patients even the best reach an event-F1 below 50 %. A
small detector for wearable multimodal data, scored with SzCORE-style event metrics on strictly held-out patients,
is still missing.
