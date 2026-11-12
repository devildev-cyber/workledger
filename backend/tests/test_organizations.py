import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Membership, MembershipRole, Role, User
from app.services.organizations import (
    AlreadyMemberError,
    NoRolesError,
    add_membership,
    create_organization,
    get_membership,
    list_memberships_for_user,
)
from app.services.users import create_user

PASSWORD = "correct horse battery staple"


def make_user(session: Session, email: str) -> User:
    return create_user(session, email=email, full_name=email.split("@")[0], password=PASSWORD)


def test_user_can_belong_to_two_organizations_with_different_roles(db_session: Session) -> None:
    contractor = make_user(db_session, "pat@plumbing.example")
    harbor = create_organization(db_session, name="Harbor Property Management")
    elm = create_organization(db_session, name="Elm Street Rentals")

    add_membership(db_session, organization=harbor, user=contractor, roles=[Role.CONTRACTOR])
    add_membership(
        db_session, organization=elm, user=contractor, roles=[Role.CONTRACTOR, Role.RESIDENT]
    )

    memberships = list_memberships_for_user(db_session, contractor.id)

    assert [m.organization.name for m in memberships] == [
        "Elm Street Rentals",
        "Harbor Property Management",
    ]
    assert memberships[0].roles == {Role.CONTRACTOR, Role.RESIDENT}
    assert memberships[1].roles == {Role.CONTRACTOR}


def test_roles_are_reloaded_from_the_database(db_session: Session) -> None:
    user = make_user(db_session, "ana@example.com")
    organization = create_organization(db_session, name="Harbor")
    add_membership(
        db_session, organization=organization, user=user, roles=[Role.ADMINISTRATOR, Role.MANAGER]
    )
    db_session.commit()
    db_session.expire_all()

    membership = get_membership(db_session, organization_id=organization.id, user_id=user.id)

    assert membership is not None
    assert membership.roles == {Role.ADMINISTRATOR, Role.MANAGER}


def test_user_cannot_join_the_same_organization_twice(db_session: Session) -> None:
    user = make_user(db_session, "ana@example.com")
    organization = create_organization(db_session, name="Harbor")
    add_membership(db_session, organization=organization, user=user, roles=[Role.MANAGER])

    with pytest.raises(AlreadyMemberError):
        add_membership(db_session, organization=organization, user=user, roles=[Role.RESIDENT])


def test_membership_needs_at_least_one_role(db_session: Session) -> None:
    user = make_user(db_session, "ana@example.com")
    organization = create_organization(db_session, name="Harbor")

    with pytest.raises(NoRolesError):
        add_membership(db_session, organization=organization, user=user, roles=[])


def test_database_rejects_duplicate_memberships(db_session: Session) -> None:
    user = make_user(db_session, "ana@example.com")
    organization = create_organization(db_session, name="Harbor")
    db_session.add(Membership(organization=organization, user=user))
    db_session.add(Membership(organization=organization, user=user))

    with pytest.raises(IntegrityError):
        db_session.flush()


def test_database_rejects_unknown_roles(db_session: Session) -> None:
    user = make_user(db_session, "ana@example.com")
    organization = create_organization(db_session, name="Harbor")
    membership = add_membership(
        db_session, organization=organization, user=user, roles=[Role.MANAGER]
    )

    with pytest.raises(IntegrityError):
        db_session.execute(
            text("INSERT INTO membership_roles (membership_id, role) VALUES (:id, 'superuser')"),
            {"id": membership.id.hex},
        )


def test_deleting_a_membership_deletes_its_roles(db_session: Session) -> None:
    user = make_user(db_session, "ana@example.com")
    organization = create_organization(db_session, name="Harbor")
    membership = add_membership(
        db_session, organization=organization, user=user, roles=[Role.MANAGER, Role.RESIDENT]
    )

    db_session.delete(membership)
    db_session.flush()

    assert db_session.scalars(select(MembershipRole)).all() == []
