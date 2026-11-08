# Literature section B: seizure detection algorithms and evaluation methodology

How this was checked: every paper below came up in a web search whose result matched its title, authors, venue and
year. Direct page fetches were blocked in this environment (arxiv.org, dblp.org, infoscience.epfl.ch,
api.semanticscholar.org all failed to resolve), so each "Verified at" URL is a page that the search engine returned
together with its metadata and abstract or text snippet. I did not open the full PDFs. Every number in "Key result"
comes from an abstract or text snippet returned by the search, and its source is named in brackets. "-" means I found
no number I could check. Before submission, open each DOI once to confirm volume, issue and page numbers, which are
left out of the BibTeX where I could not verify them.

There are 16 core papers (the brief asked for 10-14, but it also named four sub-areas) and 3 supplementary ones. To
stay at 14, move `wu2025seizuretransformer` (preprint) and `lawhern2018eegnet` (built for BCI, not seizures) to the
supplementary list.

## (a) Table

### Core papers

| Ref key | Authors | Year | Title | Venue | Problem | Method | Data | Key result (source) | Limitation / gap relevant to our project | Verified at (URL) |
|---|---|---|---|---|---|---|---|---|---|---|
| shoeb2010icml | Shoeb & Guttag | 2010 | Application of Machine Learning To Epileptic Seizure Detection | ICML 2010, pp. 975-982 | Seizure-onset detection from scalp EEG | Patient-specific SVM classifier on EEG features | CHB-MIT scalp EEG: 916 h, 24 patients | Caught 96% of 173 test seizures; median latency 3 s; median 2 false detections per 24 h (abstract) | Patient-specific: needs at least 2 seizures of the same patient to train. Pediatric, multichannel scalp EEG, not wearable. Says nothing about inter-patient performance, which our split tests | https://archive.physionet.org/pn6/chbmit/shoeb-icml-2010.pdf ; https://dblp.org/rec/conf/icml/ShoebG10.html |
| shah2018tusz | Shah et al. | 2018 | The Temple University Hospital Seizure Detection Corpus | Frontiers in Neuroinformatics (Data Report) | Need for a large, clinically realistic seizure corpus | Corpus built by keyword search of EEG reports, commercial (Persyst) and experimental deep-learning detection, then manual annotation | TUSZ v1.2.0 (Dec 2017) | 315 subjects, 822 sessions, 280 of them with seizures (text snippet) | Clinical scalp EEG with full montages, not behind-the-ear wearables. Annotation by students carries label noise. Most deep-learning detectors are tuned to it | https://www.frontiersin.org/articles/10.3389/fninf.2018.00083 ; https://www.ncbi.nlm.nih.gov/pmc/articles/PMC6246677/ |
| alhussaini2023seizft | Al-Hussaini & Mitchell | 2023 | SeizFt: Interpretable Machine Learning for Seizure Detection Using Wearables | Bioengineering (MDPI) 10(8):918 | Interpretable seizure detection on wearable behind-the-ear EEG | Hand-crafted features, Fourier-transform-surrogate augmentation, class balancing, CatBoost (gradient-boosted tree ensemble), 1-s decisions | Trained on SeizeIT1, validated and tested on SeizeIT2 (ICASSP 2023 challenge data) | 1st place in the ICASSP 2023 Seizure Detection Grand Challenge; total score 40.15, about 30% above the next best (abstract) | EEG only, no ECG, EMG or motion. Uses the challenge score, not SzCORE or FA/24 h. Large tree ensemble with no hardware cost analysis. Gives the strongest tree-based baseline on our dataset | https://mdpi.com/2306-5354/10/8/918 ; https://www.pubmed.gov/37627803/ |
| huang2023lightweight | Huang, Abtahi & Aminifar | 2023 | Lightweight Machine Learning for Seizure Detection on Wearable Devices | ICASSP 2023 (Seizure Detection Challenge paper) | Low-cost detection for wearables; data-centric ChronoNet task | Random forest on EEG band-power features; also ChronoNet trained on SeizeIT1 (challenge Task 2) | SeizeIT1 to SeizeIT2 (Byteflies SensorDot) | Random forest: sensitivity 73.6%, specificity 96.7%. ChronoNet trained on SeizeIT1: sensitivity 15.2%, specificity 99.8% on validation data (abstract / text snippet) | Reports specificity, not FA/24 h or event F1. EEG only. Shows that the off-the-shelf ChronoNet transfers poorly to behind-the-ear data, which is relevant to our M2 reproduction | https://portal.research.lu.se/en/publications/lightweight-machine-learning-for-seizure-detection-on-wearable-de/ ; https://lup.lub.lu.se/search/files/141522442/2023051653.pdf |
| roy2019chrononet | Roy, Kiral-Kornek & Harrer | 2019 (arXiv 2018) | ChronoNet: A Deep Recurrent Neural Network for Abnormal EEG Identification | AIME 2019, LNCS 11526 (Springer); arXiv:1802.00308 | Normal vs abnormal EEG classification | Stacked multi-scale 1-D convolutions (filter lengths grow exponentially) followed by densely connected GRU layers, on raw EEG | TUH Abnormal EEG Corpus | 1.17% better than the previous best, a new benchmark on TUH Abnormal (abstract) | Built for abnormal-EEG triage, not seizure detection. The recurrent GRU stack is costly and hard to map onto LUTs. It was the fixed model of ICASSP 2023 Task 2 and transfers poorly to SeizeIT2 (see huang2023lightweight) | https://rd.springer.com/chapter/10.1007/978-3-030-21642-9_8 ; https://arxiv.org/pdf/1802.00308 |
| lawhern2018eegnet | Lawhern et al. | 2018 | EEGNet: a compact convolutional neural network for EEG-based brain-computer interfaces | Journal of Neural Engineering 15(5):056013 | One compact CNN for several EEG paradigms | Depthwise and separable convolutions | Four BCI paradigms (P300, ERN, MRCP, SMR) | Generalises across paradigms, with performance comparable to traditional approaches and up to two orders of magnitude fewer parameters (abstract) | Not a seizure paper, though often used as a compact seizure baseline (e.g. EEGNet-8,2 in EEGWaveNet). Still multiply-accumulate (MAC) arithmetic. "Compact" is measured in parameters, not in FPGA LUTs or energy | https://pubmed.ncbi.nlm.nih.gov/29932424/ ; https://iopscience.iop.org/article/10.1088/1741-2552/aace8c/meta |
| thuwajit2022eegwavenet | Thuwajit et al. | 2022 (online 2021) | EEGWaveNet: Multiscale CNN-Based Spatiotemporal Feature Extraction for EEG Seizure Detection | IEEE Trans. Industrial Informatics 18(8):5547-5557 | End-to-end seizure detection, subject-dependent and subject-independent | Multiscale CNN: trainable depthwise convolutions split each channel into several resolutions, then spatio-temporal features | CHB-MIT, TUSZ (BONN also listed in some abstract versions) | Comparable to baselines when subject-dependent, better when subject-independent; time complexity similar to EEGNet-8,2; fine-tuning on 1 h of a new patient raises sensitivity and F1 (abstract) | Multichannel scalp EEG. Floating-point CNN. Patient adaptation needs labelled data from the new patient | https://api.openalex.org/works/doi:10.1109%2FTII.2021.3133307 ; https://www.aminer.cn/pub/62286c3b5aee126c0fa63378 |
| tang2022gnnssl | Tang et al. | 2022 | Self-Supervised Graph Neural Networks for Improved Electroencephalographic Seizure Analysis | ICLR 2022 | Seizure detection and classification that uses spatial electrode structure | Graph neural network on two electrode graphs (electrode geometry; dynamic connectivity), plus self-supervised pre-training on unlabelled EEG | TUSZ (5,499 EEGs) | Detection AUROC 0.875; seizure-type weighted F1 0.749 (abstract) | Needs a full 19-channel montage to build the graph, which does not exist with 2-channel behind-the-ear EEG. Heavy model. Window-level AUROC rather than event-level metrics | https://iclr.cc/virtual/2022/poster/7027 ; https://dblp1.uni-trier.de/rec/conf/iclr/TangDSZHDRL22.html |
| wu2025seizuretransformer | Wu, Zhao & Yener | 2025 | SeizureTransformer: Scaling U-Net with Transformer for Simultaneous Time-Step Level Seizure Detection from Long EEG Recordings (v2 title: Large EEG-U-Transformer for Time-Step Level Detection Without Pre-Training) | arXiv:2504.00336 (preprint) | Per-time-step seizure detection on long recordings | U-Net encoder-decoder with residual CNN and transformer encoder | TUSZ v2.0.3 train (910 h, 579 subjects) + Siena (128 h, 14 subjects) | Says it ranked first in the 2025 seizure detection challenge (abstract) | Large model, not suited to edge hardware. Scalp montage. Preprint, not peer reviewed. I did not find its own challenge score | https://arxiv.org/abs/2504.00336v2 ; https://www.emergentmind.com/papers/2504.00336 |
| ziyabari2017metrics | Ziyabari et al. | 2017 | Objective evaluation metrics for automatic classification of EEG events | arXiv:1712.10107 (extended as a 2021 Springer chapter by Shah, Golmohammadi, Obeid & Picone) | Sensitivity and specificity can mislead for sequential event detection | Compares epoch-based and any-overlap (OVLP) scoring with ATWV and a new Time-Aligned Event Scoring (TAES) | TUH EEG / TUSZ seizure detection | - (proposes metrics; OVLP is permissive about how much events overlap, TAES gives partial credit by alignment (snippet)) | Different scoring methods give different numbers for the same system. Many papers report only epoch or sample metrics, so results cannot be compared. Our scorer has to state its scoring rule explicitly | https://arxiv.org/pdf/1712.10107 ; https://www.isip.piconepress.com/publications/book_sections/2021/springer/metrics/_ARCHIVES/paper_v07.pdf |
| dan2024szcore | Dan et al. | 2024 (online Sep 2024; print issue 66(S3):14-24, 2025) | SzCORE: Seizure Community Open-Source Research Evaluation framework for the validation of electroencephalography-based automated seizure detection algorithms | Epilepsia | Datasets, metrics and cross-validation vary so much that results cannot be compared | Standard framework: EEG 10-20 benchmark built from public datasets in one format, file and annotation formats, cross-validation advice, event-based metrics (any-overlap; sensitivity, precision, F1, false positives per day), open-source scoring library | Public scalp datasets in 10-20 format | - (framework paper; event scoring counts any overlap as a true positive (preprint snippet)) | Built for scalp 10-20 EEG; wearable multimodal recordings are not part of its benchmark. Event-scoring settings (pre-onset tolerance, merging) are conventions that change results | https://serval.unil.ch/notice/serval:BIB_CEC107F4AB63 ; https://pesquisa.bvsalud.org/bvsms/resource/pt/mdl-39292446 ; https://arxiv.org/pdf/2402.13005 |
| bhagubai2024challenge | Bhagubai et al. | 2024 | Towards Automated Seizure Detection With Wearable EEG - Grand Challenge | IEEE Open Journal of Signal Processing 5:717-724 | Report on the ICASSP 2023 wearable seizure detection challenge | Task 1: open-method detection. Task 2: data-centric optimisation of a fixed ChronoNet | 42 patients with focal epilepsy, continuous behind-the-ear EEG (SeizeIT), separate held-out evaluation set | Five best methods described; the winner was a feature-based decision-tree ensemble with Fourier-transform-surrogate augmentation (abstract) | EEG-only challenge, so SeizeIT2's ECG, EMG and motion were not used. Challenge-specific score, not comparable with SzCORE. Says training data are scarce | https://doaj.org/article/f808625d83b948468b601ad4592d927c ; https://ieeexplore.ieee.org/document/10474132 ; https://signalprocessingsociety.org/publications-resources/data-challenges/seizure-detection-challenge-icassp-2023 |
| dan2025szcorechallenge | Dan, Shahbazinia, Kechris & Atienza | 2025 | SzCORE as a benchmark: report from the seizure detection challenge at the 2025 AI in Epilepsy and Neurological Disorders Conference (later retitled: Quantifying the Generalization Gap in Seizure Detection: A Large-Scale Empirical Benchmark via the SzCORE Challenge) | arXiv:2505.18191 (preprint) | Blind, independent test of seizure detectors on unseen long-term EEG | Challenge: participants submit algorithms, scored with SzCORE on hidden data; ranked by event-based F1 | Private EMU dataset: 65 subjects, 4,360 h continuous EEG | Best F1 43% (sensitivity 37%, precision 45%); wide spread of results and a gap between reported and blind-test performance (abstract) | Shows that published inter-patient numbers do not hold up on blind data. Scalp EEG only. Private test set | https://arxiv.org/abs/2505.18191 ; https://www.emergentmind.com/papers/2505.18191 |
| brookshire2024leakage | Brookshire et al. | 2024 | Data leakage in deep learning studies of translational EEG | Frontiers in Neuroscience 18:1373515 | Segment-level train/test splits inflate accuracy | Reproduces two published CNNs with and without subject-wise splits, then surveys the literature | Translational EEG classification datasets | Most surveyed translational DNN-EEG studies leak subject data between train and test and may greatly overestimate performance on new subjects (abstract) | Not about seizures, but it is the clearest argument for strict patient-wise splits like ours (test patients sub-097..125 held out) | https://www.frontiersin.org/articles/10.3389/fnins.2024.1373515 ; https://www.ncbi.nlm.nih.gov/pmc/articles/PMC11099244/ |
| shama2026bundl | Shama & Venkataraman | 2024 (arXiv) / 2026 (PLOS ONE) | BUNDL: Bayesian Uncertainty-aware Deep Learning with Noisy training Labels for Seizure Detection in EEG (journal title: Bayesian uncertainty-aware deep learning with noisy labels: Tackling annotation ambiguity in EEG seizure detection) | arXiv:2410.19815; PLOS ONE 21(6), 2026 | Noisy, ambiguous seizure annotations (low inter-rater agreement) | KL-divergence loss modelling clean-to-noisy label transitions; no extra parameters; Monte Carlo dropout for uncertainty | Simulated EEG (7 noise types), TUH, CHB-MIT; Siena for cross-site testing | Makes three base models more robust under label noise and improves seizure-onset-zone localisation (abstract) | Scalp EEG only. Model-agnostic, but the dropout ensemble adds inference cost. Onset and offset noise in wearable annotations is not studied | https://arxiv.org/abs/2410.19815v2 ; https://ideas.repec.org/a/plo/pone00/0352191.html |
| zheng2023kdgnn | Zheng, Venkitaraman, Petravic & Frossard | 2023 | Knowledge Distillation with Graph Neural Networks for Epileptic Seizure Detection (arXiv title: Knowledge-Distilled Graph Neural Networks for Personalized Epileptic Seizure Detection) | ECML PKDD 2023, LNCS, pp. 547-563; arXiv:2304.06038 | Few-channel detectors for wearables | Teacher GNN trained on the full montage distilled into few-channel student GNNs; personalised channel selection with Gumbel-softmax | TUSZ | With as few as 2 channels, detection performance remains competitive (abstract) | Students are still floating-point GNNs. Channel selection is per patient. Scalp channels chosen after the fact, not real behind-the-ear electrodes | https://mlanthology.org/ecmlpkdd/2023/zheng2023ecmlpkdd-knowledge ; https://arxiv.org/pdf/2304.06038 |

