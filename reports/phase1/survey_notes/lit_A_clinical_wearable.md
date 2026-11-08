# Literature survey, theme A: clinical background and wearable / multimodal seizure detection

Compiled 2026-11-08 for SeizeLUT (LUT-native multimodal seizure detector on SeizeIT2, OpenNeuro ds005873).

**How this was verified.** Every entry below was found through web search, and title, authors, venue and year were
matched against at least one bibliographic record (publisher page, PubMed, dblp, OpenAlex, PMC, institutional
repository or DOAJ/library catalogue) that the search returned. In this environment, direct page fetches failed for
www.nature.com, api.crossref.org, api.semanticscholar.org and dblp.org, so the evidence is search-result text: the
abstract text, or snippets from the indexed record. A number appears only where that text stated it. "abstract" means
the abstract as indexed by the record in the "Verified at" column. "snippet" means record text other than the abstract.
"-" means no number could be verified. Before citing a number, check it against the full text.

20 papers are listed, more than the target of 10 to 14, because the brief named most of them. If space is tight, a
core subset of 14 is marked with **(core)** in the Ref key column.

## (a) Table

### A1. Clinical need

| Ref key | Authors (first author et al.) | Year | Title | Venue | Problem | Method / device | Data | Key result (source) | Limitation / gap relevant to our project | Verified at (URL) |
|---|---|---|---|---|---|---|---|---|---|---|
| gbd2019epilepsy **(core)** | GBD 2016 Epilepsy Collaborators | 2019 | Global, regional, and national burden of epilepsy, 1990–2016: a systematic analysis for the Global Burden of Disease Study 2016 | Lancet Neurology 18(4):357–375 | Global burden of epilepsy | Systematic analysis (GBD 2016) | 317 prevalence, 81 incidence and 23 mortality studies | 45.9 M people with active epilepsy in 2016; age-standardised prevalence 621.5 per 100,000 (abstract) | Epidemiology only, used to motivate the work. It contains nothing on detection. | https://www.healthdata.org/node/6908 ; https://openrepository.aut.ac.nz/items/ddb4f683-8f85-4fb8-9589-fdd62021f9da |
| fisher2017ilae **(core)** | Fisher RS et al. (ILAE Commission for Classification and Terminology) | 2017 | Operational classification of seizure types by the International League Against Epilepsy: Position Paper of the ILAE Commission for Classification and Terminology | Epilepsia 58(4):522–530 | A common seizure-type vocabulary | Operational (practical) revision of the 1981/2010 classification | - | "Partial" becomes "focal"; awareness classifies focal seizures; onset can be focal, generalized or unknown (abstract) | Defines the focal (aware / impaired awareness) vs focal-to-bilateral tonic-clonic (FBTC) types annotated in SeizeIT2. Detection difficulty differs sharply between these types. | https://pubmed.ncbi.nlm.nih.gov/28276060/ ; https://ilae.org/guidelines/definition-and-classification/operational-classification-2017 |
| elger2018underreporting **(core)** | Elger CE, Hoppe C | 2018 | Diagnostic challenges in epilepsy: seizure under-reporting and seizure detection | Lancet Neurology 17(3):279–288 | Seizure diaries are unreliable | Personal View (review) | - | "Lack of awareness that a seizure has occurred appears to be the primary cause for under-reporting". It calls for ambulatory long-term detection that combines autonomic (heart-rate) and movement measures (abstract) | Motivates objective wearable seizure counting. Focal impaired-awareness and nocturnal seizures are the ones missed, and they are the target class in SeizeIT2. | https://pubmed.ncbi.nlm.nih.gov/29452687/ ; https://www.sciencedirect.com/science/article/abs/pii/S1474442218300383 |
| ryvlin2013mortemus | Ryvlin P et al. | 2013 | Incidence and mechanisms of cardiorespiratory arrests in epilepsy monitoring units (MORTEMUS): a retrospective study | Lancet Neurology 12(10):966–977 | SUDEP mechanisms and incidence | Retrospective survey of 147 epilepsy monitoring units (EMUs) | 29 cardiorespiratory arrests, 16 of them SUDEP | SUDEP incidence in adult EMUs was 5.1 (95% CI 2.6–9.2) per 1000 patient-years. In the cases with recordings, terminal cardiorespiratory dysfunction followed a generalised tonic-clonic seizure (abstract) | Links SUDEP to unattended tonic-clonic seizures, which motivates real-time alarms. The data come from EMUs, not from wearables. | https://serval.unil.ch/notice/serval:BIB_AE56F6165A92 ; https://publikationen.uni-tuebingen.de/xmlui/handle/10900/41652 |
| beniczky2021guideline **(core)** | Beniczky S et al. (ILAE–IFCN working group) | 2021 | Automated seizure detection using wearable devices: A clinical practice guideline of the International League Against Epilepsy and the International Federation of Clinical Neurophysiology | Epilepsia 62(3):632–646 | When wearable seizure detection should be used clinically | Systematic review (PRISMA) with GRADE recommendations | Published validation studies | High-level evidence for GTCS and FBTCS. Weak/conditional recommendation for clinically validated devices in these types, especially in unsupervised patients. Clinical use is not recommended for other seizure types (abstract) | Says explicitly that non-convulsive (focal) seizure detection is not yet clinically usable. This is the gap SeizeIT2 and our project target. | https://www.ilae.org/guidelines/guidelines-and-reports/proposed-clinical-practice-guideline-for-automated-seizure-detection-using-wearable-devices ; https://ilae.org/files/ilaeGuideline/Automjated-seizure-detection-using-wearable-devices---epi.16818.pdf ; https://muni.cz/en/research/publications/1837301 |

