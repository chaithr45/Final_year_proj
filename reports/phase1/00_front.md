---
title: "SeizeLUT: A LUT-Native Multimodal Seizure Detector for Wearable Devices"
subtitle: "B.Tech Major Project, Phase 1 Report"
author:
  - "[Student name 1 (roll number)], [Student name 2 (roll number)], [Student name 3 (roll number)]"
  - "Guide: [Guide name], [Designation]"
  - "Department of [Department], National Institute of Technology Warangal"
date: "November 2026"
lang: en-GB
---

# Abstract

Automatic seizure detection with wearable sensors could give people with epilepsy objective seizure counts and
timely alarms, but the detector must run for days on a small battery next to the sensors. This project asks whether
a **LUT-native** neural network, whose neurons are the lookup tables (LUTs) that make up an FPGA, can detect seizures
from behind-the-ear EEG, ECG, EMG and motion signals in patients it has never seen, with no multipliers in the
classifier and a budget of a few thousand LUTs.

We use SeizeIT2, a public wearable dataset of 125 patients with focal epilepsy (11,626 hours, 883 seizures), with its
official split into 96 training and 29 test patients. Phase 1, the first two months of the project, covered: a complete audit of the dataset, which found
that it differs from its documentation (256 Hz instead of 250 Hz, 883 instead of 886 seizures); an independent
reproduction of the published ChronoNet baseline, which was only partly reproduced and whose released code selects
its model on the test patients; a bit-exact integer feature pipeline of 117 features that loses no accuracy against
floating point (AUROC 0.736 vs 0.735); and a comparison of nine model families with patient-wise cross-validation
and event-based SzCORE metrics.

So far, on cross-validation of the 96 training patients, a Differentiable Weightless Neural Network of 50 six-input
LUTs reaches an event-F1 of 0.211 with 2.4 false alarms per day at an estimated 960 LUTs and no multipliers. It is
seven to eight times smaller than the next LUT-based models (TreeLUT, logic-gate network) and better than an INT8 neural
network that needs 9,600 multiplications per decision, but below gradient-boosted trees (event-F1 0.292). It
detects 88 % of tonic-clonic seizures but few focal seizures, and depends on the ECG signal. An interpretability
study of the network led to a better feature selection that raised its event-F1 from 0.148 to 0.208.

The literature survey of 79 verified references found no LUT-native seizure detector and no LUT network that fuses
modalities or handles missing sensors. Phase 2 will complete the extensions of the network, evaluate the final
models once on the 29 held-out test patients, and implement the detector on an FPGA.

**Keywords:** epilepsy, seizure detection, wearable EEG, behind-the-ear EEG, multimodal fusion, weightless neural
networks, lookup tables, FPGA, SeizeIT2.