### Supplementary papers (verified; use if space allows)

| Ref key | Authors | Year | Title | Venue | Problem | Method | Data | Key result (source) | Limitation / gap relevant to our project | Verified at (URL) |
|---|---|---|---|---|---|---|---|---|---|---|
| isaev2020mil | Isaev et al. | 2020 | Attention-Based Network for Weak Labels in Neonatal Seizure Detection | MLHC 2020, PMLR 126:479-507 | Only time periods are labelled, not channels (weak labels) | Attention-based multiple-instance learning (after Ilse et al. 2018) with channel attention | Neonatal EEG | - (attention compared with per-channel expert labels; a high AUC did not guarantee agreement with the expert (snippet)) | Neonatal scalp EEG. Shows how to learn from coarse event labels, as in SeizeIT2 annotations | https://proceedings.mlr.press/v126/isaev20a.html |
| saab2020weak | Saab, Dunnmon, Ré, Rubin & Lee-Messer | 2020 | Weak supervision as an efficient approach for automated seizure detection in electroencephalography | npj Digital Medicine 3 | Expert labels are expensive | CNNs trained on noisy clinical annotations (weak supervision) | Pediatric and adult clinical EEG | AUROC 0.93 (pediatric) and 0.94 (adult); F1 31% higher (18 points) than deployed clinical software for pediatric patients (abstract) | Scalp EEG, large CNN, AUROC rather than event metrics | https://doaj.org/article/ff53b21a684b46adb56f53e342154ca4 ; https://www.ncbi.nlm.nih.gov/pmc/articles/PMC7170880/ |
| yang2023biot | Yang, Westover & Sun | 2023 | BIOT: Biosignal Transformer for Cross-data Learning in the Wild | NeurIPS 2023 (arXiv:2305.10351) | Pre-training across biosignal datasets with mismatched channels and lengths | Splits each channel into segments, joins them into one "sentence", feeds a linear-attention transformer | EEG (incl. CHB-MIT), ECG, human-activity sensors | CHB-MIT: +3% balanced accuracy over baselines; pre-training adds up to +4% more (abstract) | Large transformer, not deployable on an FPGA as is. Window-level balanced accuracy only. Shows that EEG, ECG and motion can share one model | https://papers.neurips.cc/paper_files/paper/2023/file/f6b30f3e2dd9cb53bbf2024402d02295-Paper-Conference.pdf ; https://arxiv.org/pdf/2305.10351 |