### A2. Wearable devices and reviews

| Ref key | Authors (first author et al.) | Year | Title | Venue | Problem | Method / device | Data | Key result (source) | Limitation / gap relevant to our project | Verified at (URL) |
|---|---|---|---|---|---|---|---|---|---|---|
| leijten2018review **(core)** | Leijten FSS (Dutch TeleEpilepsy Consortium) | 2018 | Multimodal seizure detection: A review | Epilepsia 59(S1):42–47 | Does combining non-EEG modalities help? | Literature review | 7 papers (2010–2017): accelerometry (ACC) n=5, EMG n=2, heart rate (HR) n=2, electrodermal activity (EDA) n=1, oximetry n=1 | Sensitivity 4–100%; false detections 0.25–20 per 8 h. Tonic-clonic detection performed best. More sensors increased sensitivity; false detections fell in one study and rose in another (abstract) | Covers motor seizures and non-EEG sensors only, and the evidence base is small and heterogeneous. It contains no EEG plus non-EEG fusion for focal seizures. | https://onlinelibrary.wiley.com/doi/10.1111/epi.14047 ; https://pubmed.ncbi.nlm.nih.gov/29873832/ ; https://researchinformation.umcutrecht.nl/en/publications/multimodal-seizure-detection-a-review/ |
| beniczky2018emg | Beniczky S, Conradsen I, Henning O, Fabricius M, Wolf P | 2018 | Automated real-time detection of tonic-clonic seizures using a wearable EMG device | Neurology 90(5):e428–e434 | Real-time GTCS alarm | Wearable surface-EMG (arm) device; prespecified algorithm and cut-offs | Prospective study at 3 centres, 71 patients | Sensitivity > 90% and latency within 30 s (abstract). 30/32 GTCS detected (93.8%) and 0.67 false alarms/day (snippet) | Detects GTCS only, with a single modality (EMG). It does not address focal seizures. | https://pmc.ncbi.nlm.nih.gov/articles/PMC5791791 ; https://peeref.com/works/5723753 |
| onorati2017empatica | Onorati F, Regalia G et al. | 2017 | Multicenter clinical assessment of improved wearable multimodal convulsive seizure detectors | Epilepsia 58(11):1870–1879 | Wristband convulsive-seizure detection | Empatica wristbands, EDA + ACC, machine-learning classifiers | 69 patients, 6 sites, 5,928 h, 55 convulsive seizures | Best classifier: sensitivity 94.55%, false alarm rate (FAR) 0.2/day; median latency 29.3 s (abstract) | Convulsive seizures only, recorded in hospital. EDA/ACC carry little information for non-motor focal seizures. | https://onlinelibrary.wiley.com/doi/10.1111/epi.13899 ; https://pubmed.ncbi.nlm.nih.gov/28980315/ ; https://dspace.mit.edu/handle/1721.1/111959 |
| naganur2022meta **(core)** | Naganur V et al. | 2022 | Automated seizure detection with noninvasive wearable devices: A systematic review and meta-analysis | Epilepsia 63:1930–1941 | How accurate are wearables? | Systematic review and meta-analysis against a video-EEG reference | 28 studies (23 meta-analysed), 1,269 patients | Pooled tonic-clonic sensitivity 0.91 (95% CI 0.85–0.96); pooled FAR 2.1/24 h (wrist 2.5, surface 0.96). Focal-seizure sensitivity ranged from 31.1% to 93.1% (abstract/snippet) | The authors call for lower FAR, detection of other seizure types and longer recordings in the community, all of which apply to focal-seizure wearables. | https://findanexpert.unimelb.edu.au/scholarlywork/1678518-automated-seizure-detection-with-noninvasive-wearable-devices--a-systematic-review-and-meta-analysis ; https://cureepilepsy.org/news/automated-seizure-detection-with-non-invasive-wearable-devices-a-systematic-review-and-meta-analysis |

