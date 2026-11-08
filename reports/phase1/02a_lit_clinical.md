# Chapter 2. Literature survey

The survey covers four areas, from the clinical problem to the hardware: (2.1) epilepsy and why seizures need to
be detected automatically, (2.2) wearable and multimodal seizure detection, including behind-the-ear EEG and the
SeizeIT project, (2.3) detection algorithms and how they are evaluated, (2.4) LUT-native, weightless and logic
networks, and (2.5) hardware seizure detectors and efficient inference. Section 2.6 summarises the research gaps
and how this project addresses them. Every reference was checked against a published record (title, authors,
venue, year); numbers quoted from a paper are as reported in its abstract unless stated otherwise.

## 2.1 Epilepsy and the need for automatic seizure detection

Epilepsy affected an estimated 45.9 million people with active epilepsy in 2016 [@gbd2019epilepsy]. The ILAE 2017
operational classification [@fisher2017ilae] divides seizures by onset into focal and generalised; focal seizures
are further described by whether the patient stays aware (focal aware, focal impaired awareness), and a focal
seizure can spread into a focal to bilateral tonic-clonic seizure. These are the classes annotated in SeizeIT2.

Patients are often unaware of their own seizures, which Elger and Hoppe identify as the main cause of seizure
under-reporting [@elger2018underreporting]; seizure diaries therefore undercount, and treatment decisions are made
on incomplete information. Seizures are also dangerous: in the MORTEMUS study of sudden unexpected death in epilepsy
(SUDEP) in monitoring units, the fatal cardiorespiratory dysfunction followed a generalised tonic-clonic seizure
[@ryvlin2013mortemus]. Objective, automatic seizure counting outside the hospital is therefore a clinical need, both
to alert caregivers and to give clinicians reliable seizure counts.

The ILAE–IFCN clinical practice guideline [@beniczky2021guideline] gives a (weak) recommendation for wearable
devices that detect generalised and focal to bilateral tonic-clonic seizures, and does not recommend current devices
for other seizure types. Detecting **focal** seizures, the majority in focal epilepsy, with a wearable remains an
open problem.

## 2.2 Wearable and multimodal seizure detection

**Reviews and devices.** A review of multimodal wearable detection [@leijten2018review] found sensitivities from 4 %
to 100 % across studies, with tonic-clonic seizures detected best. A wearable EMG device detected tonic-clonic seizures
with more than 90 % sensitivity in a 71-patient prospective study [@beniczky2018emg], and wrist-worn
electrodermal-activity and accelerometer sensors reached 94.55 % sensitivity at 0.2 false alarms per day for
convulsive seizures [@onorati2017empatica]. A meta-analysis [@naganur2022meta] pooled a sensitivity of 0.91 for
tonic-clonic seizures at 2.1 false alarms per 24 hours. All of this evidence concerns convulsive seizures.

**Behind-the-ear EEG and the SeizeIT project.** EEG is the most direct signal of a seizure, but a full scalp EEG is
not wearable for days. The SeizeIT project records EEG from electrodes behind the ears. Vandecasteele et al.
[@vandecasteele2020bte] showed that seizures can be annotated and detected on behind-the-ear EEG, with a
patient-specific detector at 69.1 % sensitivity and 0.49 false positives per 24 h and a patient-independent one at
64.1 % and 2.8 per 24 h. Adding ECG to a two-channel EEG detector raised sensitivity by 8–11 % at the same false-alarm
rate [@vandecasteele2021ecg], and helped human reviewers too: with ECG, false detections fell from 6.5 to 2.4 per day
[@bhagubai2023ecg]. The ICASSP 2023 Grand Challenge on wearable-EEG seizure detection [@bhagubai2024challenge] was won
by an ensemble of decision trees. SeizeIT2 [@bhagubai2025seizeit2] then released 125 patients with more than 11,000
hours of behind-the-ear EEG, ECG, EMG and motion, with ChronoNet and SVM baselines; it is the dataset of this
project. A multicentre clinical validation of the same wearable on 192 adults [@swinnen2026seizeit2] reached an
algorithmic sensitivity of 0.73 at a precision of only 0.004 (most alarms false) before human review, which shows
that **false alarms are the main obstacle** for focal seizures.

**Other work on SeizeIT2.** A study of tonic-clonic seizures in the SeizeIT2 cohort [@zhang2024tcs] fused EEG, EMG
and accelerometry and reached 90.9 % sensitivity at 0.1 false positives per 24 h, against 100 % at 10.3 per 24 h for
EEG alone: fusion mainly removes false alarms. ECG-only anomaly detection [@reintjes2025ecg] and a complex-valued
multimodal network (CMEpiNet) [@su2026cmepinet] have also been applied to SeizeIT2; none of these reports a hardware
budget.

**Fusion and missing modalities.** BrainFuseNet [@ingolfsson2024brainfusenet] fused EEG, PPG and accelerometry and
ran on a microcontroller (64.28 % sensitivity at 0.21 false positives per hour). A cyclic transformer trained on EEG
and EMG but tested on EEG alone [@zhang2024cyclic] is the only work we found that targets a missing modality at test
time.

| Work | Year | Signals | Seizures / patients | Result (as reported) | Gap for our problem |
|---|---|---|---|---|---|
| Beniczky et al. [@beniczky2018emg] | 2018 | EMG | tonic-clonic, 71 patients | > 90 % sensitivity | convulsive only |
| Onorati et al. [@onorati2017empatica] | 2017 | EDA + ACC | convulsive | 94.55 %, 0.2 FA/day | convulsive only |
| Naganur et al. [@naganur2022meta] | 2022 | meta-analysis | tonic-clonic | 0.91 sens., 2.1 FA/24 h | focal not solved |
| Vandecasteele et al. [@vandecasteele2020bte] | 2020 | bte-EEG | focal | 64.1 %, 2.8 FP/24 h (patient-independent) | EEG only |
| Vandecasteele et al. [@vandecasteele2021ecg] | 2021 | bte-EEG + ECG | focal | +8–11 % sensitivity with ECG | software only |
| Bhagubai et al. [@bhagubai2024challenge] | 2024 | bte-EEG | challenge | tree ensemble won | no hardware budget |
| Zhang et al. [@zhang2024tcs] | 2024 | EEG + EMG + ACC | tonic-clonic | 90.9 %, 0.1 FP/24 h | tonic-clonic only |
| Swinnen et al. [@swinnen2026seizeit2] | 2026 | wearable (SeizeIT2 device) | focal, 192 adults | 0.73 sens. at 0.004 precision | false alarms |
| BrainFuseNet [@ingolfsson2024brainfusenet] | 2024 | EEG + PPG + ACC | — | 64.28 %, 0.21 FP/h, MCU | multipliers, no missing-sensor test |
| Zhang et al. [@zhang2024cyclic] | 2024 | EEG + EMG | — | — | transformer, large model |

**Gap.** Wearable detection is clinically established only for tonic-clonic seizures. For focal seizures, fusion of
EEG with ECG, EMG and motion is the most consistent way to raise sensitivity and cut false alarms, but the published
fusion detectors are software models or multiply-accumulate networks on microcontrollers, and only one handles a
missing sensor.
