import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import CSRF_HEADER_NAME
from app.core.config import Settings
from app.models import ActivityEvent, EventType, Membership, Role, User
from app.services.organizations import add_membership, create_organization
from app.services.users import create_user

PASSWORD = "correct horse battery staple"
ClientFactory = Callable[[Settings | None], TestClient]

ADMIN = "admin@harbor.example"
SECOND_ADMIN = "admin2@harbor.example"
MANAGER = "manager@harbor.example"
RESIDENT = "resident@harbor.example"
CONTRACTOR = "contractor@harbor.example"
OWNER = "owner@harbor.example"
ELM_ADMIN = "admin@elm.example"


@dataclass(frozen=True)
class World:
    harbor_id: uuid.UUID
    elm_id: uuid.UUID


@pytest.fixture
def world(db_session: Session) -> World:
    harbor = create_organization(db_session, name="Harbor", actor=None)
    elm = create_organization(db_session, name="Elm Street", actor=None)
    members = [
        (harbor, ADMIN, "Ada Admin", [Role.ADMINISTRATOR]),
        (harbor, MANAGER, "Mo Manager", [Role.MANAGER]),
        (harbor, RESIDENT, "Rae Resident", [Role.RESIDENT]),
        (harbor, CONTRACTOR, "Cy Contractor", [Role.CONTRACTOR]),
        (harbor, OWNER, "Olu Owner", [Role.PROPERTY_OWNER]),
        (elm, ELM_ADMIN, "Eli Admin", [Role.ADMINISTRATOR]),
        # Belongs to both organizations.
        (elm, RESIDENT, "Rae Resident", [Role.RESIDENT]),
    ]
    for organization, email, name, roles in members:
        user = db_session.scalar(select(User).where(User.email == email))
        if user is None:
            user = create_user(db_session, email=email, full_name=name, password=PASSWORD)
        add_membership(db_session, organization=organization, user=user, roles=roles, actor=None)
    db_session.commit()
    return World(harbor_id=harbor.id, elm_id=elm.id)


class SignedInClient:
    def __init__(self, client: TestClient, csrf_token: str) -> None:
        self.client = client
        self.headers = {CSRF_HEADER_NAME: csrf_token}

    def get(self, path: str) -> Any:
        return self.client.get(path)

    def put(self, path: str, **kwargs: Any) -> Any:
        return self.client.put(path, headers=self.headers, **kwargs)

    def delete(self, path: str) -> Any:
        return self.client.delete(path, headers=self.headers)