### A3. Behind-the-ear EEG, the SeizeIT project and SeizeIT2 users

| Ref key | Authors (first author et al.) | Year | Title | Venue | Problem | Method / device | Data | Key result (source) | Limitation / gap relevant to our project | Verified at (URL) |
|---|---|---|---|---|---|---|---|---|---|---|
| vandecasteele2020bte **(core)** | Vandecasteele K et al. | 2020 | Visual seizure annotation and automated seizure detection using behind-the-ear electroencephalographic channels | Epilepsia 61(4):766–775 | Can behind-the-ear (bte) EEG channels capture focal seizures? | bte channels derived from full-scalp video-EEG; visual review plus an automated detector | 54 patients, 182 seizures (mostly temporal lobe epilepsy, TLE), 5,284 h; UZ Leuven | Visual review: sensitivity 65.7%, specificity 94.4%. Patient-specific detector: 69.1% at 0.49 FP/24 h. Patient-independent detector: 64.1% at 2.8 FP/24 h (abstract) | The bte signals were derived from scalp EEG, not recorded with a wearable. EEG alone misses about a third of seizures, which is the argument for adding ECG/EMG. | https://repository.tudelft.nl/record/uuid:48e91477-aee2-43f2-9211-1acc13dcb5e8 ; https://omicsdi.org/dataset/biostudies-literature/S-EPMC7217054 ; https://zendy.io/title/10.1111/epi.16470 |
| vandecasteele2021ecg **(core)** | Vandecasteele K et al. | 2021 | The power of ECG in multimodal patient-specific seizure monitoring | Epilepsia 62(10):2333–2343 | Does single-lead ECG add to bte/temporal EEG? | Separate EEG and ECG machine-learning models, fused by late integration; patient-specific | 3 multicentre databases, 135 patients, 896 focal seizures | Multimodal beat EEG-only in 2 of 3 databases: +11% and +8% sensitivity at the same false-alarm rate (abstract) | Patient-specific models, so no claim about unseen patients. Fusion is late and offline, with no hardware budget. | https://repository.tudelft.nl/record/uuid:69d523e4-1bb8-463c-823c-2dbd62a13a7f ; https://pmc.ncbi.nlm.nih.gov/articles/PMC8518059 ; https://ubmr.hds.hebis.de/Record/HEB499055551 |
| bhagubai2023ecg | Bhagubai M et al. | 2023 | The Power of ECG in Semi-Automated Seizure Detection in Addition to Two-Channel behind-the-Ear EEG | Bioengineering 10(4):491 | Does ECG help human review of algorithm alarms? | Multimodal algorithm produces alarms; 2 reviewers read them with bte-EEG only, then with bte-EEG + ECG + HR | SeizeIT1: 42 patients with focal epilepsy | bte-EEG only: mean sensitivity 59.1%, 6.5 false detections/day. With ECG: 62.2% and 2.4/day; inter-rater agreement improved (abstract) | Semi-automated (needs a clinician to review). Shows that ECG mainly removes false alarms. | https://www.ncbi.nlm.nih.gov/pmc/articles/PMC10136326/ ; https://www.mdpi.com/2306-5354/10/4/491/notes ; https://ouci.dntb.gov.ua/works/45w2pzj9 |
| bhagubai2024challenge **(core)** | Bhagubai M et al. | 2024 | Towards Automated Seizure Detection With Wearable EEG – Grand Challenge | IEEE Open Journal of Signal Processing 5:717–724 | Report of the ICASSP 2023 Seizure Detection Challenge | Open challenge: train on bte-EEG, evaluate on recordings from the bte-EEG wearable; includes a data-centric subtask | Training: 42 patients with focal epilepsy (SeizeIT1). Held-out evaluation: wearable bte-EEG recordings | Presents the 5 best methods. The winner was a feature-based decision-tree ensemble with Fourier-transform-surrogate augmentation (abstract). Scores: - | EEG only (no ECG/EMG/motion), and the main obstacle named is lack of training data. Lightweight tree ensembles won, which supports small models. | https://doaj.org/article/f808625d83b948468b601ad4592d927c ; https://ieeexplore.ieee.org/document/10474132/authors ; https://signalprocessingsociety.org/publications-resources/data-challenges/seizure-detection-challenge-icassp-2023 |
| bhagubai2025seizeit2 **(core)** | Bhagubai M et al. | 2025 | SeizeIT2: Wearable Dataset Of Patients With Focal Epilepsy | Scientific Data (Nature Portfolio) | No open wearable focal-epilepsy dataset existed | Sensor Dot (Byteflies) wearable: bte-EEG, ECG, EMG, accelerometer, gyroscope; BIDS on OpenNeuro | 125 patients, 5 European EMUs, > 11,000 h, 883 focal seizures (journal abstract; the arXiv 2502.01224 preprint says 886) | First open dataset of wearable data from patients with focal epilepsy. Proposes a training/validation split, two benchmark approaches and evaluation metrics (abstract). Benchmark numbers: - | This is our dataset. The benchmark numbers could not be verified here (nature.com unreachable); take them from the paper itself. | https://library.kab.ac.ug/Record/doaj-art-b4461b0d68014a9cb04e887eb6caab9e/Description ; https://pdf.arxiv.org/abs/2502.01224 |
| zhang2024tcs **(core)** | Zhang J, Swinnen L et al. | 2024 | Multimodal wearable EEG, EMG and accelerometry measurements improve the accuracy of tonic-clonic seizure detection (arXiv title ends "... in-hospital") | Physiological Measurement 45(6); arXiv:2403.13066 | Which wearable modalities detect tonic-clonic seizures (TCS) best? | Sensor Dot bte-EEG, EMG, ACC; unimodal and fused detectors | SeizeIT2: 27 participants, 44 TCS | EEG alone: sensitivity 100.0%, 10.3 FP/24 h. EEG + EMG + ACC fusion: sensitivity 90.9%, 0.1 FP/24 h, precision 75.5%, F1 82.5% (abstract) | Covers TCS only, a small part of SeizeIT2's focal-seizure majority. The study shows that fusion mostly cuts false positives. | https://pubmed.ncbi.nlm.nih.gov/38772401 ; https://arxiv.org/pdf/2403.13066 ; https://aminer.org/pub/65fb947913fb2c6cf6828fe0/multimodal-wearable-eeg-emg-and-accelerometry-measurements-improve-the-accuracy-of-tonic |
| swinnen2026seizeit2 **(core)** | Swinnen L et al. | 2026 | A multicenter, video-EEG-based validation of a multimodal wearable device for focal seizure detection in adults: The SeizeIT2 study | Epilepsia Open | Clinical validation of the Sensor Dot for focal seizures | Sensor Dot (bte-EEG + ECG); offline algorithm, then blinded expert review, compared against video-EEG | 192 adults, 616 focal seizures, about 5 days each | Algorithm alone: sensitivity 0.73, precision 0.004, F1 0.01. After human review: precision 0.83, sensitivity 0.31, F1 0.45. Seizures with a clear ictal bte-EEG pattern plus tachycardia: sensitivity 0.74 (abstract) | The best evidence that automated focal detection on this device is limited by false alarms. A detector that is precise without a human reviewer is still missing. | https://ora.ox.ac.uk/objects/uuid:50cfdcb4-4513-49eb-814b-36bb749c4721 ; https://www.ndcn.ox.ac.uk/team/arjune-sen/publication_modal/2405956 |
| reintjes2025ecg | Reintjes C et al. | 2025 | ECG-Based Detection of Epileptic Seizures in Real-World Wearable Settings: Insights from the SeizeIT2 Dataset | Sensors 25(24):7687 | Benchmark ECG-only detection on SeizeIT2 | Unsupervised time-series anomaly detection: Matrix Profile, MADRID, TimeVQVAE-AD | SeizeIT2: 11,640 h, 886 seizures | TimeVQVAE-AD had the highest sensitivity and MADRID the lowest FAR. ECG anomaly detection can reach clinically meaningful sensitivity, with a sensitivity/false-alarm trade-off (snippet). Numbers: - | ECG only, with no fusion with bte-EEG or EMG. Its reported first ECG benchmark on SeizeIT2 is a direct comparison point for our ECG branch. | https://www.ncbi.nlm.nih.gov/pmc/articles/PMC12736484/ ; https://www.mdpi.com/1424-8220/25/24/7687 |
| su2026cmepinet | Su T, Zhu H, Chen S, Wang H | 2026 | CMEpiNet: Complex-Valued Multimodal Epilepsy Detection Network Model | Sensors (DOI 10.3390/s26134186) | Use cross-modal phase and coupling features | Complex-valued convolutions (phase synchronisation, cross-frequency coupling) over EEG, ECG, EMG; two-level semantic alignment fusion; spatial-attention 3D-CNN classifier | SeizeIT2 | Improves sensitivity, lowers FAR and stays stable under perturbations (abstract; no numbers in the indexed abstract). Numbers: - | A complex-valued 3D-CNN, and the abstract reports no hardware or model-size budget. Its patient-independent protocol could not be checked. | https://www.citedrive.com/en/discovery/cmepinet-complex-valued-multimodal-epilepsy-detection-network-model/ |

