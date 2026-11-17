"""Back-off of the combined spec point (ms/py/combined_backoff.py, LOG L21)."""
import combined_backoff as B


def fam(key, levels, status="limit", limit=None):
    lv = [{"name": f"{key.replace('/', '_')}_{l}", "level": l, "bit_flips_per_window": f} for l, f in levels]
    return {"status": status, "limit": limit if limit is not None else lv[-1]["level"], "levels": lv}


def src():
    return {"grids": {
        "eeg": {"families": {
            "eeg/lsb": fam("eeg/lsb", [(1, 0.1), (2, 0.5), (4, 3.0)]),
            "eeg/white": fam("eeg/white", [(1, 0.4), (2, 2.0)]),
            "eeg/pink": fam("eeg/pink", [(1, 0.2), (3, 0.3)], "beyond grid"),
            "eeg/gain+": fam("eeg/gain+", [(0.05, 1.0), (0.1, 5.0)], limit=0.05),
            "eeg/gain-": fam("eeg/gain-", [(0.05, 1.0), (0.1, 5.0)], limit=0.05),
            "eeg/lp": fam("eeg/lp", [(100, 9.0)], "none tolerated", limit=None)}},
        "ecg": {"families": {"ecg/lsb": fam("ecg/lsb", [(1, 0.1), (2, 2.0)])}}}}


def test_start_and_ranking():
    s = src()
    st = B.start_state(s)
    assert "eeg/lp" not in st and st["eeg/lsb"] == 2 and st["eeg/gain+"] == 0
    rk = B.ranking(s, st, {"gain+", "gain-"})
    assert [k for _, k, _ in rk][:3] == ["eeg/lsb", "eeg/white", "ecg/lsb"]   # 2.0 tie: eeg before ecg
    assert "eeg/gain+" not in [k for _, k, _ in B.ranking(s, st, {"gain-"})]   # gain+ job passed: not a candidate


def test_back_off_reranks_and_pink_follows_white():
    s = src()
    st = B.back_off(B.start_state(s), "eeg/lsb")
    assert st["eeg/lsb"] == 1
    assert B.ranking(s, st, set())[0][1] == "eeg/white"                      # lsb now 0.5 flips: white leads
    st = B.back_off(B.back_off(st, "eeg/white"), "eeg/white")
    assert st["eeg/white"] == -1 and st["eeg/pink"] == -1


def test_jobs_names_and_off():
    s = src()
    st = B.start_state(s)
    j0 = B.jobs_for(s, st, 0, True, [0, 1])
    assert {j["name"] for j in j0} == {"combined_preview_gain+", "combined_preview_gain-"} and len(j0) == 4
    st = B.back_off(B.back_off(B.back_off(st, "eeg/white"), "eeg/white"), "eeg/lsb")
    j = B.jobs_for(s, st, 3, False, [0])
    assert {x["name"] for x in j} == {"combined_b3_gain+", "combined_b3_gain-"}
    eeg = j[0]["impair"]["eeg"]
    assert "white_density" not in eeg and "pink_corner_hz" not in eeg and eeg["lsb"] == 2.0
    assert j[0]["impair"]["eeg"]["gain_err"] == 0.05 and j[1]["impair"]["eeg"]["gain_err"] == -0.05
