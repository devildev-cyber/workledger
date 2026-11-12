import re
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.api.deps import CSRF_HEADER_NAME, SESSION_COOKIE_NAME
from app.core.clock import utc_now
from app.core.config import Settings
from app.core.mail import EmailMessage, MemoryEmailSender
from app.core.security import verify_password
from app.models import ActivityEvent, EventType, Invitation, Organization, Role, User
from app.services.organizations import add_membership, create_organization
from app.services.users import create_user

PASSWORD = "correct horse battery staple"
ClientFactory = Callable[[Settings | None], TestClient]

ADMIN = "admin@harbor.example"
MANAGER = "manager@harbor.example"
OTHER_MANAGER = "manager2@harbor.example"
RESIDENT = "resident@harbor.example"
CONTRACTOR = "contractor@harbor.example"
OWNER = "owner@harbor.example"
ELM_ADMIN = "admin@elm.example"
NEWCOMER = "newcomer@example.com"


@dataclass(frozen=True)
class World:
    harbor_id: uuid.UUID
    elm_id: uuid.UUID


@pytest.fixture
def world(db_session: Session) -> World:
    harbor = create_organization(db_session, name="Harbor", actor=None)
    elm = create_organization(db_session, name="Elm Street", actor=None)
    members = [
        (harbor, ADMIN, Role.ADMINISTRATOR),
        (harbor, MANAGER, Role.MANAGER),
        (harbor, OTHER_MANAGER, Role.MANAGER),
        (harbor, RESIDENT, Role.RESIDENT),
        (harbor, CONTRACTOR, Role.CONTRACTOR),
        (harbor, OWNER, Role.PROPERTY_OWNER),
        (elm, ELM_ADMIN, Role.ADMINISTRATOR),
    ]
    for organization, email, role in members:
        user = create_user(db_session, email=email, full_name=email, password=PASSWORD)
        add_membership(db_session, organization=organization, user=user, roles=[role], actor=None)
    db_session.commit()
    return World(harbor_id=harbor.id, elm_id=elm.id)


class SignedInClient:
    """A signed-in browser: a client plus the CSRF token needed for changes."""

    def __init__(self, client: TestClient, csrf_token: str) -> None:
        self.client = client
        self.headers = {CSRF_HEADER_NAME: csrf_token}

    def get(self, path: str) -> Any:
        return self.client.get(path)

    def post(self, path: str, **kwargs: Any) -> Any:
        return self.client.post(path, headers=self.headers, **kwargs)

    def delete(self, path: str) -> Any:
        return self.client.delete(path, headers=self.headers)