### A4. Multimodal fusion and robustness to missing modalities

| Ref key | Authors (first author et al.) | Year | Title | Venue | Problem | Method / device | Data | Key result (source) | Limitation / gap relevant to our project | Verified at (URL) |
|---|---|---|---|---|---|---|---|---|---|---|
| ingolfsson2024brainfusenet **(core)** | Ingolfsson TM et al. | 2024 | BrainFuseNet: Enhancing Wearable Seizure Detection Through EEG-PPG-Accelerometer Sensor Fusion and Efficient Edge Deployment | IEEE Trans. Biomedical Circuits and Systems 18(4):720–733 | A lightweight fusion detector for low-channel wearables | Small network fusing 4-channel EEG with PPG and ACC; Sensitivity-Specificity Weighted Cross-Entropy loss; deployed on the GAP9 parallel ultra-low-power (PULP) microcontroller | CHB-MIT; PEDESITE | CHB-MIT: 93.5% of seizure events detected (EEG, 4 channels). PEDESITE, sample-based: EEG 60.66% at 1.18 FP/h; EEG + PPG 61.22% at 1.0 FP/h; EEG + PPG + ACC 64.28% at 0.21 FP/h (abstract) | The closest prior work on edge deployment, but it uses multiply-accumulate (MAC) inference on a microcontroller, not LUT-only or multiplier-free logic. It does not use SeizeIT2 or bte-EEG + ECG + EMG. | https://dblp.uni-trier.de/rec/journals/tbcas/IngolfssonWCBBDRBBC24.html ; https://api.openalex.org/works/doi:10.1109%2FTBCAS.2024.3395534 ; https://iris.unimore.it/handle/11380/1355847 |
| zhang2024cyclic **(core)** | Zhang J, Swinnen L, Chatzichristos C, Van Paesschen W, De Vos M | 2024 | Learning Robust Representations of Tonic-Clonic Seizures With Cyclic Transformer | IEEE Journal of Biomedical and Health Informatics 28(6):3721–3731 | Keep working when a sensor is missing or fails | Cyclic (cross-modal translation) transformer trained on paired EEG + EMG, tested on EEG only | Wearable TCS data (SeizeIT2 group) | Competitive with multimodal systems while using only EEG at test time (abstract; no numbers in the indexed abstract). Numbers: - | The only verified seizure work here on missing modalities. It is a transformer (heavy for the edge) and covers TCS only. | https://www.pubmed.gov/38457319/ ; https://sotaverified.org/papers/learning-robust-representations-of-tonic ; https://bvbvf1.bib-bvb.de/vufind/PrimoRecord/cdi_kuleuven_dspace_20_500_12942_745175 |

