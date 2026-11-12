import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated

import pytest
from fastapi import APIRouter, Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.access import MemberContext, OrganizationContext, require_roles
from app.core.config import Settings
from app.core.permissions import PropertyScope
from app.models import ActivityEvent, Role, User
from app.services.organizations import add_membership, create_organization
from app.services.users import create_user

PASSWORD = "correct horse battery staple"
ROLE_EMAILS = {role: f"{role.value}@harbor.example" for role in Role}
ELM_ADMIN_EMAIL = "admin@elm.example"
# Manager at Harbor but administrator at Elm Street: one account, two memberships.
MULTI_EMAIL = "multi@example.com"

ClientFactory = Callable[[Settings | None], TestClient]


@dataclass(frozen=True)
class World:
    harbor_id: uuid.UUID
    elm_id: uuid.UUID


@pytest.fixture
def world(db_session: Session) -> World:
    harbor = create_organization(db_session, name="Harbor", actor=None)
    elm = create_organization(db_session, name="Elm Street", actor=None)

    def member(email: str, organization_id: uuid.UUID, *roles: Role) -> None:
        organization = harbor if organization_id == harbor.id else elm
        user = db_session.scalar(select(User).where(User.email == email))
        if user is None:
            user = create_user(db_session, email=email, full_name=email, password=PASSWORD)
        add_membership(db_session, organization=organization, user=user, roles=roles, actor=None)

    for role in Role:
        member(ROLE_EMAILS[role], harbor.id, role)
    member(ELM_ADMIN_EMAIL, elm.id, Role.ADMINISTRATOR)
    member(MULTI_EMAIL, harbor.id, Role.MANAGER)
    member(MULTI_EMAIL, elm.id, Role.ADMINISTRATOR)

    db_session.commit()
    return World(harbor_id=harbor.id, elm_id=elm.id)


