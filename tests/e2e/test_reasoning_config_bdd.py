"""pytest-bdd glue for reasoning config E2E scenarios."""

from __future__ import annotations

from pathlib import Path

import pytest
from pytest_bdd import scenarios

pytestmark = pytest.mark.e2e

_FEATURES = Path(__file__).parent / "features"
scenarios((_FEATURES / "reasoning_config.feature").as_posix())
