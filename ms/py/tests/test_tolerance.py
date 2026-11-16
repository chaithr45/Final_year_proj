"""Rule D-MS10 as implemented in ms/py/tolerance.py, on synthetic sweep rows."""
import tolerance as T

CLEAN = {"f1": 0.30, "fp_per_24h": 1.0}


def r(name, seed, f1, fa):
    return {"name": name, "seed": seed, "f1": f1, "fp_per_24h": fa, "sensitivity": 0.3, "clipped_samples": 0}


def run(rows):
    return T.analyse(CLEAN, rows, 0.005, 0.1)


def test_parse():
    assert T.parse("mov_white_4LSBrms") == ("mov", "white", 4.0, "LSBrms")
    assert T.parse("eeg_pink_10Hz_white1uV") == ("eeg", "pink", 10.0, "Hz")
    assert T.parse("emg_offset_0.3C") == ("emg", "offset", 0.3, "C")
    assert T.parse("eeg_gain_-0.05") == ("eeg", "gain-", 0.05, "")
    assert T.parse("ecg_gain_+0.5") == ("ecg", "gain+", 0.5, "")


def test_limit_and_non_monotonic():
    a = run([r("eeg_lsb_1uV", 0, 0.30, 1.0), r("eeg_lsb_2uV", 0, 0.296, 1.05),   # both inside the band
             r("eeg_lsb_4uV", 0, 0.28, 1.0), r("eeg_lsb_8uV", 0, 0.299, 1.0)])   # 4 fails; 8 tolerated again
    f = a["eeg/lsb"]
    assert f["limit"] == 2.0 and f["first_failing"] == 4.0 and f["status"] == "limit"
    assert f["non_monotonic"] == ["eeg_lsb_8uV"]


def test_direction_and_false_alarms():
    a = run([r("eeg_clip_4096uV", 0, 0.30, 1.0), r("eeg_clip_1024uV", 0, 0.30, 1.2),   # FP rise 0.2 > 0.1 fails
             r("eeg_lp_100Hz", 0, 0.30, 1.0), r("eeg_lp_30Hz", 0, 0.30, 1.0)])
    assert a["eeg/clip"]["limit"] == 4096.0 and a["eeg/clip"]["first_failing"] == 1024.0
    assert [x["level"] for x in a["eeg/lp"]["levels"]] == [100.0, 30.0]           # mild (wide band) first
    assert a["eeg/lp"]["status"] == "beyond grid" and a["eeg/lp"]["limit"] == 30.0


def test_gain_split_and_none():
    a = run([r("eeg_gain_+0.05", 0, 0.30, 1.0), r("eeg_gain_-0.05", 0, 0.20, 1.0)])
    assert a["eeg/gain+"]["status"] == "beyond grid"
    assert a["eeg/gain-"]["status"] == "none tolerated" and a["eeg/gain-"]["limit"] is None


def test_seed_average():
    # seed mean 0.293 -> drop 0.007 > 0.005 fails although seed 0 alone (drop 0.004) would pass
    a = run([r("eeg_white_1uVrms", 0, 0.296, 1.0), r("eeg_white_1uVrms", 1, 0.290, 1.0)])
    lv = a["eeg/white"]["levels"][0]
    assert abs(lv["f1"] - 0.293) < 1e-12 and not lv["tolerated"] and lv["seeds"] == [0, 1]
