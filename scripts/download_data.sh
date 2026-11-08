#!/usr/bin/env bash
# Download SeizeIT2 (OpenNeuro ds005873, v1.1.0, ~126 GB) into data/raw/ds005873/.
#
#   scripts/download_data.sh                # full dataset, first route that works
#   scripts/download_data.sh --metadata     # sidecars + events + EDF headers only (~200 MB)
#   scripts/download_data.sh --subjects sub-001 sub-002   # selected subjects (full data)
#
# Routes tried in order (Section 3.3), the one used is printed and logged:
#   1. openneuro-py   2. aws s3 sync --no-sign-request   3. datalad
# Plan for >= 250 GB free for the full set; with less disk, stream instead
# (scripts/audit_signals.py --stream, and the M3 feature extractor streams per subject).
set -euo pipefail
cd "$(dirname "$0")/.."
TARGET=data/raw/ds005873
LOG=data/download.log
mkdir -p "$TARGET" data

if [[ "${1:-}" == "--metadata" ]]; then
  python scripts/fetch_metadata.py --root "$TARGET"
  echo "$(date -Is) metadata via S3 HTTPS (scripts/fetch_metadata.py)" >> "$LOG"
  exit 0
fi

SUBJECTS=()
if [[ "${1:-}" == "--subjects" ]]; then shift; SUBJECTS=("$@"); fi

route_openneuro() {
  command -v openneuro-py >/dev/null || return 1
  if ((${#SUBJECTS[@]})); then
    local inc=(); for s in "${SUBJECTS[@]}"; do inc+=(--include "$s"); done
    openneuro-py download --dataset ds005873 --target-dir "$TARGET" "${inc[@]}"
  else
    openneuro-py download --dataset ds005873 --target-dir "$TARGET"
  fi
}
route_aws() {
  command -v aws >/dev/null || return 1
  if ((${#SUBJECTS[@]})); then
    aws s3 sync --no-sign-request s3://openneuro.org/ds005873 "$TARGET" --exclude "sub-*" \
      $(for s in "${SUBJECTS[@]}"; do printf -- '--include %s/* ' "$s"; done)
  else
    aws s3 sync --no-sign-request s3://openneuro.org/ds005873 "$TARGET"
  fi
}
route_datalad() {
  command -v datalad >/dev/null || return 1
  [[ -d "$TARGET/.datalad" ]] || { rmdir "$TARGET" 2>/dev/null || true; datalad install -s https://github.com/OpenNeuroDatasets/ds005873.git "$TARGET"; }
  (cd "$TARGET" && if ((${#SUBJECTS[@]})); then datalad get "${SUBJECTS[@]}"; else datalad get .; fi)
}

for route in openneuro aws datalad; do
  echo ">>> trying $route"
  if "route_$route"; then
    echo "$(date -Is) full download via $route ${SUBJECTS[*]:-all subjects}" | tee -a "$LOG"
    python scripts/verify_data.py --root "$TARGET" || true
    exit 0
  fi
done
echo "No download route worked: pip install openneuro-py, or install awscli or datalad." >&2
exit 1
