#!/usr/bin/env bash
# Commit the finished ChronoNet run folders on the laptop and push them to the working branch.
#   scripts/laptop/push_runs.sh        (safe to run again: only runs not yet committed are added)
# A run still in progress has a .gitignore of '*' (removed when it is scored), so git skips it.
# Only a run's small text files go in git (config, history, selected epoch, metrics, TEST_ACCESS.log);
# predictions and checkpoints stay in cache/ and checkpoints/, which git ignores.
# Pushing needs a GitHub token once: see reports/LAPTOP_RUNBOOK.md, "Sending results back".
set -euo pipefail
cd "$(dirname "$0")/../.."
branch=claude/optimistic-heisenberg-ph0bvj
if [ -z "$(git config user.email || true)" ]; then
  echo 'git does not know who you are yet; run this once, then this script again:'
  echo '  git config --global user.name "<your name>" && git config --global user.email "<your GitHub email>"'
  exit 1
fi
shopt -s nullglob
dirs=(results/runs/*_chrononet_official_s* results/runs/*_chrononet_clean_s*)
[ ${#dirs[@]} -gt 0 ] && git add -- "${dirs[@]}"
if git diff --cached --quiet; then
  echo "no newly finished run to commit"
else
  git diff --cached --stat
  names=$(git diff --cached --name-only | sed -n 's#^results/runs/\([^/]*\)/.*#\1#p' | sort -u | paste -sd' ' -)
  git commit -q -m "M2: ChronoNet run(s) from the laptop: $names"
fi
git pull -q --rebase --autostash origin "$branch"
git push origin "HEAD:$branch"
