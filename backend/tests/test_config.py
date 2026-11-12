import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_reads_settings_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WORKLEDGER_DATABASE_URL", "sqlite:///./other.db")

    settings = Settings(_env_file=None)

    assert settings.environment == "test"
    assert settings.database_url == "sqlite:///./other.db"


def test_missing_secret_key_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("WORKLEDGER_SECRET_KEY")

    with pytest.raises(ValidationError, match="secret_key"):
        Settings(_env_file=None)


def test_short_secret_key_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WORKLEDGER_SECRET_KEY", "too-short")

    with pytest.raises(ValidationError, match="at least 32 characters"):
        Settings(_env_file=None)
