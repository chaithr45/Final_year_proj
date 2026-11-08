# Chapter 1. Introduction

## 1.1 Background

<!-- BACKGROUND: written after the verified literature search (clinical need, wearables) -->

## 1.2 Why a dedicated hardware detector

A wearable seizure detector has to run for days on a small battery, close to the sensors, and raise an alarm
within seconds. Sending raw signals to a phone or a server costs radio energy and depends on a connection; running a
neural network on a microcontroller or an accelerator costs multiplications, which dominate the area and power of
digital hardware. Field-programmable gate arrays (FPGAs) offer a different trade-off: their basic logic element is a
small lookup table (LUT), typically with six inputs, that can implement any Boolean function of those inputs in one
clock cycle.

A family of recent machine-learning models, which we call **LUT-native**, is built from exactly this element:
weightless neural networks, whose neurons are truth tables [@bacellar2024], logic-gate networks [@petersen2022],
and LUT-based networks designed for FPGAs [@umuroglu2020]. They need no multipliers at inference time, so a
classifier can cost a few hundred to a few thousand LUTs. They have been applied to image benchmarks, physics
triggers and, very recently, ECG [@mommen2026] and EEG [@dharia2026] classification, but, to our knowledge, not to
seizure detection on multimodal wearable data.

## 1.3 Problem statement

> Can a LUT-native neural network, fed by integer features computed from behind-the-ear EEG, ECG, EMG and motion,
> detect seizures in patients it has never seen as well as the published SeizeIT2 baselines, with no multipliers in
> the classifier and a budget of a few thousand FPGA LUTs?

## 1.4 Objectives

1. Audit the SeizeIT2 dataset [@bhagubai2025] completely and reproduce its published baselines.
2. Design an integer-only feature pipeline that a hardware front end can compute bit-exactly, and show that it
   loses no accuracy against floating point.
3. Compare LUT-native models (DWN, logic-gate networks, TreeLUT, LogicNets-style networks) with software
   references (gradient-boosted trees) and multiplier-based networks (INT8 MLP, CNN/TCN, GRU) on the same features,
   splits and metrics, reporting accuracy against estimated hardware cost.
4. Extend the best LUT-native model with ideas specific to wearable seizure detection (memory across seconds,
   cheaper input encoders, adaptation to new patients, learning from a stronger model, losses for rare and noisily
   labelled events, robustness to missing sensors, interpretability), keeping only what is statistically
   significant.
5. Evaluate the final models once on the 29 held-out test patients with event-based metrics (SzCORE [@dan2024]).
6. Deliver a hardware handoff package (truth tables, thresholds, test vectors, verified reference Verilog) and
   implement the detector on an FPGA (Phase 2).

## 1.5 Expected contributions

* The first differentiable LUT-native seizure detector, and the first benchmark of LUT-family models on SeizeIT2.
* A bit-exact integer multimodal feature front end with its fixed-point specification.
* An independent reproduction of the SeizeIT2 ChronoNet baseline, including a protocol that uses no test
  information.
* Tier-2 extensions of the DWN for biosignal events (stateful LUT networks, comparator-budgeted encoders,
  missing-sensor robustness), each judged by per-patient statistics.
* A hardware handoff package that lets the FPGA implementation be checked bit for bit against the software.

## 1.6 Organisation of this report

Chapter 2 surveys the literature. Chapter 3 describes the dataset and our audit of it. Chapter 4 presents the
proposed system and the evaluation protocol. Chapter 5 reports the work done and the results so far, Chapter 6 the
challenges we met and how we solved them, and Chapter 7 the plan for Phase 2.
