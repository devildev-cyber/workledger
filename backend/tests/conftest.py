import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import create_db_engine

TEST_SECRET_KEY = "test-secret-key-that-is-long-enough-for-validation"
BACKEND_DIR = Path(__file__).resolve().parents[1]

# Set before test modules are imported, because importing app.main builds the app.
os.environ["WORKLEDGER_ENVIRONMENT"] = "test"
os.environ["WORKLEDGER_SECRET_KEY"] = TEST_SECRET_KEY


@pytest.fixture(autouse=True)
def fresh_settings() -> Iterator[None]:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def alembic_config(tmp_path: Path) -> Config:
    config = Config(BACKEND_DIR / "alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{tmp_path / 'test.db'}")
    return config


@pytest.fixture
def migrated_engine(alembic_config: Config) -> Iterator[Engine]:
    command.upgrade(alembic_config, "head")
    engine = create_db_engine(alembic_config.get_main_option("sqlalchemy.url"))
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(migrated_engine: Engine) -> Iterator[Session]:
    with Session(migrated_engine) as session:
        yield session
