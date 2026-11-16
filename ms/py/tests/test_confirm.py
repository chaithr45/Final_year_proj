"""Full-data verdicts and the "marginal" label (ms/py/confirm_full.py, MS_SPEC step 7, LOG L18)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import confirm_full  # noqa: E402

D = {"delta_f1": 0.0092, "delta_fp24": 0.206}


def _job(name, d_f1, d_fa, p):
    return {"name": name, "d_f1": d_f1, "d_fp24": d_fa, "wilcoxon_p": p}


def test_verdicts():
    levels = {"eeg_white_2uVrms": {"f1_sd": 0.004, "fp24_sd": 0.05},
              "eeg_lsb_4uV": {"f1_sd": None, "fp24_sd": None}}
    J = [_job("eeg_white_2uVrms", -0.002, 0.0, 0.5),     # clear pass, far from both thresholds
         _job("eeg_white_2uVrms", -0.008, 0.0, 0.5),     # pass, 0.0012 from the F1 threshold < sd 0.004 -> marginal
         _job("eeg_white_2uVrms", -0.002, 0.18, 0.5),    # pass, 0.026 from the FA threshold < sd 0.05 -> marginal
         _job("eeg_white_2uVrms", -0.002, 0.0, 0.01),    # Wilcoxon significant -> not tolerated
         _job("eeg_white_2uVrms", -0.030, 0.0, 0.5),     # F1 drop too large, far beyond -> not marginal
         _job("eeg_lsb_4uV", -0.009, 0.0, 0.5),          # deterministic: never marginal
         _job("combined_gain+", -0.001, 0.0, 0.9)]       # not in the subset table: never marginal
    confirm_full.verdicts(J, D, levels)
    assert [j["tolerated"] for j in J] == [True, True, True, False, False, True, True]
    assert [j["marginal"] for j in J] == [False, True, True, False, False, False, False]
