#!/usr/bin/env bash
# Build the Phase 1 report: Word (editable) and PDF, with numbered IEEE-style references from refs.bib.
#   reports/phase1/build.sh   -> reports/phase1/out/SeizeLUT_Phase1_Report.docx and .pdf
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p out
python ../../scripts/make_report_diagrams.py > /dev/null
pandoc 00_front.md 01_introduction.md 02a_lit_clinical.md 02b_lit_algorithms.md 02d_lit_lut.md 02e_lit_hardware.md \
  02f_lit_gaps.md 03_dataset.md 04_method.md 05_work_done.md 06_challenges.md 07_phase2_plan.md 99_references.md \
  --citeproc --bibliography refs.bib --csl ieee.csl --reference-doc reference.docx --resource-path=.:..:../.. --toc --toc-depth=2 \
  -o out/SeizeLUT_Phase1_Report.docx
python docx2pdf.py out/SeizeLUT_Phase1_Report.docx out/SeizeLUT_Phase1_Report.pdf || echo "PDF conversion failed (LibreOffice)"
ls -la out