def sign_in_as(client_factory: ClientFactory, email: str) -> SignedInClient:
    client = client_factory(None)
    response = client.post("/api/auth/sign-in", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200
    return SignedInClient(client, response.json()["csrf_token"])


def invite(
    session: SignedInClient, organization_id: uuid.UUID, email: str = NEWCOMER, *roles: Role
) -> Any:
    roles = roles or (Role.RESIDENT,)
    return session.post(
        f"/api/organizations/{organization_id}/invitations",
        json={"email": email, "roles": [role.value for role in roles]},
    )


def token_from(message: EmailMessage) -> str:
    match = re.search(r"#token=([\w-]+)", message.body)
    assert match, message.body
    return match.group(1)


def latest_token(outbox: MemoryEmailSender) -> str:
    return token_from(outbox.sent[-1])


def invitation_count(db: Session) -> int:
    return len(db.scalars(select(Invitation)).all())


# --- Creating invitations ---------------------------------------------------------------


def test_administrator_invites_by_email(
    client_factory: ClientFactory, world: World, outbox: MemoryEmailSender, db_session: Session
) -> None:
    admin = sign_in_as(client_factory, ADMIN)

    response = invite(admin, world.harbor_id, " Newcomer@Example.com ", Role.MANAGER, Role.RESIDENT)

    assert response.status_code == 201
    body = response.json()
    assert body["email"] == NEWCOMER
    assert body["roles"] == ["manager", "resident"]
    assert body["status"] == "pending"
    assert body["invited_by_name"] == ADMIN
    assert "token" not in response.text

    [message] = outbox.sent
    assert message.to == NEWCOMER
    assert "Harbor" in message.subject
    assert "http://localhost:5173/invitations/accept#token=" in message.body

    stored = db_session.scalars(select(Invitation)).one()
    assert latest_token(outbox) not in stored.token_hash
    assert stored.expires_at - stored.created_at == timedelta(days=7)


def test_managers_can_only_invite_residents_and_contractors(
    client_factory: ClientFactory, world: World, outbox: MemoryEmailSender, db_session: Session
) -> None:
    manager = sign_in_as(client_factory, MANAGER)

    assert invite(manager, world.harbor_id, "a@example.com", Role.RESIDENT).status_code == 201
    assert invite(manager, world.harbor_id, "b@example.com", Role.CONTRACTOR).status_code == 201
    assert len(outbox.sent) == 2

    for forbidden in (Role.ADMINISTRATOR, Role.MANAGER, Role.PROPERTY_OWNER):
        response = invite(manager, world.harbor_id, "c@example.com", Role.RESIDENT, forbidden)
        assert response.status_code == 403, forbidden

    assert len(outbox.sent) == 2
    assert invitation_count(db_session) == 2


@pytest.mark.parametrize("email", [RESIDENT, CONTRACTOR, OWNER])
def test_other_roles_cannot_invite_or_list(
    client_factory: ClientFactory, world: World, email: str
) -> None:
    session = sign_in_as(client_factory, email)

    assert invite(session, world.harbor_id).status_code == 403
    assert session.get(f"/api/organizations/{world.harbor_id}/invitations").status_code == 403


def test_other_organizations_cannot_be_reached(client_factory: ClientFactory, world: World) -> None:
    elm_admin = sign_in_as(client_factory, ELM_ADMIN)

    assert invite(elm_admin, world.harbor_id).status_code == 404
    assert elm_admin.get(f"/api/organizations/{world.harbor_id}/invitations").status_code == 404


def test_signed_out_and_missing_csrf_are_rejected(
    client: TestClient, client_factory: ClientFactory, world: World
) -> None:
    url = f"/api/organizations/{world.harbor_id}/invitations"
    payload = {"email": NEWCOMER, "roles": ["resident"]}
    assert client.post(url, json=payload).status_code == 401

    admin = sign_in_as(client_factory, ADMIN)
    assert admin.client.post(url, json=payload).status_code == 403


def test_inviting_an_existing_member_is_a_conflict(
    client_factory: ClientFactory, world: World, outbox: MemoryEmailSender
) -> None:
    admin = sign_in_as(client_factory, ADMIN)

    response = invite(admin, world.harbor_id, RESIDENT.upper(), Role.RESIDENT)

    assert response.status_code == 409
    assert outbox.sent == []


@pytest.mark.parametrize(
    "payload",
    [
        {"email": NEWCOMER, "roles": []},
        {"email": NEWCOMER, "roles": ["superuser"]},
        {"email": "not-an-email", "roles": ["resident"]},
        {"email": "two words@example.com", "roles": ["resident"]},
    ],
)
def test_invalid_requests_are_rejected(
    client_factory: ClientFactory, world: World, payload: dict[str, object]
) -> None:
    admin = sign_in_as(client_factory, ADMIN)

    response = admin.post(f"/api/organizations/{world.harbor_id}/invitations", json=payload)

    assert response.status_code == 422


def test_a_new_invitation_replaces_the_previous_one(
    client_factory: ClientFactory, world: World, outbox: MemoryEmailSender
) -> None:
    admin = sign_in_as(client_factory, ADMIN)
    invite(admin, world.harbor_id)
    first_token = latest_token(outbox)
    invite(admin, world.harbor_id)
    second_token = latest_token(outbox)
    public = client_factory(None)

    assert public.post("/api/invitations/preview", json={"token": first_token}).status_code == 404
    assert public.post("/api/invitations/preview", json={"token": second_token}).status_code == 200
    statuses = [
        i["status"] for i in admin.get(f"/api/organizations/{world.harbor_id}/invitations").json()
    ]
    assert sorted(statuses) == ["pending", "revoked"]


def test_creating_an_invitation_records_an_event(
    client_factory: ClientFactory, world: World, db_session: Session
) -> None:
    invite(sign_in_as(client_factory, ADMIN), world.harbor_id, NEWCOMER, Role.CONTRACTOR)

    event = db_session.scalars(
        select(ActivityEvent).where(ActivityEvent.event_type == EventType.INVITATION_CREATED)
    ).one()
    assert event.organization_id == world.harbor_id
    assert event.after == {"email": NEWCOMER, "roles": ["contractor"]}
    assert event.actor_user_id is not None


# --- Listing and revoking ---------------------------------------------------------------


def test_administrators_see_all_invitations_and_managers_only_their_own(
    client_factory: ClientFactory, world: World
) -> None:
    manager = sign_in_as(client_factory, MANAGER)
    other_manager = sign_in_as(client_factory, OTHER_MANAGER)
    admin = sign_in_as(client_factory, ADMIN)
    invite(manager, world.harbor_id, "one@example.com")
    invite(other_manager, world.harbor_id, "two@example.com")
    url = f"/api/organizations/{world.harbor_id}/invitations"

    assert {i["email"] for i in admin.get(url).json()} == {"one@example.com", "two@example.com"}
    assert {i["email"] for i in manager.get(url).json()} == {"one@example.com"}


def test_revoking_makes_the_link_useless(
    client_factory: ClientFactory, world: World, outbox: MemoryEmailSender
) -> None:
    admin = sign_in_as(client_factory, ADMIN)
    invitation_id = invite(admin, world.harbor_id).json()["id"]
    token = latest_token(outbox)

    response = admin.delete(f"/api/organizations/{world.harbor_id}/invitations/{invitation_id}")

    assert response.status_code == 204
    public = client_factory(None)
    assert public.post("/api/invitations/preview", json={"token": token}).status_code == 404
    again = admin.delete(f"/api/organizations/{world.harbor_id}/invitations/{invitation_id}")
    assert again.status_code == 409


def test_managers_can_revoke_only_their_own_invitations(
    client_factory: ClientFactory, world: World
) -> None:
    manager = sign_in_as(client_factory, MANAGER)
    other_manager = sign_in_as(client_factory, OTHER_MANAGER)
    invitation_id = invite(manager, world.harbor_id).json()["id"]
    url = f"/api/organizations/{world.harbor_id}/invitations/{invitation_id}"

    assert other_manager.delete(url).status_code == 404
    assert manager.delete(url).status_code == 204


def test_invitations_of_other_organizations_look_missing(
    client_factory: ClientFactory, world: World
) -> None:
    admin = sign_in_as(client_factory, ADMIN)
    elm_admin = sign_in_as(client_factory, ELM_ADMIN)
    invitation_id = invite(admin, world.harbor_id).json()["id"]

    foreign = elm_admin.delete(f"/api/organizations/{world.elm_id}/invitations/{invitation_id}")
    missing = elm_admin.delete(f"/api/organizations/{world.elm_id}/invitations/{uuid.uuid4()}")

    assert foreign.status_code == missing.status_code == 404
    assert foreign.json() == missing.json()


# --- Accepting: new people --------------------------------------------------------------


def test_preview_describes_the_invitation(
    client_factory: ClientFactory, world: World, outbox: MemoryEmailSender
) -> None:
    invite(sign_in_as(client_factory, ADMIN), world.harbor_id, NEWCOMER, Role.CONTRACTOR)

    response = client_factory(None).post(
        "/api/invitations/preview", json={"token": latest_token(outbox)}
    )

    assert response.json() == {
        "organization_id": str(world.harbor_id),
        "organization_name": "Harbor",
        "email": NEWCOMER,
        "roles": ["contractor"],
        "has_account": False,
    }


def test_unknown_tokens_are_not_found(client: TestClient, world: World) -> None:
    for path in ("preview", "accept"):
        response = client.post(f"/api/invitations/{path}", json={"token": "made-up"})

        assert response.status_code == 404
        assert "not valid" in response.json()["detail"]


def test_a_new_person_creates_their_account_and_is_signed_in(
    client_factory: ClientFactory, world: World, outbox: MemoryEmailSender, db_session: Session
) -> None:
    invite(sign_in_as(client_factory, ADMIN), world.harbor_id, NEWCOMER, Role.RESIDENT)
    browser = client_factory(None)

    response = browser.post(
        "/api/invitations/accept",
        json={"token": latest_token(outbox), "full_name": "Nia Newcomer", "password": PASSWORD},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["user"]["email"] == NEWCOMER
    assert body["user"]["full_name"] == "Nia Newcomer"
    assert [m["organization_name"] for m in body["user"]["memberships"]] == ["Harbor"]
    assert body["user"]["memberships"][0]["roles"] == ["resident"]
    assert SESSION_COOKIE_NAME in response.headers["set-cookie"]
    assert browser.get("/api/auth/me").status_code == 200

    user = db_session.scalars(select(User).where(User.email == NEWCOMER)).one()
    assert verify_password(user.password_hash, PASSWORD)


def test_an_invitation_works_only_once(
    client_factory: ClientFactory, world: World, outbox: MemoryEmailSender
) -> None:
    invite(sign_in_as(client_factory, ADMIN), world.harbor_id)
    token = latest_token(outbox)
    payload = {"token": token, "full_name": "Nia", "password": PASSWORD}

    assert client_factory(None).post("/api/invitations/accept", json=payload).status_code == 200
    assert client_factory(None).post("/api/invitations/accept", json=payload).status_code == 404
    assert (
        client_factory(None).post("/api/invitations/preview", json={"token": token}).status_code
        == 404
    )


@pytest.mark.parametrize(
    "extra",
    [{}, {"full_name": "Nia"}, {"password": PASSWORD}, {"full_name": "  ", "password": PASSWORD}],
)
def test_a_new_person_must_give_a_name_and_password(
    client_factory: ClientFactory,
    world: World,
    outbox: MemoryEmailSender,
    db_session: Session,
    extra: dict[str, str],
) -> None:
    invite(sign_in_as(client_factory, ADMIN), world.harbor_id)
    token = latest_token(outbox)

    response = client_factory(None).post("/api/invitations/accept", json={"token": token, **extra})

    assert response.status_code == 422
    assert db_session.scalars(select(User).where(User.email == NEWCOMER)).all() == []


def test_a_weak_password_leaves_the_invitation_usable(
    client_factory: ClientFactory, world: World, outbox: MemoryEmailSender
) -> None:
    invite(sign_in_as(client_factory, ADMIN), world.harbor_id)
    token = latest_token(outbox)
    browser = client_factory(None)

    weak = browser.post(
        "/api/invitations/accept", json={"token": token, "full_name": "Nia", "password": "short"}
    )
    retry = browser.post(
        "/api/invitations/accept", json={"token": token, "full_name": "Nia", "password": PASSWORD}
    )

    assert weak.status_code == 422
    assert retry.status_code == 200


def test_expired_invitations_cannot_be_used(
    client_factory: ClientFactory, world: World, outbox: MemoryEmailSender, db_session: Session
) -> None:
    admin = sign_in_as(client_factory, ADMIN)
    invite(admin, world.harbor_id)
    token = latest_token(outbox)
    db_session.execute(update(Invitation).values(expires_at=utc_now() - timedelta(minutes=1)))
    db_session.commit()
    public = client_factory(None)

    assert public.post("/api/invitations/preview", json={"token": token}).status_code == 404
    accept = {"token": token, "full_name": "Nia", "password": PASSWORD}
    assert public.post("/api/invitations/accept", json=accept).status_code == 404
    [listed] = admin.get(f"/api/organizations/{world.harbor_id}/invitations").json()
    assert listed["status"] == "expired"


def test_accepting_records_events_attributed_to_the_new_member(
    client_factory: ClientFactory, world: World, outbox: MemoryEmailSender, db_session: Session
) -> None:
    invite(sign_in_as(client_factory, ADMIN), world.harbor_id)
    accept = {"token": latest_token(outbox), "full_name": "Nia", "password": PASSWORD}
    client_factory(None).post("/api/invitations/accept", json=accept)

    newcomer = db_session.scalars(select(User).where(User.email == NEWCOMER)).one()
    events = db_session.scalars(
        select(ActivityEvent).where(ActivityEvent.actor_user_id == newcomer.id)
    ).all()

    assert {event.event_type for event in events} == {
        EventType.INVITATION_ACCEPTED,
        EventType.MEMBERSHIP_CREATED,
    }


# --- Accepting: people who already have an account -------------------------------------


@pytest.fixture
def existing_account(db_session: Session) -> None:
    create_user(db_session, email=NEWCOMER, full_name="Eve Existing", password=PASSWORD)
    db_session.commit()


def test_preview_tells_the_app_that_an_account_exists(
    client_factory: ClientFactory, world: World, outbox: MemoryEmailSender, existing_account: None
) -> None:
    invite(sign_in_as(client_factory, ADMIN), world.harbor_id)

    response = client_factory(None).post(
        "/api/invitations/preview", json={"token": latest_token(outbox)}
    )

    assert response.json()["has_account"] is True


def test_an_existing_account_must_be_signed_in_to_accept(
    client_factory: ClientFactory, world: World, outbox: MemoryEmailSender, existing_account: None
) -> None:
    invite(sign_in_as(client_factory, ADMIN), world.harbor_id)
    token = latest_token(outbox)

    response = client_factory(None).post("/api/invitations/accept", json={"token": token})

    assert response.status_code == 401
    assert (
        client_factory(None).post("/api/invitations/preview", json={"token": token}).status_code
        == 200
    )


def test_a_different_signed_in_account_cannot_accept(
    client_factory: ClientFactory, world: World, outbox: MemoryEmailSender, existing_account: None
) -> None:
    invite(sign_in_as(client_factory, ADMIN), world.harbor_id)
    token = latest_token(outbox)
    intruder = sign_in_as(client_factory, RESIDENT)

    response = intruder.post("/api/invitations/accept", json={"token": token})

    assert response.status_code == 403


def test_signed_in_acceptance_needs_the_csrf_token(
    client_factory: ClientFactory, world: World, outbox: MemoryEmailSender, existing_account: None
) -> None:
    invite(sign_in_as(client_factory, ADMIN), world.harbor_id)
    token = latest_token(outbox)
    browser = client_factory(None)
    browser.post("/api/auth/sign-in", json={"email": NEWCOMER, "password": PASSWORD})

    response = browser.post("/api/invitations/accept", json={"token": token})

    assert response.status_code == 403


def test_the_account_owner_joins_a_second_organization(
    client_factory: ClientFactory,
    world: World,
    outbox: MemoryEmailSender,
    db_session: Session,
    existing_account: None,
) -> None:
    elm_admin = sign_in_as(client_factory, ELM_ADMIN)
    invite(elm_admin, world.elm_id, NEWCOMER, Role.CONTRACTOR)
    eve = sign_in_as(client_factory, NEWCOMER)
    invite(sign_in_as(client_factory, ADMIN), world.harbor_id, NEWCOMER, Role.CONTRACTOR)

    response = eve.post("/api/invitations/accept", json={"token": latest_token(outbox)})

    assert response.status_code == 200
    memberships = response.json()["user"]["memberships"]
    assert [m["organization_name"] for m in memberships] == ["Harbor"]
    assert len(db_session.scalars(select(User).where(User.email == NEWCOMER)).all()) == 1

    second = eve.post("/api/invitations/accept", json={"token": token_from(outbox.sent[0])})
    assert [m["organization_name"] for m in second.json()["user"]["memberships"]] == [
        "Elm Street",
        "Harbor",
    ]


def test_someone_who_became_a_member_another_way_gets_a_conflict_and_can_retry_later(
    client_factory: ClientFactory,
    world: World,
    outbox: MemoryEmailSender,
    db_session: Session,
    existing_account: None,
) -> None:
    invite(sign_in_as(client_factory, ADMIN), world.harbor_id)
    token = latest_token(outbox)
    user = db_session.scalars(select(User).where(User.email == NEWCOMER)).one()
    harbor = db_session.get(Organization, world.harbor_id)
    assert harbor is not None
    add_membership(db_session, organization=harbor, user=user, roles=[Role.RESIDENT], actor=None)
    db_session.commit()
    eve = sign_in_as(client_factory, NEWCOMER)

    response = eve.post("/api/invitations/accept", json={"token": token})

    assert response.status_code == 409
    preview = client_factory(None).post("/api/invitations/preview", json={"token": token})
    assert preview.status_code == 200
