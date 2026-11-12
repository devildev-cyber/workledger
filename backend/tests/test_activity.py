from datetime import timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ActivityEvent, ActivityEventImmutableError, EventType, Organization, Role
from app.services.organizations import add_membership, create_organization
from app.services.users import create_user

PASSWORD = "correct horse battery staple"


def events(session: Session) -> list[ActivityEvent]:
    return list(session.scalars(select(ActivityEvent).order_by(ActivityEvent.occurred_at)))


def test_creating_an_organization_records_an_attributed_event(db_session: Session) -> None:
    operator = create_user(db_session, email="op@example.com", full_name="Op", password=PASSWORD)

    organization = create_organization(db_session, name="Harbor", actor=operator)
    db_session.commit()
    db_session.expire_all()

    [event] = events(db_session)
    assert event.event_type == EventType.ORGANIZATION_CREATED
    assert event.organization_id == organization.id
    assert event.actor_user_id == operator.id
    assert event.subject_type == "organization"
    assert event.subject_id == organization.id
    assert event.before is None
    assert event.after == {"name": "Harbor"}
    assert event.occurred_at.utcoffset() == timedelta(0)


def test_adding_a_member_records_their_roles(db_session: Session) -> None:
    user = create_user(db_session, email="ana@example.com", full_name="Ana", password=PASSWORD)
    organization = create_organization(db_session, name="Harbor", actor=None)

    membership = add_membership(
        db_session,
        organization=organization,
        user=user,
        roles=[Role.MANAGER, Role.ADMINISTRATOR],
        actor=None,
    )

    event = events(db_session)[-1]
    assert event.event_type == EventType.MEMBERSHIP_CREATED
    assert event.subject_id == membership.id
    assert event.actor_user_id is None
    assert event.after == {"user_id": str(user.id), "roles": ["administrator", "manager"]}


def test_event_and_change_are_rolled_back_together(db_session: Session) -> None:
    create_organization(db_session, name="Harbor", actor=None)

    db_session.rollback()

    assert db_session.scalars(select(Organization)).all() == []
    assert events(db_session) == []


def test_events_cannot_be_changed(db_session: Session) -> None:
    create_organization(db_session, name="Harbor", actor=None)
    db_session.flush()
    [event] = events(db_session)

    event.event_type = "organization.renamed"

    with pytest.raises(ActivityEventImmutableError):
        db_session.flush()


def test_events_cannot_be_deleted(db_session: Session) -> None:
    create_organization(db_session, name="Harbor", actor=None)
    db_session.flush()
    [event] = events(db_session)

    db_session.delete(event)

    with pytest.raises(ActivityEventImmutableError):
        db_session.flush()