Notes on the table:
- SeizeIT1 is the earlier 42-patient bte-EEG (+ECG) dataset from the same consortium (KU Leuven / UZ Leuven). It
  appears here through bhagubai2023ecg and bhagubai2024challenge, which both describe it as 42 patients with focal
  epilepsy. Search did not turn up a separate SeizeIT1 dataset paper, so none is cited.
- SeizeIT2 seizure count: the journal abstract says 883 and the arXiv preprint (and Reintjes 2025) say 886. Cite the
  journal figure, or state which release was used.
- One index also lists beniczky2021guideline as co-published in Clinical Neurophysiology 132(5). It was not verified
  further, so only the Epilepsia version is cited.
- Considered but left out because no figure could be verified: Jeppesen et al., Epilepsia 2019 (HRV-based detection
  with a wearable ECG patch, doi 10.1111/epi.16343 per search). Only press-coverage numbers were available.
  Regalia et al., Epilepsy Research 153:79–82, 2019 (review of the Empatica E4/Embrace wristbands,
  doi 10.1016/j.eplepsyres.2019.02.007) was verified. It is not in the table because onorati2017empatica already
  covers the EDA+ACC wristband line, but it can be added.

## (b) BibTeX

```bibtex
@article{gbd2019epilepsy,
  author  = {{GBD 2016 Epilepsy Collaborators}},
  title   = {Global, regional, and national burden of epilepsy, 1990--2016: a systematic analysis for the Global Burden of Disease Study 2016},
  journal = {The Lancet Neurology},
  year    = {2019},
  volume  = {18},
  number  = {4},
  pages   = {357--375},
  doi     = {10.1016/S1474-4422(18)30454-X}
}

@article{fisher2017ilae,
  author  = {Fisher, R. S. and Cross, J. H. and French, J. A. and Higurashi, N. and Hirsch, E. and Jansen, F. E. and Lagae, L. and Mosh{\'e}, S. L. and Peltola, J. and Roulet Perez, E. and Scheffer, I. E. and Zuberi, S. M.},
  title   = {Operational classification of seizure types by the {International League Against Epilepsy}: Position Paper of the {ILAE} Commission for Classification and Terminology},
  journal = {Epilepsia},
  year    = {2017},
  volume  = {58},
  number  = {4},
  pages   = {522--530},
  doi     = {10.1111/epi.13670}
}

@article{elger2018underreporting,
  author  = {Elger, C. E. and Hoppe, C.},
  title   = {Diagnostic challenges in epilepsy: seizure under-reporting and seizure detection},
  journal = {The Lancet Neurology},
  year    = {2018},
  volume  = {17},
  number  = {3},
  pages   = {279--288},
  doi     = {10.1016/S1474-4422(18)30038-3}
}

@article{ryvlin2013mortemus,
  author  = {Ryvlin, Philippe and Nashef, Lina and Lhatoo, Samden D. and others},
  title   = {Incidence and mechanisms of cardiorespiratory arrests in epilepsy monitoring units ({MORTEMUS}): a retrospective study},
  journal = {The Lancet Neurology},
  year    = {2013},
  volume  = {12},
  number  = {10},
  pages   = {966--977},
  doi     = {10.1016/S1474-4422(13)70214-X}
}

@article{beniczky2021guideline,
  author  = {Beniczky, S. and Wiebe, S. and Jeppesen, J. and Tatum, W. O. and Br{\'a}zdil, M. and Wang, Y. and Herman, S. T. and Ryvlin, P.},
  title   = {Automated seizure detection using wearable devices: A clinical practice guideline of the {International League Against Epilepsy} and the {International Federation of Clinical Neurophysiology}},
  journal = {Epilepsia},
  year    = {2021},
  volume  = {62},
  number  = {3},
  pages   = {632--646},
  doi     = {10.1111/epi.16818}
}

@article{leijten2018review,
  author  = {Leijten, Frans S. S. and {Dutch TeleEpilepsy Consortium}},
  title   = {Multimodal seizure detection: A review},
  journal = {Epilepsia},
  year    = {2018},
  volume  = {59},
  number  = {S1},
  pages   = {42--47},
  doi     = {10.1111/epi.14047}
}

@article{beniczky2018emg,
  author  = {Beniczky, S. and Conradsen, I. and Henning, O. and Fabricius, M. and Wolf, P.},
  title   = {Automated real-time detection of tonic-clonic seizures using a wearable {EMG} device},
  journal = {Neurology},
  year    = {2018},
  volume  = {90},
  number  = {5},
  pages   = {e428--e434},
  doi     = {10.1212/WNL.0000000000004893}
}

@article{onorati2017empatica,
  author  = {Onorati, Francesco and Regalia, Giulia and Caborni, Chiara and Migliorini, Matteo and Bender, Daniel and Poh, Ming-Zher and Frazier, Cherise and Kovitch Thropp, Eliana and Mynatt, Elizabeth D. and Bidwell, Jonathan and Mai, Roberto and LaFrance, Jr., W. Curt and Blum, Andrew S. and Friedman, Daniel and Loddenkemper, Tobias and Mohammadpour-Touserkani, Fatemeh and Reinsberger, Claus and Tognetti, Simone and Picard, Rosalind W.},
  title   = {Multicenter clinical assessment of improved wearable multimodal convulsive seizure detectors},
  journal = {Epilepsia},
  year    = {2017},
  volume  = {58},
  number  = {11},
  pages   = {1870--1879},
  doi     = {10.1111/epi.13899}
}

@article{naganur2022meta,
  author  = {Naganur, V. and Sivathamboo, S. and Chen, Z. and Kusmakar, S. and Antonic-Baker, A. and O'Brien, T. J. and Kwan, P.},
  title   = {Automated seizure detection with noninvasive wearable devices: A systematic review and meta-analysis},
  journal = {Epilepsia},
  year    = {2022},
  volume  = {63},
  pages   = {1930--1941},
  doi     = {10.1111/epi.17297}
}

@article{vandecasteele2020bte,
  author  = {Vandecasteele, K. and De Cooman, T. and Dan, J. and Cleeren, E. and Van Huffel, S. and Hunyadi, B. and Van Paesschen, W.},
  title   = {Visual seizure annotation and automated seizure detection using behind-the-ear electroencephalographic channels},
  journal = {Epilepsia},
  year    = {2020},
  volume  = {61},
  number  = {4},
  pages   = {766--775},
  doi     = {10.1111/epi.16470}
}

@article{vandecasteele2021ecg,
  author  = {Vandecasteele, Kaat and De Cooman, Thomas and Chatzichristos, Christos and Cleeren, Evy and Swinnen, Lauren and Macea Ortiz, Jaiver and Van Huffel, Sabine and D{\"u}mpelmann, Matthias and Schulze-Bonhage, Andreas and De Vos, Maarten and Van Paesschen, Wim and Hunyadi, Borb{\'a}la},
  title   = {The power of {ECG} in multimodal patient-specific seizure monitoring},
  journal = {Epilepsia},
  year    = {2021},
  volume  = {62},
  number  = {10},
  pages   = {2333--2343},
  doi     = {10.1111/epi.16990}
}

@article{bhagubai2023ecg,
  author  = {Bhagubai, Miguel and Vandecasteele, Kaat and Swinnen, Lauren and Macea, Jaiver and Chatzichristos, Christos and De Vos, Maarten and Van Paesschen, Wim},
  title   = {The Power of {ECG} in Semi-Automated Seizure Detection in Addition to Two-Channel behind-the-Ear {EEG}},
  journal = {Bioengineering},
  year    = {2023},
  volume  = {10},
  number  = {4},
  pages   = {491},
  doi     = {10.3390/bioengineering10040491}
}

@article{bhagubai2024challenge,
  author  = {Bhagubai, Miguel and Swinnen, Lauren and Cleeren, Evy and Van Paesschen, Wim and De Vos, Maarten and Chatzichristos, Christos},
  title   = {Towards Automated Seizure Detection With Wearable {EEG} -- Grand Challenge},
  journal = {IEEE Open Journal of Signal Processing},
  year    = {2024},
  volume  = {5},
  pages   = {717--724},
  doi     = {10.1109/OJSP.2024.3378604}
}

@article{bhagubai2025seizeit2,
  author  = {Bhagubai, Miguel and Chatzichristos, Christos and Swinnen, Lauren and Macea, Jaiver and Zhang, Jingwei and Lagae, Lieven and Jansen, Katrien and Schulze-Bonhage, Andreas and Sales, Francisco and Mahler, Benno and Weber, Yvonne and Van Paesschen, Wim and De Vos, Maarten},
  title   = {{SeizeIT2}: Wearable Dataset Of Patients With Focal Epilepsy},
  journal = {Scientific Data},
  year    = {2025},
  doi     = {10.1038/s41597-025-05580-x},
  note    = {Preprint: arXiv:2502.01224. Dataset: OpenNeuro ds005873, doi 10.18112/openneuro.ds005873.v1.0.1 (as listed in a citation found by search). Volume and article number not verified here.}
}

@article{zhang2024tcs,
  author  = {Zhang, Jingwei and Swinnen, Lauren and Chatzichristos, Christos and Broux, Victoria and Proost, Renee and Jansen, Katrien and Mahler, Benno and Zabler, Nicolas and Epitashvilli, Nino and D{\"u}mpelmann, Matthias and Schulze-Bonhage, Andreas and Schriewer, Elisabeth and Ermis, Ummahan and Wolking, Stefan and Linke, Florian and Weber, Yvonne and Symmonds, Mkael and Sen, Arjune and Biondi, Andrea and Richardson, Mark P. and Sulaiman I, Abuhaiba and Silva, Ana Isabel and Sales, Francisco and V{\'e}rtes, Gergely and Van Paesschen, Wim and De Vos, Maarten},
  title   = {Multimodal wearable {EEG}, {EMG} and accelerometry measurements improve the accuracy of tonic-clonic seizure detection},
  journal = {Physiological Measurement},
  year    = {2024},
  volume  = {45},
  number  = {6},
  doi     = {10.1088/1361-6579/ad4e94},
  eprint  = {2403.13066},
  archivePrefix = {arXiv},
  note    = {Author names as given in the arXiv/PubMed records; article number not verified here.}
}

@article{swinnen2026seizeit2,
  author  = {Swinnen, Lauren and others},
  title   = {A multicenter, video-{EEG}-based validation of a multimodal wearable device for focal seizure detection in adults: The {SeizeIT2} study},
  journal = {Epilepsia Open},
  year    = {2026},
  doi     = {10.1002/epi4.70260},
  note    = {Full author list, volume and pages not verified here; published online April 2026 per the search record.}
}

@article{reintjes2025ecg,
  author  = {Reintjes, Conrad and Hagenbeck, Janosch Fabio and Ballo, Mohamed and Rahlmeier, Tim and Wolf, Simon Maximilian and Schoder, Detlef},
  title   = {{ECG}-Based Detection of Epileptic Seizures in Real-World Wearable Settings: Insights from the {SeizeIT2} Dataset},
  journal = {Sensors},
  year    = {2025},
  volume  = {25},
  number  = {24},
  pages   = {7687},
  doi     = {10.3390/s25247687}
}

@article{su2026cmepinet,
  author  = {Su, Tianyi and Zhu, Haiyan and Chen, Shuai and Wang, Haifeng},
  title   = {{CMEpiNet}: Complex-Valued Multimodal Epilepsy Detection Network Model},
  journal = {Sensors},
  year    = {2026},
  doi     = {10.3390/s26134186},
  note    = {Title as given by the CiteDrive record; volume/issue/article number not verified here.}
}

@article{ingolfsson2024brainfusenet,
  author  = {Ingolfsson, Thorir Mar and Wang, Xiaying and Chakraborty, Upasana and Benatti, Simone and Bernini, Adriano and Ducouret, Pauline and Ryvlin, Philippe and Beniczky, S{\'a}ndor and Benini, Luca and Cossettini, Andrea},
  title   = {{BrainFuseNet}: Enhancing Wearable Seizure Detection Through {EEG-PPG}-Accelerometer Sensor Fusion and Efficient Edge Deployment},
  journal = {IEEE Transactions on Biomedical Circuits and Systems},
  year    = {2024},
  volume  = {18},
  number  = {4},
  pages   = {720--733},
  doi     = {10.1109/TBCAS.2024.3395534}
}

@article{zhang2024cyclic,
  author  = {Zhang, Jingwei and Swinnen, Lauren and Chatzichristos, Christos and Van Paesschen, Wim and De Vos, Maarten},
  title   = {Learning Robust Representations of Tonic-Clonic Seizures With Cyclic Transformer},
  journal = {IEEE Journal of Biomedical and Health Informatics},
  year    = {2024},
  volume  = {28},
  number  = {6},
  pages   = {3721--3731},
  doi     = {10.1109/JBHI.2024.3375123}
}
```

