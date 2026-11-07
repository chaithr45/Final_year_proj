# Laptop runbook (RTX 3060 6 GB, Windows + WSL2 Ubuntu)

Everything that needs a GPU, in order. Each command is resumable or writes a new
`results/runs/<id>/` and never overwrites another run. Commit the `results/` changes
afterwards (never `data/`, `cache/` or `checkpoints/`).

## 0. Once

```bash
wsl --install -d Ubuntu-24.04
```

Inside Ubuntu: install Miniforge, then

```bash
git clone https://github.com/chaithr45/Final_year_proj.git && cd Final_year_proj && git checkout claude/optimistic-heisenberg-ph0bvj
```

```bash
conda env create -f environment.yml && conda activate seizelut
```

```bash
python -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"
```

Our DWN is pure PyTorch (`src/models/dwn.py`), so it runs on CUDA without compiling `torch-dwn`.
`torch-dwn` and `difflogic` are not in `environment.yml`: both need a CUDA toolkit to build, and our
DWN and LGN code does not need them.

## Launching long jobs

Use `scripts/laptop/start.sh feat|chrono|sweep`: each job runs in its own tmux session (it survives
closing the window's tab, not shutting WSL down: keep one Ubuntu window open), logs to `logs/<job>.log`,
and its window stays open at the end so errors can be read with `tmux attach -t <job>`.

Every job resumes: if it is interrupted (exit 143 in the log = stopped from outside, e.g. the window
was closed, Windows slept or restarted), run the same `start.sh` command again. The ChronoNet data step
keeps a per-recording progress file and training continues from the last finished epoch (`--resume auto`).
To keep a job alive overnight: leave one Ubuntu window open, laptop on the charger, and in Windows
power settings set sleep to Never and closing the lid to Do nothing (when plugged in).

## 1. Data (about 126 GB download, then 7 GB of features)

```bash
scripts/download_data.sh && python scripts/verify_data.py
```

```bash
python scripts/extract_features.py --workers 6
```

(The cloud session already built the same feature cache; extraction is deterministic, so the
laptop cache is identical. If you only want the GPU runs, the features are all you need: skip the
download and let `extract_features.py` stream from S3.)

## 2. M2: official ChronoNet reproduction (about 3-6 h)

```bash
python scripts/baselines/chrononet_data.py --config configs/baselines/chrononet_official.yaml --final-test
```

```bash
python scripts/baselines/chrononet_train.py --config configs/baselines/chrononet_official.yaml --device cuda
```

```bash
python scripts/baselines/chrononet_predict.py --run results/runs/<the new chrononet_official run> --final-test --device cuda
```

```bash
python scripts/baselines/evaluate_predictions.py --run results/runs/<same run> --final-test
```

Repeat with `configs/baselines/chrononet_clean.yaml` (no epoch selection on test patients).
`--final-test` is required because the published baseline is scored on the validation (= test)
patients; this is the M2 reproduction and is logged in `TEST_ACCESS.log`.

## 3. M4: DWN size sweep on the inner folds (about 8-12 h)

```bash
python scripts/make_dwn_sweep.py && scripts/run_queue.sh configs/m4/sweep/*.yaml
```

## 4. Raw-EEG CNN/TCN and GRU references

Not yet implemented in this branch; they will be added as configs that run with `--device cuda`.
