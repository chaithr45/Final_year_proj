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

## 3. Current job: large DWNs on the LightGBM-gain features, then the raw-EEG CNN and TCN (D35)

If the old `sweep` job is still running, stop it first (its feature extraction resumes in the new job):

```bash
tmux kill-session -t sweep
```

```bash
git pull && scripts/laptop/start.sh big
```

Finishes and checks the training feature cache (streams the recordings from S3; runs already cached are
skipped; three workers, not more: each holds a whole recording in memory and WSL has 7.4 GB), trains 9 DWN
configs on the GPU (500, 1000 and 2000 LUTs at 8 bits, 1000 LUTs at 16 bits, then the Section 6.1 ablations at
500 LUTs: 4- and 5-input LUTs, tau 1 and 10, two layers), then the raw-EEG CNN and TCN (section 4), and pushes
the finished runs itself (`scripts/laptop/push_runs.sh`). Progress: `tail -n 3 logs/big.log`.

The old `sweep` job (21 configs on the mutual-information features, `scripts/laptop/sweep_big.sh`) is
superseded: D34 showed that the LightGBM-gain features beat them at the same size, so the size question is
asked again on the new features.

## 4. Raw-EEG 1-D CNN and TCN references (part of `big`)

Runs inside `big`; on its own (e.g. after a fix): `scripts/laptop/start.sh raw`.

Trains both on the ChronoNet cache of the 96 training patients (already on the laptop), fold by fold,
then streams the held-out patients' EEG once per fold and scores every second (most of the time goes
into streaming: roughly the 96 patients' EEG once). Uses the training feature cache from `big` for
the artefact flags and labels. Resumable per fold, recording and epoch. The GRU reference runs on the
cloud (`configs/m4/gru_lgbm40.yaml`).
