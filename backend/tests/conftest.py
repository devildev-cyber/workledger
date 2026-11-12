from collections.abc import Iterator

import pytest

from app.core.config import get_settings

TEST_SECRET_KEY = "test-secret-key-that-is-long-enough-for-validation"


@pytest.fixture(autouse=True)
def test_environment(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("WORKLEDGER_ENVIRONMENT", "test")
    monkeypatch.setenv("WORKLEDGER_SECRET_KEY", TEST_SECRET_KEY)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
