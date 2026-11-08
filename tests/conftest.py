from pathlib import Path

import pytest

FIXTURE = Path(__file__).parent / "fixtures" / "synthetic_bids"


@pytest.fixture(scope="session")
def bids_root() -> Path:
    assert FIXTURE.exists(), "run: python tests/fixtures/make_synthetic_bids.py"
    return FIXTURE