def sign_in_as(client_factory: ClientFactory, email: str) -> TestClient:
    client = client_factory(None)
    response = client.post("/api/auth/sign-in", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200
    return client


def event_ids(db: Session, organization_id: uuid.UUID) -> set[str]:
    return {
        str(event_id)
        for event_id in db.scalars(
            select(ActivityEvent.id).where(ActivityEvent.organization_id == organization_id)
        )
    }


def add_probe_routes(client: TestClient) -> None:
    """Add test-only endpoints, one per role, to exercise the role checks directly."""
    app = client.app
    assert isinstance(app, FastAPI)
    router = APIRouter(prefix="/api/organizations/{organization_id}/probe")

    for role in Role:

        @router.get(f"/{role.value}")
        def requires_role(
            context: Annotated[OrganizationContext, Depends(require_roles(role))],
        ) -> dict[str, str]:
            return {"organization": context.organization.name}

    @router.get("/manager-or-administrator")
    def requires_either(
        context: Annotated[
            OrganizationContext, Depends(require_roles(Role.MANAGER, Role.ADMINISTRATOR))
        ],
    ) -> dict[str, str]:
        return {"organization": context.organization.name}

    @router.get("/scope")
    def read_scope(context: MemberContext) -> dict[str, bool]:
        return {"unrestricted": context.property_scope.unrestricted}

    app.include_router(router)


# --- Organization isolation -------------------------------------------------------------


def test_member_can_read_their_organization(client_factory: ClientFactory, world: World) -> None:
    client = sign_in_as(client_factory, ROLE_EMAILS[Role.RESIDENT])

    response = client.get(f"/api/organizations/{world.harbor_id}")

    assert response.status_code == 200
    assert response.json() == {
        "id": str(world.harbor_id),
        "name": "Harbor",
        "roles": ["resident"],
    }


def test_signed_out_requests_are_rejected(client: TestClient, world: World) -> None:
    assert client.get(f"/api/organizations/{world.harbor_id}").status_code == 401
    assert client.get(f"/api/organizations/{world.harbor_id}/activity").status_code == 401


def test_other_organizations_look_exactly_like_missing_ones(
    client_factory: ClientFactory, world: World
) -> None:
    elm_admin = sign_in_as(client_factory, ELM_ADMIN_EMAIL)

    for path in ("", "/activity"):
        real_but_foreign = elm_admin.get(f"/api/organizations/{world.harbor_id}{path}")
        nonexistent = elm_admin.get(f"/api/organizations/{uuid.uuid4()}{path}")

        assert real_but_foreign.status_code == nonexistent.status_code == 404
        assert real_but_foreign.json() == nonexistent.json()


def test_an_administrator_elsewhere_gets_no_power_here(
    client_factory: ClientFactory, world: World
) -> None:
    elm_admin = sign_in_as(client_factory, ELM_ADMIN_EMAIL)

    assert elm_admin.get(f"/api/organizations/{world.elm_id}/activity").status_code == 200
    assert elm_admin.get(f"/api/organizations/{world.harbor_id}/activity").status_code == 404


def test_activity_only_includes_the_requested_organizations_events(
    client_factory: ClientFactory, world: World, db_session: Session
) -> None:
    harbor_admin = sign_in_as(client_factory, ROLE_EMAILS[Role.ADMINISTRATOR])
    elm_admin = sign_in_as(client_factory, ELM_ADMIN_EMAIL)

    harbor_ids = {
        e["id"]
        for e in harbor_admin.get(f"/api/organizations/{world.harbor_id}/activity?limit=200").json()
    }
    elm_ids = {
        e["id"]
        for e in elm_admin.get(f"/api/organizations/{world.elm_id}/activity?limit=200").json()
    }

    assert harbor_ids == event_ids(db_session, world.harbor_id)
    assert elm_ids == event_ids(db_session, world.elm_id)
    assert harbor_ids and elm_ids
    assert harbor_ids.isdisjoint(elm_ids)


def test_one_account_has_separate_roles_in_each_organization(
    client_factory: ClientFactory, world: World
) -> None:
    multi = sign_in_as(client_factory, MULTI_EMAIL)

    harbor = multi.get(f"/api/organizations/{world.harbor_id}").json()
    elm = multi.get(f"/api/organizations/{world.elm_id}").json()

    assert harbor["roles"] == ["manager"]
    assert elm["roles"] == ["administrator"]
    assert multi.get(f"/api/organizations/{world.harbor_id}/activity").status_code == 403
    assert multi.get(f"/api/organizations/{world.elm_id}/activity").status_code == 200


# --- Role checks ------------------------------------------------------------------------


def test_activity_history_is_for_administrators_only(
    client_factory: ClientFactory, world: World
) -> None:
    for role in Role:
        client = sign_in_as(client_factory, ROLE_EMAILS[role])

        status_code = client.get(f"/api/organizations/{world.harbor_id}/activity").status_code

        expected = 200 if role is Role.ADMINISTRATOR else 403
        assert status_code == expected, f"{role.value} got {status_code}, expected {expected}"


def test_every_role_is_allowed_only_where_it_is_listed(
    client_factory: ClientFactory, world: World
) -> None:
    for acting_role in Role:
        client = sign_in_as(client_factory, ROLE_EMAILS[acting_role])
        add_probe_routes(client)

        for required_role in Role:
            path = f"/api/organizations/{world.harbor_id}/probe/{required_role.value}"
            status_code = client.get(path).status_code

            expected = 200 if acting_role is required_role else 403
            assert status_code == expected, (
                f"{acting_role.value} on a {required_role.value}-only endpoint: "
                f"got {status_code}, expected {expected}"
            )


def test_an_endpoint_can_allow_several_roles(client_factory: ClientFactory, world: World) -> None:
    for role in Role:
        client = sign_in_as(client_factory, ROLE_EMAILS[role])
        add_probe_routes(client)

        path = f"/api/organizations/{world.harbor_id}/probe/manager-or-administrator"
        status_code = client.get(path).status_code

        expected = 200 if role in {Role.MANAGER, Role.ADMINISTRATOR} else 403
        assert status_code == expected, f"{role.value} got {status_code}, expected {expected}"


def test_role_checks_apply_before_any_organization_data_is_returned(
    client_factory: ClientFactory, world: World
) -> None:
    resident = sign_in_as(client_factory, ROLE_EMAILS[Role.RESIDENT])

    response = resident.get(f"/api/organizations/{world.harbor_id}/activity")

    assert response.status_code == 403
    assert response.json() == {"detail": "You do not have permission to do this"}


def test_require_roles_needs_at_least_one_role() -> None:
    with pytest.raises(ValueError):
        require_roles()


# --- Property scope ---------------------------------------------------------------------


def test_property_scope_allows_only_listed_properties() -> None:
    allowed, other = uuid.uuid4(), uuid.uuid4()

    limited = PropertyScope.limited_to([allowed])

    assert limited.allows(allowed)
    assert not limited.allows(other)
    assert PropertyScope.everything().allows(other)
    assert not PropertyScope.limited_to([]).allows(other)


def test_only_administrators_are_unrestricted_until_properties_exist(
    client_factory: ClientFactory, world: World
) -> None:
    for role in Role:
        client = sign_in_as(client_factory, ROLE_EMAILS[role])
        add_probe_routes(client)

        response = client.get(f"/api/organizations/{world.harbor_id}/probe/scope")

        assert response.json() == {"unrestricted": role is Role.ADMINISTRATOR}
