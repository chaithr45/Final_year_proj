# Literature re-check (Section 2), 2026-11-06

Search terms: weightless / differentiable weightless / DWN / logic gate network / difflogic /
LUT network / LogicNets / TreeLUT / PolyLUT / NeuraLUT / AmigoLUT combined with seizure / epilepsy /
EEG / ECG / biosignal / wearable; and SeizeIT2 with FPGA / hardware / low-power / edge.

**Limit of this check.** It was done through web search summaries; arxiv.org and publisher pages
could not be opened from the coding environment. Every number marked *snippet* must be checked in
the PDF before it is cited.

## Verdict per contribution

| Claim | Verdict | What narrows it |
|---|---|---|
| C1 first LUT-native seizure detector; first LUT-family benchmark on SeizeIT2 | **Still novel, narrower wording** | No DWN/LGN/LogicNets/TreeLUT seizure detector found; no FPGA/hardware work on SeizeIT2 found. But LGN/LUT nets already used on ECG (Mommen et al., arXiv:2601.11433) and LGNs on EEG (Dharia et al., arXiv:2607.18149, PMLR 318); WiSARD (older weightless net) used for EEG seizure *anticipation* (EMBC 2015). Say "first *differentiable* LUT-native seizure detector" and "first LUT-family benchmark on SeizeIT2", not "first on a clinical biosignal". |
| C2 stateful LUT network | **Partially pre-empted** | Recurrent deep differentiable logic gate networks with flip-flop-like state (Bührer et al., arXiv:2508.06097). Mommen et al., arXiv:2607.09399, list recurrent LUT networks as future work. A recurrent DWN/LUT6 network for biosignal events still looks open; cite both. |
| C3 hardware-aware thermometer encoding | **Partially pre-empted** | Mecik & Kumm (arXiv:2512.15251, Asilomar 2025) quantify encoder cost; Differentiable Weightless Controllers (arXiv:2512.01467) treat thresholds as integer comparisons; BTHOWeN (arXiv:2203.01479) uses non-uniform thermometers. *Comparator-budgeted* threshold selection plus pruning of never-read bits: not found. |
| C4 label-free per-patient threshold adaptation | **Still novel** (for LUT/DWN) | Generic biosignal test-time calibration exists (PMLR v287, Jo et al. 2025); per-patient bte-EEG transfer exists but is supervised (arXiv:2512.02626). |
| C5 MIL + noise-robust losses + distillation into a LUT net | **Parts exist; combination novel** | MIL for seizures (neonatal, attention MIL); noisy seizure labels (BUNDL, arXiv:2410.19815); distillation into an LGN (NeurIPS ML4PS 2025, physics trigger). |
| C6 reliability-gated multimodal fusion in a LUT net | **Still novel** | arXiv:2403.13066 (SeizeIT2 cohort) lists missing-modality-robust fusion as future work; CMEpiNet (Sensors 26(13):4186, 2026) is a deep multimodal model on SeizeIT2 without missing-modality handling. |
| C7 interpretable alarms traced to LUT inputs | **Still novel in this setting** | Interpretable logic networks for tabular medical data exist (arXiv:2407.04168). |

## Prior work in the prompt, verified

| Item | Status |
|---|---|
| Mommen et al., arXiv:2601.11433 | Confirmed: inter-patient ECG arrhythmia (MIT-BIH, 4 classes), Artix-7, 2,000–2,990 LUTs, 5–7 mW (*snippet*). |
| Dharia et al., arXiv:2607.18149 | Confirmed; also Canadian AI 2026, PMLR 318:377–391; CPU only (Jetson Orin Nano). |
| Bührer et al., arXiv:2508.06097 | Confirmed: recurrent deep differentiable LGNs, WMT'14 En-De. |
| Busia et al., IEEE TBioCAS 19(6), 2025 | Mostly confirmed: SNN on CHB-MIT, 0.3 FP/h (*snippet*); iCE40UP5K confirmed for the SYNtzulu platform, not verified in this paper's text. |
| Bhagubai et al. 2025, Table 2 | Numbers confirmed: SVM 71.1 % / 11.0 FA/h, ChronoNet 84.2 % / 100.5 FA/h. Metric definition (OVLP sensitivity, epoch false alarms) to be confirmed from the PDF in M2. |

## Other SeizeIT2 results found (none on the official split with SzCORE event scoring)

* Swinnen et al., Epilepsia Open 2026: clinical validation of the Sensor Dot (192 patients, detector trained on SeizeIT1).
* CMEpiNet, Sensors 26(13):4186, 2026: claims to beat the official SVM/ChronoNet; numbers not retrieved.
* Reintjes et al., Sensors 25(24):7687, 2025: ECG-only anomaly detection.
* Multimodal EEG World Model (medRxiv, Jul 2026): own split, segment-level metrics only.
* arXiv:2403.13066: tonic-clonic subset, EEG+EMG.
* ICASSP 2023 wearable-EEG challenge (SeizeIT2 test set): SeizFt (CatBoost), Lund RF.

## Venues

* BioCAS 2026 and ISCAS 2027 deadlines have passed.
* **EMBC 2027** (Singapore, 11–15 Jul 2027): full papers reportedly due **24 Jan 2027** (aggregator; not yet on the official site); EMBC 2026 allowed 4–7 pages.
* BioCAS 2027 (Oslo, Oct 2027): no call yet.
