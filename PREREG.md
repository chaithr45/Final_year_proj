# SeizeLUT-MS pre-registration

Rule (ground rule 2): the frozen classifier and the 29 test patients (sub-097..sub-125) are untouchable. All
sweeps, tolerance studies and design choices of the mixed-signal study use the 96 training patients only
(inner folds, `configs/folds_inner5.json`). Any analysis that must read test-patient data is written here
**first**, with its exact procedure and outputs, committed, and run only after you say yes in the chat. Every such run
uses the existing `--final-test` guard and appends to the run's `TEST_ACCESS.log`.

Entry format: `P<n> | date | what will be read | exact procedure | outputs | decision it may change (should be none) | status`.

## Registry

| ID | Date | Test-patient data read | Procedure | Outputs | Status |
|---|---|---|---|---|---|
| (none) | 15 Nov 2026 | none | Phase 0 read no test-patient data. The quick RTL check (`verify_kv260_rtl.py --quick`) replays the committed vectors of one test recording (sub-097 run-10) through the RTL; that is the FCCM M7 hardware check, already logged, and compares hardware against software only (no detection metric) | none | — |

## Already-used test-patient material in the repository (for reference, from the FCCM work)

These files contain test-patient data and were produced under the FCCM project's own logged accesses
(`export/n4_distill_s0/TEST_ACCESS.log`, `results/decisions.md` D39-D40). The mixed-signal study uses them only for
hardware-equals-software checks, never to choose or tune anything:

- `hw/kv260/board/vectors/*.npz`, `hw/kv260/sim/vectors/*.hex`: features of 10 test recordings (431,960 windows).
- `hw/kv260/board/raw/*.npz`: raw samples of 3 test recordings (board step 7).
- `hw/kv260/demo/segments/*.npz`: demo segments cut from the above.

## Planned entries (not registered yet; to be written in full before use)

- **Phase 4 replay subset.** If you want a detection result through the real analog chain on test patients, it must be
  registered here first. The default plan replays **training-fold** seizures plus matched background, and needs no
  entry.
