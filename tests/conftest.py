from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def schema_path() -> Path:
    return Path("schemas/auditor_verdict.schema.json")
