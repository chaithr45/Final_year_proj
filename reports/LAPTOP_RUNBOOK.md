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
Memory: WSL gets half the laptop's RAM (7.4 GB here). The ChronoNet data step needs scipy 1.18 (`pip install scipy==1.18.1`): with the conda scipy 1.16.3 a single long recording needs ~5 GB and the out-of-memory killer stops the whole tmux session (`journalctl -b | grep -i oom` shows it).
To keep a job alive overnight: leave one Ubuntu window open, laptop on the charger, and in Windows
power settings set sleep to Never and closing the lid to Do nothing (when plugged in).

## 1. Data (about 126 GB download, then 7 GB of features)

```bash
scripts/download_data.sh && python scripts/verify_data.py
```

```bash
python scripts/extract_features.py --workers 3
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

All of it unattended: `scripts/laptop/start.sh finish` waits for the running ChronoNet training, then
writes its test predictions and scores, then trains, predicts and scores the clean variant (about
5 h more on an RTX 3060). It can be started while `night` is still training; the internet must be on
for the predictions (the test EEG is streamed from S3, one file at a time). It resumes like the others.
`--final-test` is required because the published baseline is scored on the validation (= test)
patients; this is the M2 reproduction and is logged in `TEST_ACCESS.log`.

## Sending results back

`scripts/laptop/push_runs.sh` commits every scored ChronoNet run folder (unfinished ones are skipped)
and pushes it. Pushing needs a GitHub token once:

1. On github.com: Settings, Developer settings, Personal access tokens, Fine-grained tokens,
   Generate new token. Repository access: only `Final_year_proj`. Repository permissions:
   Contents, Read and write. A short expiry (7 days) is enough.
2. On the laptop, so the token is asked for only once (it is saved in plain text in
   `~/.git-credentials`; delete that file or revoke the token when done):

```bash
git config --global credential.helper store
```

3. Then (username: your GitHub user name; password: the token):

```bash
git pull && scripts/laptop/push_runs.sh
```

Pulling while `finish` is running is safe: the running steps have already loaded their code.

## 3. M4: DWN size sweep on the inner folds (the laptop's share, D32)

```bash
scripts/laptop/start.sh sweep
```

Builds the feature cache first if it is missing (streams the recordings from S3: hours, depending on the
connection; runs already cached are skipped), checks it against the M1 audit, then trains the 21 configs with
>= 500 LUTs on the GPU, most informative first. Three extraction workers, not more: each holds a whole
recording in memory and WSL has 7.4 GB. The cloud runs the rest of the grid. Send finished runs with
`scripts/laptop/push_runs.sh` (any time; unfinished runs are skipped).

## 4. Raw-EEG CNN/TCN and GRU references

Not yet implemented in this branch; they will be added as configs that run with `--device cuda`.
