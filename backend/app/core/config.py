from datetime import timedelta
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
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
    # "file" writes .eml files to email_outbox_dir; "memory" is for tests; "smtp" sends for real.
    email_backend: Literal["file", "memory", "smtp"] = "file"
    email_from: str = "WorkLedger <no-reply@workledger.local>"
    email_outbox_dir: Path = Path("./outbox")
    smtp_host: str | None = None
    smtp_port: int = Field(default=587, gt=0, le=65535)
    smtp_username: str | None = None
    smtp_password: SecretStr | None = None
    # starttls: connect in plain text, then upgrade (usually port 587). ssl: encrypted from the
    # first byte (usually port 465). none: for a trusted local relay only.
    smtp_security: Literal["starttls", "ssl", "none"] = "starttls"
    # Where the browser app is served; invitation links point here.
    frontend_url: str = "http://localhost:5173"
    # Where uploaded files are kept (decision 0018). Back this directory up with the database.
    upload_dir: Path = Path("./uploads")
    max_upload_megabytes: int = Field(default=10, gt=0, le=100)
    invitation_valid_days: int = Field(default=7, gt=0)
    password_reset_valid_minutes: int = Field(default=60, gt=0)
    session_max_age_hours: int = Field(default=168, gt=0)
    session_idle_timeout_hours: int = Field(default=12, gt=0)
    # Protection against guessing passwords (decision 0025). After this many failed sign-ins
    # for one account, or from one address, sign-in is refused until the window has passed.
    sign_in_max_failures: int = Field(default=5, gt=0)
    sign_in_max_failures_per_address: int = Field(default=30, gt=0)
    sign_in_window_minutes: int = Field(default=15, gt=0)
    # How many password-reset emails one account, or one address, can ask for in an hour.
    reset_requests_per_hour: int = Field(default=5, gt=0)
    reset_requests_per_address_per_hour: int = Field(default=20, gt=0)
    # Read the client address from X-Forwarded-For only when a proxy you run sets it.
    trust_forwarded_for: bool = False

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_megabytes * 1024 * 1024

    @property
    def invitation_ttl(self) -> timedelta:
        return timedelta(days=self.invitation_valid_days)

    @property
    def password_reset_ttl(self) -> timedelta:
        return timedelta(minutes=self.password_reset_valid_minutes)

    @property
    def session_max_age(self) -> timedelta:
        return timedelta(hours=self.session_max_age_hours)

    @property
    def session_idle_timeout(self) -> timedelta:
        return timedelta(hours=self.session_idle_timeout_hours)

    @property
    def sign_in_window(self) -> timedelta:
        return timedelta(minutes=self.sign_in_window_minutes)

    @model_validator(mode="after")
    def production_is_configured_safely(self) -> "Settings":
        """Refuse to start in production with settings that are only fit for a laptop."""
        if self.email_backend == "smtp" and not self.smtp_host:
            raise ValueError("smtp_host is required when email_backend is smtp")
        if self.environment != "production":
            return self
        problems = []
        if not self.frontend_url.startswith("https://"):
            problems.append("frontend_url must use https://")
        if self.database_url.startswith("sqlite"):
            problems.append("database_url must be PostgreSQL, not SQLite")
        if self.email_backend != "smtp":
            problems.append("email_backend must be smtp")
        if problems:
            raise ValueError("unsafe production settings: " + "; ".join(problems))
        return self

    @field_validator("secret_key")
    @classmethod
    def secret_key_is_long_enough(cls, value: SecretStr) -> SecretStr:
        if len(value.get_secret_value()) < MIN_SECRET_KEY_LENGTH:
            raise ValueError(f"must be at least {MIN_SECRET_KEY_LENGTH} characters")
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