## (b) BibTeX

```bibtex
@inproceedings{shoeb2010icml,
  author    = {Shoeb, Ali and Guttag, John},
  title     = {Application of Machine Learning To Epileptic Seizure Detection},
  booktitle = {Proceedings of the 27th International Conference on Machine Learning (ICML)},
  pages     = {975--982},
  year      = {2010},
  url       = {https://archive.physionet.org/pn6/chbmit/shoeb-icml-2010.pdf}
}

@article{shah2018tusz,
  author  = {Shah, Vinit and von Weltin, Eva and Lopez, Silvia and McHugh, James Riley and Veloso, Lillian and Golmohammadi, Meysam and Obeid, Iyad and Picone, Joseph},
  title   = {The {Temple University Hospital} Seizure Detection Corpus},
  journal = {Frontiers in Neuroinformatics},
  year    = {2018},
  doi     = {10.3389/fninf.2018.00083},
  note    = {arXiv:1801.08085}
}

@article{alhussaini2023seizft,
  author  = {Al-Hussaini, Irfan and Mitchell, Cassie S.},
  title   = {{SeizFt}: Interpretable Machine Learning for Seizure Detection Using Wearables},
  journal = {Bioengineering},
  volume  = {10},
  number  = {8},
  pages   = {918},
  year    = {2023},
  doi     = {10.3390/bioengineering10080918}
}

@inproceedings{huang2023lightweight,
  author    = {Huang, Baichuan and Abtahi, Azra and Aminifar, Amir},
  title     = {Lightweight Machine Learning for Seizure Detection on Wearable Devices},
  booktitle = {IEEE International Conference on Acoustics, Speech and Signal Processing (ICASSP)},
  year      = {2023},
  url       = {https://portal.research.lu.se/en/publications/lightweight-machine-learning-for-seizure-detection-on-wearable-de/},
  note      = {ICASSP 2023 Seizure Detection Challenge paper; DOI not verified}
}

@inproceedings{roy2019chrononet,
  author    = {Roy, Subhrajit and Kiral-Kornek, Isabell and Harrer, Stefan},
  title     = {{ChronoNet}: A Deep Recurrent Neural Network for Abnormal {EEG} Identification},
  booktitle = {Artificial Intelligence in Medicine (AIME 2019)},
  series    = {Lecture Notes in Computer Science},
  volume    = {11526},
  publisher = {Springer},
  year      = {2019},
  doi       = {10.1007/978-3-030-21642-9_8},
  eprint    = {1802.00308},
  archivePrefix = {arXiv}
}

@article{lawhern2018eegnet,
  author  = {Lawhern, Vernon J. and Solon, Amelia J. and Waytowich, Nicholas R. and Gordon, Stephen M. and Hung, Chou P. and Lance, Brent J.},
  title   = {{EEGNet}: a compact convolutional neural network for {EEG}-based brain--computer interfaces},
  journal = {Journal of Neural Engineering},
  volume  = {15},
  number  = {5},
  pages   = {056013},
  year    = {2018},
  doi     = {10.1088/1741-2552/aace8c},
  eprint  = {1611.08024},
  archivePrefix = {arXiv}
}

@article{thuwajit2022eegwavenet,
  author  = {Thuwajit, Punnawish and Rangpong, Phurin and Sawangjai, Phattarapong and Autthasan, Phairot and Chaisaen, Rattanaphon and Banluesombatkul, Nannapas and Boonchit, Puttaranun and Tatsaringkansakul, Nattasate and Sudhawiyangkul, T. and Wilaiprasitporn, Theerawit},
  title   = {{EEGWaveNet}: Multiscale {CNN}-Based Spatiotemporal Feature Extraction for {EEG} Seizure Detection},
  journal = {IEEE Transactions on Industrial Informatics},
  volume  = {18},
  number  = {8},
  pages   = {5547--5557},
  year    = {2022},
  doi     = {10.1109/TII.2021.3133307}
}

@inproceedings{tang2022gnnssl,
  author    = {Tang, Siyi and Dunnmon, Jared and Saab, Khaled Kamal and Zhang, Xuan and Huang, Qianying and Dubost, Florian and Rubin, Daniel and Lee-Messer, Christopher},
  title     = {Self-Supervised Graph Neural Networks for Improved Electroencephalographic Seizure Analysis},
  booktitle = {International Conference on Learning Representations (ICLR)},
  year      = {2022},
  url       = {https://openreview.net/forum?id=k9bx1EfHI_-},
  eprint    = {2104.08336},
  archivePrefix = {arXiv}
}

@misc{wu2025seizuretransformer,
  author  = {Wu, Kerui and Zhao, Ziyue and Yener, B{\"u}lent},
  title   = {{SeizureTransformer}: Scaling {U-Net} with Transformer for Simultaneous Time-Step Level Seizure Detection from Long {EEG} Recordings},
  year    = {2025},
  eprint  = {2504.00336},
  archivePrefix = {arXiv},
  note    = {v2 retitled ``Large EEG-U-Transformer for Time-Step Level Detection Without Pre-Training''}
}

@misc{ziyabari2017metrics,
  author  = {Ziyabari, Saeedeh and Shah, Vinit and Golmohammadi, Meysam and Obeid, Iyad and Picone, Joseph},
  title   = {Objective evaluation metrics for automatic classification of {EEG} events},
  year    = {2017},
  eprint  = {1712.10107},
  archivePrefix = {arXiv},
  note    = {Extended as a chapter by V. Shah, M. Golmohammadi, I. Obeid and J. Picone in Biomedical Signal Processing: Innovation and Applications (Springer, 2021); chapter DOI not verified}
}

@article{dan2024szcore,
  author  = {Dan, Jonathan and Pale, U. and Amirshahi, A. and Cappelletti, W. and Ingolfsson, Thorir Mar and Wang, Xiaying and Cossettini, Andrea and Bernini, Adriano and Benini, Luca and Beniczky, S{\'a}ndor and Atienza, David and Ryvlin, Philippe},
  title   = {{SzCORE}: Seizure Community Open-Source Research Evaluation framework for the validation of electroencephalography-based automated seizure detection algorithms},
  journal = {Epilepsia},
  year    = {2024},
  doi     = {10.1111/epi.18113},
  note    = {Published online September 2024; print issue 66(S3):14--24 (2025); arXiv:2402.13005}
}

@article{bhagubai2024challenge,
  author  = {Bhagubai, Miguel and Swinnen, Lauren and Cleeren, Evy and Van Paesschen, Wim and De Vos, Maarten and Chatzichristos, Christos},
  title   = {Towards Automated Seizure Detection With Wearable {EEG} -- Grand Challenge},
  journal = {IEEE Open Journal of Signal Processing},
  volume  = {5},
  pages   = {717--724},
  year    = {2024},
  doi     = {10.1109/OJSP.2024.3378604}
}

@misc{dan2025szcorechallenge,
  author  = {Dan, Jonathan and Shahbazinia, Amirhossein and Kechris, Christodoulos and Atienza, David},
  title   = {{SzCORE} as a benchmark: report from the seizure detection challenge at the 2025 {AI} in Epilepsy and Neurological Disorders Conference},
  year    = {2025},
  eprint  = {2505.18191},
  archivePrefix = {arXiv},
  note    = {Later retitled ``Quantifying the Generalization Gap in Seizure Detection: A Large-Scale Empirical Benchmark via the SzCORE Challenge''}
}

@article{brookshire2024leakage,
  author  = {Brookshire, Geoffrey and Kasper, Jake and Blauch, Nicholas M. and Wu, Yunan Charles and Glatt, Ryan and Merrill, David A. and Gerrol, Spencer and Yoder, Keith J. and Quirk, Colin and Lucero, Ch{\'e}},
  title   = {Data leakage in deep learning studies of translational {EEG}},
  journal = {Frontiers in Neuroscience},
  volume  = {18},
  pages   = {1373515},
  year    = {2024},
  doi     = {10.3389/fnins.2024.1373515}
}

@article{shama2026bundl,
  author  = {Shama, Deeksha M. and Venkataraman, Archana},
  title   = {Bayesian uncertainty-aware deep learning with noisy labels: Tackling annotation ambiguity in {EEG} seizure detection},
  journal = {PLOS ONE},
  volume  = {21},
  number  = {6},
  year    = {2026},
  doi     = {10.1371/journal.pone.0352191},
  note    = {Preprint: arXiv:2410.19815 (2024), first titled ``BUNDL: Bayesian Uncertainty-aware Deep Learning with Noisy training Labels for Seizure Detection in EEG''}
}

@inproceedings{zheng2023kdgnn,
  author    = {Zheng, Qinyue and Venkitaraman, Arun and Petravic, Simona and Frossard, Pascal},
  title     = {Knowledge Distillation with Graph Neural Networks for Epileptic Seizure Detection},
  booktitle = {Machine Learning and Knowledge Discovery in Databases (ECML PKDD 2023)},
  series    = {Lecture Notes in Computer Science},
  publisher = {Springer},
  pages     = {547--563},
  year      = {2023},
  doi       = {10.1007/978-3-031-43427-3_33},
  eprint    = {2304.06038},
  archivePrefix = {arXiv}
}

@inproceedings{isaev2020mil,
  author    = {Isaev, Dmitry Yu. and Tchapyjnikov, Dmitry and Cotten, C. Michael and Tanaka, David and Martinez, Natalia and Bertran, Martin and Sapiro, Guillermo and Carlson, David},
  title     = {Attention-Based Network for Weak Labels in Neonatal Seizure Detection},
  booktitle = {Proceedings of the 5th Machine Learning for Healthcare Conference},
  series    = {Proceedings of Machine Learning Research},
  volume    = {126},
  pages     = {479--507},
  year      = {2020},
  url       = {https://proceedings.mlr.press/v126/isaev20a.html}
}

@article{saab2020weak,
  author  = {Saab, Khaled and Dunnmon, Jared and R{\'e}, Christopher and Rubin, Daniel and Lee-Messer, Christopher},
  title   = {Weak supervision as an efficient approach for automated seizure detection in electroencephalography},
  journal = {npj Digital Medicine},
  volume  = {3},
  year    = {2020},
  doi     = {10.1038/s41746-020-0264-0}
}

@inproceedings{yang2023biot,
  author    = {Yang, Chaoqi and Westover, M. Brandon and Sun, Jimeng},
  title     = {{BIOT}: Biosignal Transformer for Cross-data Learning in the Wild},
  booktitle = {Advances in Neural Information Processing Systems (NeurIPS)},
  volume    = {36},
  year      = {2023},
  eprint    = {2305.10351},
  archivePrefix = {arXiv}
}
```

