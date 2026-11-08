## 2.6 Research gaps and how this project addresses them

| # | Gap found in the literature | Evidence | How this project addresses it |
|---|---|---|---|
| 1 | No LUT-native (weightless, logic-gate or LUT) seizure detector exists | Sections 2.4, 2.5: LUT networks are benchmarked on images, physics and tabular data; the only weightless seizure work is a 4-patient WiSARD study [@deaguiar2015wisard] | First benchmark of DWN, LGN, TreeLUT and LogicNets-style networks for seizure detection, on SeizeIT2 (M4) |
| 2 | Hardware detectors use EEG alone, although fusion is the most consistent way to cut false alarms | Section 2.2 [@vandecasteele2021ecg; @zhang2024tcs]; Section 2.5 | Integer features from behind-the-ear EEG, ECG, EMG and motion in one bit-exact front end (M3) |
| 3 | Missing sensors are rarely handled; LUT networks never | Section 2.2 [@zhang2024cyclic]; Section 2.4 | Presence bits, modality dropout, reliability-gated and late fusion, and missing-sensor tests (N6) |
| 4 | The encoder's hardware cost is ignored, although it dominates small LUT networks | [@mecik2025thermo]; our estimate: about 850 of 960 LUTs | Cost model that counts every comparator; comparator-budgeted and learned encoders (N2) |
| 5 | LUT networks are stateless; seizures unfold over tens of seconds | Section 2.4 [@buhrer2025rdlgn] | A stateful DWN with state bits fed back every second (N1) |
| 6 | Results are patient-specific, leak between training and test, or are scored with incomparable metrics | Section 2.3 [@brookshire2024leakage; @ziyabari2017metrics; @dan2025szcorechallenge] | Patient-wise cross-validation, a locked test set used once, SzCORE event metrics with the paper's metrics alongside |
| 7 | Small models learn from noisy labels and from larger models only in floating point | Section 2.3 [@shama2026bundl; @zheng2023kdgnn] | Noise-robust and multiple-instance losses (N5) and distillation from LightGBM (N4) into a LUT network |
| 8 | Detectors are black boxes | Section 2.4 | Tracing alarms to the inputs read by each LUT (N7) |
| 9 | Published wearable baselines are not independently reproduced | Section 2.2 | Independent reproduction of the SeizeIT2 ChronoNet baseline, with and without test-patient information (M2) |