def sign_in_as(client_factory: ClientFactory, email: str) -> SignedInClient:
    client = client_factory(None)
    response = client.post("/api/auth/sign-in", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200
    return SignedInClient(client, response.json()["csrf_token"])


def membership_id(db: Session, organization_id: uuid.UUID, email: str) -> uuid.UUID:
    return db.scalars(
        select(Membership.id)
        .join(Membership.user)
        .where(Membership.organization_id == organization_id, User.email == email)
    ).one()


def roles_of(db: Session, membership: uuid.UUID) -> frozenset[Role]:
    db.expire_all()
    found = db.get(Membership, membership)
    assert found is not None
    return found.roles


def members_url(organization_id: uuid.UUID) -> str:
    return f"/api/organizations/{organization_id}/members"


def set_roles(
    session: SignedInClient, organization_id: uuid.UUID, member: uuid.UUID, *roles: Role
) -> Any:
    return session.put(
        f"{members_url(organization_id)}/{member}/roles",
        json={"roles": [role.value for role in roles]},
    )


def events_of(db: Session, event_type: EventType) -> list[ActivityEvent]:
    return list(db.scalars(select(ActivityEvent).where(ActivityEvent.event_type == event_type)))


@pytest.fixture
def make_second_admin(db_session: Session, world: World) -> Callable[[], None]:
    def make() -> None:
        user = create_user(
            db_session, email=SECOND_ADMIN, full_name="Sam Second", password=PASSWORD
        )
        organization = db_session.get(Membership, membership_id(db_session, world.harbor_id, ADMIN))
        assert organization is not None
        add_membership(
            db_session,
            organization=organization.organization,
            user=user,
            roles=[Role.ADMINISTRATOR],
            actor=None,
        )
        db_session.commit()

    return make


# --- Listing ----------------------------------------------------------------------------


def test_administrator_lists_members_of_the_organization_only(
    client_factory: ClientFactory, world: World
) -> None:
    admin = sign_in_as(client_factory, ADMIN)

    response = admin.get(members_url(world.harbor_id))

    assert response.status_code == 200
    members = response.json()
    assert [member["full_name"] for member in members] == [
        "Ada Admin",
        "Cy Contractor",
        "Mo Manager",
        "Olu Owner",
        "Rae Resident",
    ]
    ada = members[0]
    assert ada["email"] == ADMIN
    assert ada["roles"] == ["administrator"]
    assert ada["is_active"] is True
    assert {"id", "user_id", "joined_at"} <= ada.keys()
    assert "password" not in response.text


@pytest.mark.parametrize("email", [MANAGER, RESIDENT, CONTRACTOR, OWNER])
def test_only_administrators_can_manage_members(
    client_factory: ClientFactory, world: World, db_session: Session, email: str
) -> None:
    session = sign_in_as(client_factory, email)
    target = membership_id(db_session, world.harbor_id, RESIDENT)

    assert session.get(members_url(world.harbor_id)).status_code == 403
    assert set_roles(session, world.harbor_id, target, Role.MANAGER).status_code == 403
    assert session.delete(f"{members_url(world.harbor_id)}/{target}").status_code == 403

    assert roles_of(db_session, target) == {Role.RESIDENT}


def test_administrators_of_other_organizations_see_nothing(
    client_factory: ClientFactory, world: World, db_session: Session
) -> None:
    elm_admin = sign_in_as(client_factory, ELM_ADMIN)
    target = membership_id(db_session, world.harbor_id, RESIDENT)

    assert elm_admin.get(members_url(world.harbor_id)).status_code == 404
    assert set_roles(elm_admin, world.harbor_id, target, Role.MANAGER).status_code == 404
    assert elm_admin.delete(f"{members_url(world.harbor_id)}/{target}").status_code == 404


def test_signing_in_is_required(client_factory: ClientFactory, world: World) -> None:
    assert client_factory(None).get(members_url(world.harbor_id)).status_code == 401


def test_a_member_of_another_organization_cannot_be_reached_through_this_one(
    client_factory: ClientFactory, world: World, db_session: Session
) -> None:
    admin = sign_in_as(client_factory, ADMIN)
    elm_member = membership_id(db_session, world.elm_id, RESIDENT)

    assert set_roles(admin, world.harbor_id, elm_member, Role.MANAGER).status_code == 404
    assert admin.delete(f"{members_url(world.harbor_id)}/{elm_member}").status_code == 404
    assert db_session.get(Membership, elm_member) is not None


def test_changes_need_the_csrf_header(
    client_factory: ClientFactory, world: World, db_session: Session
) -> None:
    admin = sign_in_as(client_factory, ADMIN)
    target = membership_id(db_session, world.harbor_id, RESIDENT)

    response = admin.client.delete(f"{members_url(world.harbor_id)}/{target}")

    assert response.status_code == 403
    assert db_session.get(Membership, target) is not None


# --- Changing roles ---------------------------------------------------------------------


def test_administrator_changes_a_members_roles(
    client_factory: ClientFactory, world: World, db_session: Session
) -> None:
    admin = sign_in_as(client_factory, ADMIN)
    target = membership_id(db_session, world.harbor_id, RESIDENT)

    response = set_roles(admin, world.harbor_id, target, Role.RESIDENT, Role.MANAGER)

    assert response.status_code == 200
    assert response.json()["roles"] == ["manager", "resident"]
    assert roles_of(db_session, target) == {Role.MANAGER, Role.RESIDENT}

    # Taking a role away works the same way, and the member's other roles stay.
    response = set_roles(admin, world.harbor_id, target, Role.MANAGER)
    assert response.json()["roles"] == ["manager"]


def test_a_role_change_is_recorded_with_before_and_after(
    client_factory: ClientFactory, world: World, db_session: Session
) -> None:
    admin = sign_in_as(client_factory, ADMIN)
    target = membership_id(db_session, world.harbor_id, RESIDENT)

    set_roles(admin, world.harbor_id, target, Role.MANAGER)

    [event] = events_of(db_session, EventType.MEMBERSHIP_ROLES_CHANGED)
    admin_user = db_session.scalars(select(User).where(User.email == ADMIN)).one()
    assert event.organization_id == world.harbor_id
    assert event.actor_user_id == admin_user.id
    assert event.subject_id == target
    assert event.before is not None and event.before["roles"] == ["resident"]
    assert event.after is not None and event.after["roles"] == ["manager"]


def test_saving_the_same_roles_changes_nothing(
    client_factory: ClientFactory, world: World, db_session: Session
) -> None:
    admin = sign_in_as(client_factory, ADMIN)
    target = membership_id(db_session, world.harbor_id, RESIDENT)

    response = set_roles(admin, world.harbor_id, target, Role.RESIDENT)

    assert response.status_code == 200
    assert events_of(db_session, EventType.MEMBERSHIP_ROLES_CHANGED) == []


def test_a_member_needs_at_least_one_valid_role(
    client_factory: ClientFactory, world: World, db_session: Session
) -> None:
    admin = sign_in_as(client_factory, ADMIN)
    target = membership_id(db_session, world.harbor_id, RESIDENT)
    url = f"{members_url(world.harbor_id)}/{target}/roles"

    assert admin.put(url, json={"roles": []}).status_code == 422
    assert admin.put(url, json={"roles": ["emperor"]}).status_code == 422
    assert roles_of(db_session, target) == {Role.RESIDENT}


def test_the_last_administrator_cannot_lose_the_role(
    client_factory: ClientFactory, world: World, db_session: Session
) -> None:
    admin = sign_in_as(client_factory, ADMIN)
    own = membership_id(db_session, world.harbor_id, ADMIN)

    response = set_roles(admin, world.harbor_id, own, Role.MANAGER)

    assert response.status_code == 409
    assert "at least one administrator" in response.json()["detail"]
    assert roles_of(db_session, own) == {Role.ADMINISTRATOR}
    assert events_of(db_session, EventType.MEMBERSHIP_ROLES_CHANGED) == []


def test_an_administrator_can_step_down_when_another_remains(
    client_factory: ClientFactory,
    world: World,
    db_session: Session,
    make_second_admin: Callable[[], None],
) -> None:
    make_second_admin()
    admin = sign_in_as(client_factory, ADMIN)
    own = membership_id(db_session, world.harbor_id, ADMIN)

    response = set_roles(admin, world.harbor_id, own, Role.MANAGER)

    assert response.status_code == 200
    assert response.json()["roles"] == ["manager"]


def test_an_administrator_can_keep_the_role_while_gaining_others(
    client_factory: ClientFactory, world: World, db_session: Session
) -> None:
    admin = sign_in_as(client_factory, ADMIN)
    own = membership_id(db_session, world.harbor_id, ADMIN)

    response = set_roles(admin, world.harbor_id, own, Role.ADMINISTRATOR, Role.MANAGER)

    assert response.status_code == 200
    assert response.json()["roles"] == ["administrator", "manager"]


def test_a_new_administrator_can_be_promoted(
    client_factory: ClientFactory, world: World, db_session: Session
) -> None:
    admin = sign_in_as(client_factory, ADMIN)
    target = membership_id(db_session, world.harbor_id, MANAGER)

    response = set_roles(admin, world.harbor_id, target, Role.ADMINISTRATOR)

    assert response.status_code == 200
    promoted = sign_in_as(client_factory, MANAGER)
    assert promoted.get(members_url(world.harbor_id)).status_code == 200


# --- Removing ---------------------------------------------------------------------------


def test_administrator_removes_a_member(
    client_factory: ClientFactory, world: World, db_session: Session
) -> None:
    admin = sign_in_as(client_factory, ADMIN)
    target = membership_id(db_session, world.harbor_id, CONTRACTOR)

    response = admin.delete(f"{members_url(world.harbor_id)}/{target}")

    assert response.status_code == 204
    emails = [member["email"] for member in admin.get(members_url(world.harbor_id)).json()]
    assert CONTRACTOR not in emails
    # The account itself is kept, so history that refers to the person stays meaningful.
    assert db_session.scalars(select(User).where(User.email == CONTRACTOR)).one().is_active


def test_a_removed_member_loses_access_but_keeps_other_organizations(
    client_factory: ClientFactory, world: World, db_session: Session
) -> None:
    resident = sign_in_as(client_factory, RESIDENT)
    assert resident.get(f"/api/organizations/{world.harbor_id}").status_code == 200
    admin = sign_in_as(client_factory, ADMIN)
    target = membership_id(db_session, world.harbor_id, RESIDENT)

    admin.delete(f"{members_url(world.harbor_id)}/{target}")

    # The resident's existing session stops working for Harbor at once.
    assert resident.get(f"/api/organizations/{world.harbor_id}").status_code == 404
    assert resident.get(f"/api/organizations/{world.elm_id}").status_code == 200


def test_a_removal_is_recorded(
    client_factory: ClientFactory, world: World, db_session: Session
) -> None:
    admin = sign_in_as(client_factory, ADMIN)
    target = membership_id(db_session, world.harbor_id, OWNER)
    owner = db_session.scalars(select(User).where(User.email == OWNER)).one()

    admin.delete(f"{members_url(world.harbor_id)}/{target}")

    [event] = events_of(db_session, EventType.MEMBERSHIP_REMOVED)
    assert event.organization_id == world.harbor_id
    assert event.subject_id == target
    assert event.before == {"user_id": str(owner.id), "roles": ["property_owner"]}
    assert event.after is None


def test_removing_someone_twice_says_not_found(
    client_factory: ClientFactory, world: World, db_session: Session
) -> None:
    admin = sign_in_as(client_factory, ADMIN)
    target = membership_id(db_session, world.harbor_id, MANAGER)
    url = f"{members_url(world.harbor_id)}/{target}"

    assert admin.delete(url).status_code == 204
    assert admin.delete(url).status_code == 404


def test_the_last_administrator_cannot_be_removed(
    client_factory: ClientFactory, world: World, db_session: Session
) -> None:
    admin = sign_in_as(client_factory, ADMIN)
    own = membership_id(db_session, world.harbor_id, ADMIN)

    response = admin.delete(f"{members_url(world.harbor_id)}/{own}")

    assert response.status_code == 409
    assert "at least one administrator" in response.json()["detail"]
    assert db_session.get(Membership, own) is not None
    assert events_of(db_session, EventType.MEMBERSHIP_REMOVED) == []


def test_an_administrator_can_leave_when_another_remains(
    client_factory: ClientFactory,
    world: World,
    db_session: Session,
    make_second_admin: Callable[[], None],
) -> None:
    make_second_admin()
    admin = sign_in_as(client_factory, ADMIN)
    own = membership_id(db_session, world.harbor_id, ADMIN)

    assert admin.delete(f"{members_url(world.harbor_id)}/{own}").status_code == 204
    assert admin.get(members_url(world.harbor_id)).status_code == 404

    remaining = sign_in_as(client_factory, SECOND_ADMIN)
    assert remaining.get(members_url(world.harbor_id)).status_code == 200
