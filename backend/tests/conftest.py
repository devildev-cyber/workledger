import os
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.mail import MemoryEmailSender
from app.db.session import create_db_engine, get_session

TEST_SECRET_KEY = "test-secret-key-that-is-long-enough-for-validation"
# Set this to run the whole suite against PostgreSQL instead of a throwaway SQLite file. The
# database must be empty and disposable: every test starts by wiping its public schema.
POSTGRES_TEST_URL = os.environ.get("WORKLEDGER_TEST_DATABASE_URL")
BACKEND_DIR = Path(__file__).resolve().parents[1]

# Set before test modules are imported, because importing app.main builds the app.
os.environ["WORKLEDGER_ENVIRONMENT"] = "test"
os.environ["WORKLEDGER_SECRET_KEY"] = TEST_SECRET_KEY
os.environ["WORKLEDGER_EMAIL_BACKEND"] = "memory"


@pytest.fixture(autouse=True)
def fresh_settings() -> Iterator[None]:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def alembic_config(tmp_path: Path) -> Config:
    config = Config(BACKEND_DIR / "alembic.ini")
    url = POSTGRES_TEST_URL or f"sqlite:///{tmp_path / 'test.db'}"
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return config


def _wipe_postgres(url: str) -> None:
    engine = create_db_engine(url)
    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))
    engine.dispose()


@pytest.fixture
def migrated_engine(alembic_config: Config) -> Iterator[Engine]:
    url = alembic_config.get_main_option("sqlalchemy.url").replace("%%", "%")
    if POSTGRES_TEST_URL:
        _wipe_postgres(url)
    command.upgrade(alembic_config, "head")
    engine = create_db_engine(url)
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(migrated_engine: Engine) -> Iterator[Session]:
    with Session(migrated_engine) as session:
        yield session


@pytest.fixture
def outbox() -> MemoryEmailSender:
    """Every email sent by any client built in this test."""
    return MemoryEmailSender()


@pytest.fixture
def client_factory(
    migrated_engine: Engine, outbox: MemoryEmailSender
) -> Callable[[Settings | None], TestClient]:
    """Build API clients wired to the disposable migrated database and the shared outbox."""

    def build(settings: Settings | None = None) -> TestClient:
        # Imported here because importing app.main builds the app, which needs the
        # test environment variables set at the top of this file.
        from app.main import create_app

        app = create_app(settings, email_sender=outbox)

        def use_test_database() -> Iterator[Session]:
            with Session(migrated_engine) as session:
                yield session

        app.dependency_overrides[get_session] = use_test_database
        return TestClient(app)

    return build


@pytest.fixture
def client(client_factory: Callable[[Settings | None], TestClient]) -> TestClient:
    return client_factory(None)