Verified but not in the table (optional extra):

```bibtex
@article{regalia2019empatica,
  author  = {Regalia, Giulia and Onorati, Francesco and Lai, Matteo and Caborni, Chiara and Picard, Rosalind W.},
  title   = {Multimodal wrist-worn devices for seizure detection and advancing research: Focus on the {Empatica} wristbands},
  journal = {Epilepsy Research},
  year    = {2019},
  volume  = {153},
  pages   = {79--82},
  doi     = {10.1016/j.eplepsyres.2019.02.007}
}
```

(Regalia 2019 author list: the search confirmed the surnames Regalia, Onorati, Lai, Caborni and Picard as given in the
query, on the MIT DSpace / PubMed 30846346 records. Check the first names against PubMed before use.)

## (c) Research gaps that motivate SeizeLUT

Clinical evidence supports wearable detection only for tonic-clonic seizures. The ILAE–IFCN guideline does not
recommend current devices for other seizure types (beniczky2021guideline). The meta-analysis found focal-seizure
sensitivity ranging from 31% to 93% and a pooled false-alarm rate of 2.1/24 h (naganur2022meta). The largest
multicentre validation of the SeizeIT2 device reached 0.73 sensitivity at a precision of only 0.004 without human
review (swinnen2026seizeit2), so false alarms are the open problem for focal epilepsy. Multimodal fusion is the most
consistent lever against them:
- adding ECG to bte-EEG gave +8–11% sensitivity at a fixed false-alarm rate (vandecasteele2021ecg);
- ECG cut reviewer false detections from 6.5 to 2.4 per day (bhagubai2023ecg);
- adding EMG+ACC to EEG cut tonic-clonic false positives from 10.3 to 0.1 per 24 h (zhang2024tcs).

