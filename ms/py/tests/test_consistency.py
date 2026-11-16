"""LSB vs white-noise cross-check (ms/py/consistency.py)."""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import consistency as C  # noqa: E402


def test_inband_qnoise():
    assert abs(C.inband_qnoise(math.sqrt(12), 128, 128) - 1.0) < 1e-12        # whole band: q/sqrt(12)
    assert abs(C.inband_qnoise(32, 99.5, 128) - 32 / math.sqrt(12) * math.sqrt(99.5 / 128)) < 1e-12


def fams(lsb_lim, lsb_fail, w_lim, w_fail):
    return {"eeg/lsb": {"status": "limit", "limit": lsb_lim, "first_failing": lsb_fail},
            "eeg/white": {"status": "limit", "limit": w_lim, "first_failing": w_fail}}


def test_agreement():
    assert C.check(fams(32, 64, 8, 16), "eeg")["agree"]                  # 8.1 < 16 and 16.3 > 8
    assert not C.check(fams(128, 256, 8, 16), "eeg")["agree"]            # q-noise at the LSB limit 32.6 >= 16
    assert not C.check(fams(4, 8, 8, 16), "eeg")["agree"]                # q-noise at the first failing LSB 2.0 <= 8
    assert C.check({"eeg/lsb": {"status": "limit", "limit": 1, "first_failing": 2}}, "eeg") is None
