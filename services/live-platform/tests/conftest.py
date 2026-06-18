from __future__ import annotations

import pytest

from shared.config import settings


@pytest.fixture(autouse=True)
def reset_lazy_settings():
    yield
    settings.override(None)
