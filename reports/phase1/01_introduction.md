# Chapter 1. Introduction

## 1.1 Background

Epilepsy is a common neurological disorder: an estimated 45.9 million people had active epilepsy in
2016 [@gbd2019epilepsy]. Seizures are classified by onset; focal seizures start in one part of the brain, may or may
not impair awareness, and can spread into bilateral tonic-clonic seizures [@fisher2017ilae]. Patients are often
unaware of their own seizures, so seizure diaries undercount them [@elger2018underreporting], and tonic-clonic
seizures carry a risk of sudden unexpected death in epilepsy [@ryvlin2013mortemus]. Reliable, automatic seizure
detection outside the hospital would give clinicians objective seizure counts and caregivers timely alarms.

In hospital, seizures are diagnosed with video-EEG from a full scalp electrode cap, which is not usable at home for
days. Wearable devices are recommended today only for detecting tonic-clonic seizures [@beniczky2021guideline]; for
focal seizures that do not become tonic-clonic (822 of the 883 seizures in SeizeIT2) the problem is open, and false
alarms are the main obstacle [@swinnen2026seizeit2].
Behind-the-ear EEG combined with ECG, EMG and motion sensors is a promising, discreet alternative
[@vandecasteele2020bte; @vandecasteele2021ecg], and the SeizeIT2 dataset [@bhagubai2025seizeit2] now makes it
possible to develop and evaluate detectors on 125 patients recorded with such a wearable.

## 1.2 Why a dedicated hardware detector

A wearable seizure detector has to run for days on a small battery, close to the sensors, and raise an alarm
within seconds. Sending raw signals to a phone or a server costs radio energy and depends on a connection; running a
neural network on a microcontroller or an accelerator costs multiplications, which dominate the area and power of
digital hardware. Field-programmable gate arrays (FPGAs) offer a different trade-off: their basic logic element is a
small lookup table (LUT), typically with six inputs, that can implement any Boolean function of those inputs in one
clock cycle.

A family of recent machine-learning models, which we call **LUT-native**, is built from exactly this element:
weightless neural networks, whose neurons are truth tables [@bacellar2024dwn], logic-gate networks [@petersen2022dlgn],
and LUT-based networks designed for FPGAs [@umuroglu2020logicnets]. They need no multipliers at inference time, so a
classifier can cost a few hundred to a few thousand LUTs. They have been applied to image benchmarks, physics
triggers and, very recently, ECG [@mommen2026ecg] and EEG [@dharia2026eeglgn] classification, but, to our knowledge, not to
seizure detection on multimodal wearable data.

## 1.3 Problem statement

> Can a LUT-native neural network, fed by integer features computed from behind-the-ear EEG, ECG, EMG and motion,
> detect seizures in patients it has never seen as well as the published SeizeIT2 baselines, with no multipliers in
> the classifier and a budget of a few thousand FPGA LUTs?

## 1.4 Objectives

1. Audit the SeizeIT2 dataset [@bhagubai2025seizeit2] completely and reproduce its published baselines.
2. Design an integer-only feature pipeline that a hardware front end can compute bit-exactly, and show that it
   loses no accuracy against floating point.
3. Compare LUT-native models (DWN, logic-gate networks, TreeLUT, LogicNets-style networks) with software
   references (gradient-boosted trees) and multiplier-based networks (INT8 MLP, CNN/TCN, GRU) on the same features,
   splits and metrics, reporting accuracy against estimated hardware cost.
4. Extend the best LUT-native model with ideas specific to wearable seizure detection (memory across seconds,
   cheaper input encoders, adaptation to new patients, learning from a stronger model, losses for rare and noisily
   labelled events, robustness to missing sensors, interpretability), keeping only what is statistically
   significant.
5. Evaluate the final models once on the 29 held-out test patients with event-based metrics (SzCORE [@dan2024szcore]).
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
