from __future__ import annotations

import json
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def variables_payload() -> dict:
    return json.loads((FIXTURES / "variables_local.json").read_text(encoding="utf-8"))
