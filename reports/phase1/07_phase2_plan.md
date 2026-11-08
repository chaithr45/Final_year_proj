# Chapter 7. Plan for Phase 2

Phase 2 turns the cross-validated design into final, test-set results and a working hardware implementation. The
29 test patients stay untouched until every design choice is frozen, so the final numbers are an honest estimate
of performance on new patients.

## 7.1 Work packages

| # | Work package | Content | Output |
|---|---|---|---|
| 1 | Finish the extensions (M5) | The 17 queued variants of N1, N2, N4, N5 and N6; missing-sensor tests for the fusion variants; a combination run of the extensions that win; large DWNs (500–2,000 LUTs); GRU, LogicNets-style and raw-EEG CNN/TCN references; the SVM baseline if its features become available | Ablation table with per-patient statistics; final choice of the DWN design |
| 2 | Final test (M6) | Retrain each final model (best of every family, the chosen DWN, clean ChronoNet) on all 96 training patients with 5 random seeds; score each once on the 29 test patients | Test-set table (SzCORE and paper metrics), seizure-type and missing-sensor breakdowns, confidence intervals |
| 3 | Hardware handoff (M7) | Export the final DWN (thresholds, input mapping, truth tables, popcount head); test vectors for every stage from raw samples to alarms; reference Verilog checked against the software | Handoff package with 100 % bit agreement |
| 4 | FPGA implementation | Synthesis and place-and-route on a low-power FPGA (device chosen with the guide); measured LUTs, flip-flops, clock frequency, latency and estimated power; the INT8 MLP and TreeLUT baselines on the same device for comparison | Hardware results table; demonstration of a recording streamed through the design |
| 5 | Paper and final report (M8) | Conference paper (target: EMBC 2027; full papers reportedly due 24 January 2027, to be confirmed on the official site) and the final B.Tech report | Paper draft, final report, presentation |

## 7.2 Timeline

| Period | Work |
|---|---|
| Weeks 1–2 after the Phase 1 review | Work package 1: remaining M5 experiments and decisions |
| Week 3 | Work packages 2 and 3: final test and hardware handoff |
| Weeks 4–8 | Work package 4: FPGA implementation and measurements |
| Weeks 8–10 | Work package 5: paper, final report, demonstration |

The machine-learning experiments run unattended on the cloud machine and the laptop GPU, so most of work package 1
proceeds in parallel with the Phase 1 review.

## 7.3 Expected outcome

A seizure detector for multimodal wearable signals that

* uses integer arithmetic end to end and **no multipliers in the classifier**;
* fits in **about one thousand LUTs** for the classifier and encoder (current estimate: about 960);
* is evaluated **on 29 unseen patients** with event-based metrics, against the published ChronoNet baseline,
  gradient-boosted trees and an INT8 neural network;
* states exactly which seizure types it detects and how it behaves when a sensor is missing.

## 7.4 Risks

| Risk | Mitigation |
|---|---|
| The DWN stays below the tree models | Report it honestly as an accuracy-per-LUT trade-off (the DWN is about 6.6 times smaller than TreeLUT); the extensions and larger networks are designed to narrow the gap |
| Focal seizures remain mostly undetected | Report sensitivity per seizure type, and the same breakdown for the published ChronoNet baseline on the same test patients |
| Test results lower than cross-validation | Expected to some degree; the test set is used once and reported as measured |
| FPGA results differ from the estimates | The estimates are replaced by synthesis results; the handoff package and test vectors make debugging deterministic |
