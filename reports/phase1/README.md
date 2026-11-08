# College Phase 1 report

Source of the B.Tech Phase 1 report (literature survey, work done, challenges, Phase 2 plan).

* Chapters: `00_front.md` (title page, abstract) to `07_phase2_plan.md`; references in `refs.bib` (79 entries, each
  matched on title, authors, venue and year; entries with a `note` field list what to check on the publisher page).
* Build: `reports/phase1/build.sh` writes `out/SeizeLUT_Phase1_Report.docx` (editable) and `.pdf` (pandoc with
  citeproc and the IEEE style `ieee.csl`; Word template `reference.docx` from `make_reference_docx.py`; PDF through
  LibreOffice with the table of contents updated, `docx2pdf.py`).
* `survey_notes/`: the full survey tables per area, with the URL where each paper was verified and the limits of
  that check (abstract-level; full texts were not reachable from the build machine).
* Placeholders to fill: student names, roll numbers, guide, department on the title page.

All model results in the report are inner cross-validation on the 96 training patients; no model of ours has been
scored on the 29 test patients.
