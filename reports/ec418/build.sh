#!/usr/bin/env bash
# Build the EC418 BISP project report (course format): out/SeizeLUT_EC418_Project_Report.pdf
set -euo pipefail
cd "$(dirname "$0")"
latexmk -pdf -interaction=nonstopmode -halt-on-error main.tex > build.log 2>&1 || { tail -40 build.log; exit 1; }
mkdir -p out
cp main.pdf out/SeizeLUT_EC418_Project_Report.pdf
rm -f out/SeizeLUT_EC418_overleaf.zip
zip -q -r out/SeizeLUT_EC418_overleaf.zip main.tex abstract.tex abbreviations.tex ch*.tex appendix.tex refs.bib figures
ls -la out
