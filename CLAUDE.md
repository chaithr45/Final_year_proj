# Notes for Claude sessions on this repository

SeizeLUT: a LUT-native multimodal seizure detector on SeizeIT2 (OpenNeuro ds005873). Milestones M1-M8 and their
status are in `README.md`; every decision and result is in `results/decisions.md` (failed ideas stay there).

## Rules (from the project brief; not negotiable)

- Test patients are sub-097..sub-125. No model of ours is scored on them before M6. Scripts that touch them need
  `--final-test` and log the access in the run's `TEST_ACCESS.log`. The only use so far is the ChronoNet
  reproduction (M2). Never pass `--final-test` for anything else without the user's go-ahead.
- Never invent numbers, citations or results. Report failures as they are.
- Never commit `data/`, `cache/`, `checkpoints/`, `logs/` or the SeizeIT2 paper PDF.
- Ask the user before changing the research question, the dataset, the split or the metrics.
- Work on branch `claude/optimistic-heisenberg-ph0bvj` only, and pull with rebase before every push. Open a pull
  request only when the user asks. Keep model names out of commits and files.

## Two sessions share the branch

- **Cloud session** (4 CPUs, no GPU): code, CPU runs, analysis, `results/decisions.md`, README, tables, paper.
- **Laptop session** (WSL Ubuntu, RTX 3060 6 GB, 7.4 GB RAM, conda env `seizelut`): GPU jobs only.

### If you are the laptop session

1. Your jobs are in `reports/LAPTOP_RUNBOOK.md` and start with `scripts/laptop/start.sh <job>` (tmux; every job
   resumes, so after an interruption run the same command again). Current job: `sweep` (builds the feature
   cache, then trains 21 DWN configs). Progress: `tail -n 3 logs/sweep.log`.
2. Send finished runs with `scripts/laptop/push_runs.sh` (it also sends `reports/LAPTOP_STATUS.md`).
3. If a job fails, read the log and retry once. If it fails again, do not edit `src/`, `scripts/` or configs:
   write the error, the log excerpt and your diagnosis into `reports/LAPTOP_STATUS.md` and run `push_runs.sh`.
   The cloud session fixes code; then `git pull` and restart the job.
4. Do not edit `results/decisions.md`, `README.md` or `results/tables/` (the cloud session regenerates them).
5. Run one heavy job at a time: WSL has 7.4 GB, and the out-of-memory killer ends the whole tmux session
   (`journalctl -b | grep -i oom` shows it).
6. After every `git pull`, check the runbook for new jobs.

### If you are the cloud session

Do not edit a script while the laptop is running it (bash reads scripts as it runs them); currently
`scripts/laptop/sweep_big.sh`. Laptop results arrive as commits named "Laptop runs: ..."; regenerate the tables
(`python scripts/make_tables.py`) and log them in `results/decisions.md`.
