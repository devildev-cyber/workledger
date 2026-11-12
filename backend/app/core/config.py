from datetime import timedelta
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]
MIN_SECRET_KEY_LENGTH = 32


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="WORKLEDGER_",
        env_file=REPO_ROOT / ".env",
        extra="ignore",
    )

    environment: Literal["development", "test", "production"] = "development"
    secret_key: SecretStr
    database_url: str = "sqlite:///./workledger.db"
    session_max_age_hours: int = Field(default=168, gt=0)
    session_idle_timeout_hours: int = Field(default=12, gt=0)

    @property
    def session_max_age(self) -> timedelta:
        return timedelta(hours=self.session_max_age_hours)

    @property
    def session_idle_timeout(self) -> timedelta:
        return timedelta(hours=self.session_idle_timeout_hours)

    @field_validator("secret_key")
    @classmethod
    def secret_key_is_long_enough(cls, value: SecretStr) -> SecretStr:
        if len(value.get_secret_value()) < MIN_SECRET_KEY_LENGTH:
            raise ValueError(f"must be at least {MIN_SECRET_KEY_LENGTH} characters")
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
