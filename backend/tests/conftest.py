import os
from collections.abc import Iterator

import pytest

from app.core.config import get_settings

TEST_SECRET_KEY = "test-secret-key-that-is-long-enough-for-validation"

# Set before test modules are imported, because importing app.main builds the app.
os.environ["WORKLEDGER_ENVIRONMENT"] = "test"
os.environ["WORKLEDGER_SECRET_KEY"] = TEST_SECRET_KEY


@pytest.fixture(autouse=True)
def fresh_settings() -> Iterator[None]:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
