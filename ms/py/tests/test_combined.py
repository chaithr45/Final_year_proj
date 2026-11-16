"""Combined spec point (ms/py/combined.py): the merged impairment of a modality is valid for impair.py."""
import json

import combined as C
import impair as IMP
import tolerance as T

CLEAN = {"f1": 0.30, "fp_per_24h": 1.0}


def r(name, f1=0.30, fa=1.0):
    return {"name": name, "seed": 0, "f1": f1, "fp_per_24h": fa, "sensitivity": 0.3, "clipped_samples": 0}


def test_combined_eeg_compiles():
    rows = [r("eeg_lsb_2uV"), r("eeg_lsb_4uV", 0.2), r("eeg_clip_2048uV"), r("eeg_white_2uVrms"),
            r("eeg_pink_3Hz_white1uV"), r("eeg_gain_+0.1"), r("eeg_gain_-0.05"), r("eeg_gain_-0.1", 0.2),
            r("eeg_offset_0.3C"), r("eeg_drift_100uVrms"), r("eeg_mains50_10uV"), r("eeg_mains250_1uV", 0.2),
            r("eeg_hp_0.3Hz"), r("eeg_lp_70Hz"), r("eeg_lp_50Hz", 0.2)]
    fams = T.analyse(CLEAN, rows, 0.005, 0.1)
    kw, ex = C.impair_for("eeg", fams, -1)
    assert ex == ["eeg/mains250"]                       # 250 Hz failed at its mildest level: excluded
    assert kw["lsb"] == 2.0 and kw["clip"] == 2048.0 and kw["gain_err"] == -0.05 and kw["lp_hz"] == 70.0
    assert kw["mains_peak"] == (10.0, 0.0, 0.0, 0.0, 0.0) and kw["pink_corner_hz"] == 3.0
    kw = json.loads(json.dumps(kw))                     # as stored in combined_jobs.json (tuple -> list)
    c = IMP.compile_impairment(IMP.Impairment(**kw), 256.0, 0.25)
    assert c.hp is not None and c.lp is not None and c.white_c != 0 and c.pink_c != 0 and c.mains_c
