#!/usr/bin/env bash
# Fetch B. Murmann's ADC Performance Survey at the pinned commit (read 15 Nov 2026) into data/external/ (git-ignored)
# and check the spreadsheet's SHA-256, so every ADC power number regenerates from the same file.
set -euo pipefail
cd "$(dirname "$0")/../.."
DIR=data/external/ADC-survey
COMMIT=00b4b855de5ce6bdf584a6aace354380022f1de4
SHA=fa9770f8d4c09c811eaddd0c11dd1f34fcaf8bdd96a164b670ca97921d177219
if [ ! -d "$DIR/.git" ]; then
  git clone --quiet https://github.com/bmurmann/ADC-survey.git "$DIR"
fi
git -C "$DIR" checkout --quiet "$COMMIT"
echo "$SHA  $DIR/xls/ADCsurvey_rev20260801.xlsx" | sha256sum -c -
