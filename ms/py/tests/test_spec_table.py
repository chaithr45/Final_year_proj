"""Spec table (ms/py/spec_table.py): power from the NEF definition and the combined-point levels."""
import json
import math

import spec_table as T


def test_amp_current_scaling():
    i1, i2 = T.amp_current(2.0, 4e-6), T.amp_current(2.0, 8e-6)
    assert abs(i1 / i2 - 4.0) < 1e-12                         # current ~ 1/noise^2
    assert abs(T.amp_current(4.0, 4e-6) / i1 - 4.0) < 1e-12   # current ~ NEF^2
    assert T.bits_for(1024, 32) == 6 and T.bits_for(8192, 0.25) == 16


def test_combined_levels(tmp_path):
    lv = lambda k, xs: [{"name": f"{k}_{x}", "level": x} for x in xs]
    tol = {"grids": {"eeg": {"families": {"eeg/lsb": {"levels": lv("eeg_lsb", [16, 32])},
                                          "eeg/white": {"levels": lv("eeg_white", [4, 8])}}}}}
    b = {"status": "passed", "preview": False,
         "steps": [{"step": 2, "levels": {"eeg/lsb": "eeg_lsb_16", "eeg/white": "off"}}]}
    (tmp_path / "combined_backoff.json").write_text(json.dumps(b))
    c, basis = T.combined_levels(tol, tmp_path)
    assert c == {"eeg/lsb": ("value", 16), "eeg/white": ("off", None)} and "subset only (step 2)" in basis
    b["preview"] = True
    (tmp_path / "combined_backoff.json").write_text(json.dumps(b))
    assert T.combined_levels(tol, tmp_path) == ({}, None)      # a preview never feeds the spec table
