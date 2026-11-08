#!/usr/bin/env bash
# Build the NITW-format Phase I progress report: main.pdf (needs TeX Live with latex-extra and publishers),
# and out/SeizeLUT_Phase1_NITW_overleaf.zip (sources to upload to Overleaf).
set -euo pipefail
cd "$(dirname "$0")"
latexmk -pdf -interaction=nonstopmode -halt-on-error main.tex > build.log 2>&1 || { tail -40 build.log; exit 1; }
mkdir -p out
cp main.pdf out/SeizeLUT_Phase1_Progress_Report_NITW.pdf
rm -f out/SeizeLUT_Phase1_NITW_overleaf.zip
zip -q -r out/SeizeLUT_Phase1_NITW_overleaf.zip main.tex abstract.tex abbreviations.tex ch*.tex appendix.tex refs.bib figures
ls -la out
