# Notes from the SeizeIT2 dataset paper (Bhagubai et al., Sci. Data 12:1228, 2025)

Read from the published PDF (pages 2-7). Not copied into the repository (CC BY-NC-ND).

## SVM baseline (p. 6-7): what the paper specifies
* Based on Vandecasteele et al., Epilepsia 61:766-775, 2020 (paper ref. 18); input is bte-EEG from hospital equipment.
* Pre-processing: 1-25 Hz band-pass Butterworth; 2 s windows with 50 % overlap.
* Segments discarded if RMS amplitude > 150 uV or < 13 uV.
* 42 features: the original 3-channel feature set reduced to 2 channels by dropping the same-side power-asymmetry features.
  **The paper does not list the 42 features**; they are defined in Vandecasteele 2020.
* Labels: every segment annotated as seizure is used (no pruning to wearable-visible seizures, unlike the 2020 study).
* Class balance: background randomly undersampled to 5x the number of seizure segments.
* Classifier: MATLAB R2019b `fitcsvm`, RBF kernel. **C, kernel scale and standardisation are not stated** (MATLAB defaults
  would be BoxConstraint 1, KernelScale 1, Standardize false unless set).
* Post-processing (both baselines): alarms on segments with RMS < 13 uV or > 150 uV discarded; an alarm is kept if at least
  8 of the 1-s segments in a 10-s window are classified seizure; prediction threshold 0.5.
* Metrics: epoch-based and any-overlap; sensitivity and FA/h at threshold 0.5; AUROC, AUPR, AUSF (Table 2).
  Table 2: SVM 71.1 % / 11.0 FA/h / 0.6995 / 0.0810 / 0.7229; ChronoNet 84.2 % / 100.5 FA/h / 0.7921 / 0.1042 / 0.7953.

## ChronoNet baseline (p. 7)
2 s segments, 75 % overlap for seizure and 50 % for background; resample to 250 Hz; Butterworth 0.5 Hz high-pass, 60 Hz
low-pass, 50 Hz notch; background undersampled to 5x seizure segments. Matches our port of the official code
(`src/models/baselines/official.py`).

## Centres and age (Fig. 1, p. 3)
Leuven 45 adults (M 24, F 21) + 15 children; Coimbra 22 (M 15, F 7); Freiburg 21 (M 5, F 16); Karolinska 17 (M 9, F 8);
Aachen 5 (M 3, F 2). Total 125. **Leuven is the only centre with paediatric patients.** The per-patient centre is not
in the public release (still pending the authors' reply). The paper states 51 females; `participants.tsv` has 62 (D-audit).
1,059 h of the recordings are paediatric.

## Split (p. 5-6)
Training sub-001..096 (702 seizures), validation sub-097..125 (181 seizures), balanced for seizure count, data amount,
centre and seizure type. Matches our audit.