These fusion results, however, are patient-specific, semi-automated or limited to tonic-clonic seizures. The newest
SeizeIT2 models are a complex-valued 3D-CNN (su2026cmepinet) and unsupervised ECG-only anomaly detectors
(reintjes2025ecg), and their abstracts report no compute or hardware budget. Of the works found, the only fusion
detector with verified edge deployment still runs multiply-accumulate inference on a microcontroller
(ingolfsson2024brainfusenet). The only one that handles a missing sensor uses a transformer (zhang2024cyclic). The
untested combination is therefore a tiny, multiplier-free (LUT-native) bte-EEG+ECG+EMG+motion detector that
tolerates a missing modality and is scored on held-out, unseen patients with the event-level sensitivity and
false-alarms-per-24 h metrics the clinical literature uses.

## Access notes

- WebFetch could not reach www.nature.com, api.crossref.org, api.semanticscholar.org or dblp.org from this session (DNS
  blocked by the session's network policy), so no full text was read. All data come from search results that quote the
  publisher, PubMed, PMC, dblp, OpenAlex, DOAJ or institutional-repository records listed above.
- Still unverified: the SeizeIT2 (Scientific Data) benchmark numbers, volume and article number; the CMEpiNet and
  Reintjes numeric results; the full Swinnen 2026 author list; the Naganur 2022 issue number. Check these against the
  publisher pages before the final submission.
