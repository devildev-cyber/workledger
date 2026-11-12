from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, inspect, text
from sqlalchemy.orm import Session


def test_migrations_apply_to_an_empty_database(migrated_engine: Engine) -> None:
    assert "alembic_version" in inspect(migrated_engine).get_table_names()


def test_models_match_migrations(alembic_config: Config, migrated_engine: Engine) -> None:
    command.check(alembic_config)


def test_sqlite_enforces_foreign_keys(db_session: Session) -> None:
    assert db_session.execute(text("PRAGMA foreign_keys")).scalar_one() == 1
