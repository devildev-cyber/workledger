from collections.abc import Callable, Iterator

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.bootstrap import main
from app.core.security import verify_password
from app.models import ActivityEvent, EventType, Organization, Role, User
from app.services.organizations import list_memberships_for_user

PASSWORD = "correct horse battery staple"
ARGS = ["--organization", "Harbor", "--email", "Admin@Example.com", "--name", "Alex Rivera"]


def prompts(*answers: str) -> Callable[[str], str]:
    remaining: Iterator[str] = iter(answers)
    return lambda _prompt: next(remaining)


def run(engine: Engine, args: list[str], *answers: str) -> int:
    return main(args, session_factory=lambda: Session(engine), read_password=prompts(*answers))


def test_creates_organization_and_administrator(
    migrated_engine: Engine, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run(migrated_engine, ARGS, PASSWORD, PASSWORD) == 0

    assert "Created organization 'Harbor'" in capsys.readouterr().out
    with Session(migrated_engine) as session:
        user = session.scalars(select(User)).one()
        assert user.email == "admin@example.com"
        assert verify_password(user.password_hash, PASSWORD)

        [membership] = list_memberships_for_user(session, user.id)
        assert membership.organization.name == "Harbor"
        assert membership.roles == {Role.ADMINISTRATOR}


def test_records_activity_events(migrated_engine: Engine) -> None:
    run(migrated_engine, ARGS, PASSWORD, PASSWORD)

    with Session(migrated_engine) as session:
        event_types = {event.event_type for event in session.scalars(select(ActivityEvent))}

    assert event_types == {EventType.ORGANIZATION_CREATED, EventType.MEMBERSHIP_CREATED}


def test_refuses_an_existing_user_and_changes_nothing(
    migrated_engine: Engine, capsys: pytest.CaptureFixture[str]
) -> None:
    run(migrated_engine, ARGS, PASSWORD, PASSWORD)
    capsys.readouterr()

    second = ["--organization", "Elm Street", "--email", "admin@example.com", "--name", "Other"]
    assert run(migrated_engine, second, "another long password", "another long password") == 1

    assert "already has an account" in capsys.readouterr().err
    with Session(migrated_engine) as session:
        assert [org.name for org in session.scalars(select(Organization))] == ["Harbor"]
        user = session.scalars(select(User)).one()
        assert verify_password(user.password_hash, PASSWORD)


def test_rejects_mismatched_passwords(
    migrated_engine: Engine, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run(migrated_engine, ARGS, PASSWORD, "something else entirely") == 1

    assert "do not match" in capsys.readouterr().err
    with Session(migrated_engine) as session:
        assert session.scalars(select(User)).all() == []


def test_rejects_a_short_password_and_saves_nothing(
    migrated_engine: Engine, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run(migrated_engine, ARGS, "short", "short") == 1

    assert "Password must be" in capsys.readouterr().err
    with Session(migrated_engine) as session:
        assert session.scalars(select(Organization)).all() == []


def test_rejects_an_invalid_email(
    migrated_engine: Engine, capsys: pytest.CaptureFixture[str]
) -> None:
    args = ["--organization", "Harbor", "--email", "not-an-email", "--name", "Alex"]

    assert run(migrated_engine, args, PASSWORD, PASSWORD) == 1
    assert "not valid" in capsys.readouterr().err