## (c) Research gaps that motivate SeizeLUT

Strong seizure detectors have mostly been built and scored on clinical scalp EEG (CHB-MIT, TUSZ), often patient-specific
(Shoeb & Guttag). Blind inter-patient tests are much weaker: the best entry in the 2025 SzCORE challenge reached an
event F1 of 43%, and ChronoNet trained on SeizeIT1 reached 15.2% sensitivity on SeizeIT2 validation patients. Results
also cannot be compared across papers, because they mix epoch- and event-based scoring, OVLP, TAES and any-overlap
rules, challenge-specific scores (ICASSP 2023), FA/h and FP/24 h. SzCORE standardises this only for scalp 10-20 EEG,
not for wearable multimodal recordings. Reproducibility suffers from subject leakage across train and test splits
(Brookshire et al.) and from private or one-off test sets, so strict patient-wise splits with a locked test set (as in
our project) are still uncommon. The best-performing models are large floating-point networks (graph networks,
U-Net transformers, foundation models). Work on compact models (EEGNet, distilled GNN students) still counts parameters
or channels, not hardware cost, and none of the papers in this theme targets a LUT-native or weightless model. Finally,
almost every detector, including all the ICASSP 2023 wearable entries, uses EEG alone, and label noise is studied
mainly on scalp EEG. That leaves open whether noisy, multimodal SeizeIT2 annotations (behind-the-ear EEG, ECG, EMG,
motion) can support a tiny, hardware-native detector that is scored with SzCORE-style event metrics.

## Notes on what was left out or not verified

- No Springer DOI was found for the 2021 "Objective Evaluation Metrics" chapter (Shah, Golmohammadi, Obeid, Picone).
  The search placed it in *Biomedical Signal Processing: Innovation and Applications* (Springer, 2021), and the
  authors host a PDF of it. Cite the arXiv version, or confirm the chapter DOI on SpringerLink first.
- I did not verify the exact ICASSP 2023 scoring formula or the per-team sensitivity and false-alarm numbers in the
  OJSP challenge paper, so the table does not report them.
- The 2025 challenge report gives inconsistent participation counts across its versions (19 vs 30 teams, 28
  algorithms), so they are left out. I also could not confirm that SeizureTransformer's own score equals the
  reported best F1 of 43%.
- Volume, issue and page numbers missing from the BibTeX (TUSZ, Saab, BIOT, Huang) were not confirmed and should be
  copied from the DOI pages.
