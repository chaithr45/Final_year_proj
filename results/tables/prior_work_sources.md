# Sources of the prior-work comparison (paper Table I)

Collected 12 Nov 2026 by reading each paper (full text where open access, otherwise abstract). Every number in the
table was read in the listed document; values marked ‡ come only from another paper's comparison table.

| Work | Source read | Numbers used |
|---|---|---|
| Altaf, Zhang, Yoo, JSSC 2015, doi 10.1109/JSSC.2015.2482498 | primary not accessible; NeuralTree (arXiv 2205.06090) Table II, column "JSSC'15"; EEGformer p. 618 | 180 nm; CHB-MIT ("MIT (14)"); 16 channels; Sens 95.7, Spec 98; 1.563 mm²/ch (estimated by NeuralTree); 2.73 µJ/class (‡) |
| Shoaran et al., JETCAS 2018, doi 10.1109/JETCAS.2018.2844733 | abstract (Semantic Scholar API) | "3074 h of intracranial EEG data from 26 patients with 393 seizures"; "F1 ... 87.86% ... block-wise"; "65-nm TSMC process, consuming 41.2 nJ/class in a total area of 540×1850 μm²"; "patient-specific" |
| Shin et al., NeuralTree, JSSC 2022, doi 10.1109/JSSC.2022.3204508 | arXiv accepted manuscript 2205.06090 v3 | 65 nm; "active area of 3.48mm2"; 983 h EEG of 24 patients, 596 h iEEG of 6; patient-specific; "95.6%/94% sensitivity and 96.8%/96.9% specificity"; "0.227µJ/class" |
| Vittimberga, Nicolini, Scotti, Sensors 2025, doi 10.3390/s25226889 | full text (Europe PMC PMC12655991) | Artix-7 XC7A100T, 4-channel synthesis; Table 1: 192 LUT, 500 FF, 3 DSP, 0.5 BRAM; CHB-MIT 5 patients, per-patient calibration; sample-based sensitivity "over 98%"; power not reported |
| Busia et al., TBioCAS 2025, doi 10.1109/TBCAS.2025.3575327 | full text (iris.unica.it, CC BY) | Lattice iCE40UP5K; CHB-MIT 9 subjects; patient-specific; 4 temporal EEG channels; Table IV: event sensitivity 100 %, 0.3 FP/h; Table VI: 3271 LC, 2 DSP, 14 BRAM; "core energy consumption per inference of 4.55 nJ" |
| Busia et al., EEGformer, TBioCAS 2024, doi 10.1109/TBCAS.2024.3357509 | full text (iris.unica.it, CC BY) | GAP9; CHB-MIT 8 patients; subject-independent pre-training + subject-specific fine-tuning; 4 EEG channels; event sensitivity 73 % (32/44), 0.15 FP/h; 150 kB, 14.7 MOPS; Table XI: 0.31 mJ per inference (GAP9) |
| Ingolfsson et al., BrainFuseNet, TBioCAS 2024, doi 10.1109/TBCAS.2024.3395534 | full text (iris.unimore.it, CC BY) | GAP9; PEDESITE 6 patients (EEG 4 ch + PPG + ACC); subject-specific; Table VI: 95 % events detected, 0.58 FP/day; 2,293,696 MACs; "0.11 mJ per inference" |
| Bhagubai et al., SeizeIT2, Sci. Data 2025, doi 10.1038/s41597-025-05580-x | full text (uploaded copy) | Table 2: SVM Sens 71.1, FA/h 11.0; ChronoNet 84.2, 100.5 (on sub-097..125, called the validation set); SVM on 2-channel bte-EEG |
| de Aguiar et al., EMBC 2015, doi 10.1109/EMBC.2015.7319387 | abstract (PubMed) | WiSARD; four EPILEPSIAE patients; accuracy only (not in the table) |
