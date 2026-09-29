import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


@pytest.fixture
def fixtures_dir():
    return Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def _sebi_registration_number(monkeypatch):
    """Tests use a syntactically valid, obviously fake registration number."""
    monkeypatch.setenv("SEBI_RA_REGISTRATION_NUMBER", "INH000012345")
