import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from support import PASSWORD, ClientFactory, SignedInClient, sign_in_as

from app.models import ActivityEvent, EventType, Role
from app.services.organizations import add_membership, create_organization
from app.services.users import create_user

ADMIN = "admin@harbor.example"
MANAGER = "manager@harbor.example"
OTHER_MANAGER = "manager2@harbor.example"
RESIDENT = "resident@harbor.example"
CONTRACTOR = "contractor@harbor.example"
OWNER = "owner@harbor.example"
ELM_ADMIN = "admin@elm.example"

TODAY = datetime.now(UTC).date()


@dataclass(frozen=True)
class World:
    harbor_id: uuid.UUID
    elm_id: uuid.UUID

    @property
    def base(self) -> str:
        return f"/api/organizations/{self.harbor_id}"


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


@pytest.fixture
def admin(client_factory: ClientFactory, world: World) -> SignedInClient:
    return sign_in_as(client_factory, ADMIN)


# --- Helpers that build records through the API -----------------------------------------


def make_property(admin: SignedInClient, world: World, name: str = "Maple Court", **extra: Any):
    response = admin.post(f"{world.base}/properties", json={"name": name, **extra})
    assert response.status_code == 201, response.text
    return response.json()


def make_building(admin: SignedInClient, world: World, property_id: str, name: str = "A"):
    response = admin.post(f"{world.base}/properties/{property_id}/buildings", json={"name": name})
    assert response.status_code == 201, response.text
    return response.json()


def make_unit(
    admin: SignedInClient,
    world: World,
    property_id: str,
    label: str = "1A",
    building_id: str | None = None,
):
    response = admin.post(
        f"{world.base}/properties/{property_id}/units",
        json={"label": label, "building_id": building_id},
    )
    assert response.status_code == 201, response.text
    return response.json()


def make_resident(admin: SignedInClient, world: World, name: str = "Rae Resident", **extra: Any):
    response = admin.post(f"{world.base}/residents", json={"full_name": name, **extra})
    assert response.status_code == 201, response.text
    return response.json()


def move_in(
    admin: SignedInClient,
    world: World,
    unit_id: str,
    resident_id: str,
    on: date = TODAY - timedelta(days=30),
):
    response = admin.post(
        f"{world.base}/tenancies",
        json={"unit_id": unit_id, "resident_id": resident_id, "move_in_date": on.isoformat()},
    )
    assert response.status_code == 201, response.text
    return response.json()


def assign(admin: SignedInClient, world: World, property_id: str, *emails: str, db: Session):
    from app.models import Membership, User

    ids = [
        str(
            db.scalars(
                select(Membership.id)
                .join(Membership.user)
                .where(Membership.organization_id == world.harbor_id, User.email == email)
            ).one()
        )
        for email in emails
    ]
    response = admin.put(
        f"{world.base}/properties/{property_id}/managers", json={"membership_ids": ids}
    )
    assert response.status_code == 200, response.text
    return response.json()


def events(db: Session, event_type: EventType) -> list[ActivityEvent]:
    db.expire_all()
    return list(db.scalars(select(ActivityEvent).where(ActivityEvent.event_type == event_type)))


# --- Properties -------------------------------------------------------------------------


def test_administrator_creates_a_property_with_its_settings(
    admin: SignedInClient, world: World
) -> None:
    response = admin.post(
        f"{world.base}/properties",
        json={
            "name": "  Maple Court ",
            "street": "12 Maple Street",
            "city": "Portland",
            "region": "OR",
            "postal_code": "97201",
            "currency": "eur",
            "approval_threshold_cents": 50000,
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Maple Court"
    assert body["currency"] == "EUR"
    assert body["approval_threshold_cents"] == 50000
    assert body["unit_count"] == 0
    assert body["buildings"] == []
    assert admin.get(f"{world.base}/properties").json()[0]["id"] == body["id"]


def test_new_properties_default_to_dollars_and_no_threshold(
    admin: SignedInClient, world: World
) -> None:
    body = make_property(admin, world)

    assert body["currency"] == "USD"
    assert body["approval_threshold_cents"] is None


@pytest.mark.parametrize(
    "bad",
    [
        {"name": "   "},
        {"name": "x" * 201},
        {"name": "Ok", "currency": "DOLLARS"},
        {"name": "Ok", "currency": "U$D"},
        {"name": "Ok", "approval_threshold_cents": -1},
    ],
)
def test_invalid_properties_are_refused(admin: SignedInClient, world: World, bad: dict) -> None:
    assert admin.post(f"{world.base}/properties", json=bad).status_code == 422


def test_property_names_are_unique_ignoring_case(admin: SignedInClient, world: World) -> None:
    make_property(admin, world, "Maple Court")
    other = make_property(admin, world, "Oak Terrace")

    assert admin.post(f"{world.base}/properties", json={"name": "maple court"}).status_code == 409
    renamed = admin.put(f"{world.base}/properties/{other['id']}", json={"name": "MAPLE COURT"})
    assert renamed.status_code == 409


def test_two_organizations_may_use_the_same_property_name(
    admin: SignedInClient, client_factory: ClientFactory, world: World
) -> None:
    make_property(admin, world, "Maple Court")
    elm = sign_in_as(client_factory, ELM_ADMIN)

    response = elm.post(
        f"/api/organizations/{world.elm_id}/properties", json={"name": "Maple Court"}
    )

    assert response.status_code == 201


def test_updating_a_property_records_only_what_changed(
    admin: SignedInClient, world: World, db_session: Session
) -> None:
    created = make_property(admin, world, city="Portland", currency="USD")

    response = admin.put(
        f"{world.base}/properties/{created['id']}",
        json={"name": "Maple Court", "city": "Salem", "currency": "USD"},
    )

    assert response.status_code == 200
    assert response.json()["city"] == "Salem"
    [event] = events(db_session, EventType.PROPERTY_UPDATED)
    assert event.before == {"city": "Portland"}
    assert event.after == {"city": "Salem"}


def test_saving_a_property_without_changes_records_nothing(
    admin: SignedInClient, world: World, db_session: Session
) -> None:
    created = make_property(admin, world)

    admin.put(f"{world.base}/properties/{created['id']}", json={"name": "Maple Court"})

    assert events(db_session, EventType.PROPERTY_UPDATED) == []


def test_creating_a_property_is_recorded(
    admin: SignedInClient, world: World, db_session: Session
) -> None:
    created = make_property(admin, world, approval_threshold_cents=1000)

    [event] = events(db_session, EventType.PROPERTY_CREATED)
    assert event.organization_id == world.harbor_id
    assert str(event.subject_id) == created["id"]
    assert event.after is not None and event.after["approval_threshold_cents"] == 1000


# --- Who may see and change properties --------------------------------------------------


def test_only_administrators_change_the_directory(
    client_factory: ClientFactory, world: World, admin: SignedInClient
) -> None:
    created = make_property(admin, world)
    manager = sign_in_as(client_factory, MANAGER)

    assert manager.post(f"{world.base}/properties", json={"name": "New"}).status_code == 403
    assert (
        manager.put(f"{world.base}/properties/{created['id']}", json={"name": "New"}).status_code
        == 403
    )
    assert manager.post(f"{world.base}/residents", json={"full_name": "X"}).status_code == 403
    assert (
        manager.post(
            f"{world.base}/properties/{created['id']}/units", json={"label": "1"}
        ).status_code
        == 403
    )


@pytest.mark.parametrize("email", [RESIDENT, CONTRACTOR, OWNER])
def test_other_roles_have_no_access_to_the_directory(
    client_factory: ClientFactory, world: World, admin: SignedInClient, email: str
) -> None:
    created = make_property(admin, world)
    person = sign_in_as(client_factory, email)

    for path in ("/properties", f"/properties/{created['id']}", "/residents"):
        assert person.get(f"{world.base}{path}").status_code == 403


def test_managers_see_only_the_properties_assigned_to_them(
    client_factory: ClientFactory, world: World, admin: SignedInClient, db_session: Session
) -> None:
    mine = make_property(admin, world, "Maple Court")
    other = make_property(admin, world, "Oak Terrace")
    assign(admin, world, mine["id"], MANAGER, db=db_session)
    manager = sign_in_as(client_factory, MANAGER)

    listed = manager.get(f"{world.base}/properties").json()

    assert [item["name"] for item in listed] == ["Maple Court"]
    assert manager.get(f"{world.base}/properties/{mine['id']}").status_code == 200
    assert manager.get(f"{world.base}/properties/{other['id']}").status_code == 404
    assert manager.get(f"{world.base}/properties/{other['id']}/units").status_code == 404
    assert [p["name"] for p in admin.get(f"{world.base}/properties").json()] == [
        "Maple Court",
        "Oak Terrace",
    ]


def test_an_unassigned_manager_sees_nothing(
    client_factory: ClientFactory, world: World, admin: SignedInClient
) -> None:
    make_property(admin, world)
    manager = sign_in_as(client_factory, OTHER_MANAGER)

    assert manager.get(f"{world.base}/properties").json() == []


def test_other_organizations_cannot_reach_a_property(
    client_factory: ClientFactory, world: World, admin: SignedInClient
) -> None:
    created = make_property(admin, world)
    elm = sign_in_as(client_factory, ELM_ADMIN)

    assert elm.get(f"{world.base}/properties").status_code == 404
    through_own = f"/api/organizations/{world.elm_id}/properties/{created['id']}"
    assert elm.get(through_own).status_code == 404
    assert elm.put(through_own, json={"name": "Hijacked"}).status_code == 404
    assert elm.get(f"/api/organizations/{world.elm_id}/properties").json() == []


# --- Buildings and units ----------------------------------------------------------------


def test_buildings_belong_to_a_property_and_names_are_unique_within_it(
    admin: SignedInClient, world: World
) -> None:
    first = make_property(admin, world, "Maple Court")
    second = make_property(admin, world, "Oak Terrace")
    building = make_building(admin, world, first["id"], "North")

    duplicate = admin.post(
        f"{world.base}/properties/{first['id']}/buildings", json={"name": "north"}
    )
    elsewhere = admin.post(
        f"{world.base}/properties/{second['id']}/buildings", json={"name": "North"}
    )
    renamed = admin.put(
        f"{world.base}/properties/{first['id']}/buildings/{building['id']}",
        json={"name": "South"},
    )

    assert duplicate.status_code == 409
    assert elsewhere.status_code == 201
    assert renamed.json()["name"] == "South"
    listed = admin.get(f"{world.base}/properties/{first['id']}").json()
    assert [b["name"] for b in listed["buildings"]] == ["South"]


def test_units_are_listed_in_natural_order_with_their_current_residents(
    admin: SignedInClient, world: World
) -> None:
    created = make_property(admin, world)
    for label in ("10", "2", "1B", "1A"):
        make_unit(admin, world, created["id"], label)
    unit_two = next(
        u
        for u in admin.get(f"{world.base}/properties/{created['id']}/units").json()
        if u["label"] == "2"
    )
    resident = make_resident(admin, world, "Rae Resident")
    move_in(admin, world, unit_two["id"], resident["id"])

    units = admin.get(f"{world.base}/properties/{created['id']}/units").json()

    assert [unit["label"] for unit in units] == ["1A", "1B", "2", "10"]
    assert units[2]["current_residents"] == [{"id": resident["id"], "full_name": "Rae Resident"}]
    assert admin.get(f"{world.base}/properties/{created['id']}").json()["unit_count"] == 4


def test_unit_labels_are_unique_within_a_building_only(admin: SignedInClient, world: World) -> None:
    created = make_property(admin, world)
    north = make_building(admin, world, created["id"], "North")
    south = make_building(admin, world, created["id"], "South")
    make_unit(admin, world, created["id"], "1", north["id"])
    url = f"{world.base}/properties/{created['id']}/units"

    assert admin.post(url, json={"label": "1", "building_id": south["id"]}).status_code == 201
    assert admin.post(url, json={"label": "1"}).status_code == 201
    assert admin.post(url, json={"label": "1", "building_id": north["id"]}).status_code == 409
    assert admin.post(url, json={"label": " 1 "}).status_code == 409


def test_a_unit_cannot_use_a_building_from_another_property(
    admin: SignedInClient, world: World
) -> None:
    first = make_property(admin, world, "Maple Court")
    second = make_property(admin, world, "Oak Terrace")
    foreign = make_building(admin, world, second["id"], "Tower")

    response = admin.post(
        f"{world.base}/properties/{first['id']}/units",
        json={"label": "1", "building_id": foreign["id"]},
    )

    assert response.status_code == 404


def test_a_unit_can_be_renamed_and_moved_between_buildings(
    admin: SignedInClient, world: World, db_session: Session
) -> None:
    created = make_property(admin, world)
    north = make_building(admin, world, created["id"], "North")
    unit = make_unit(admin, world, created["id"], "1A")

    response = admin.put(
        f"{world.base}/properties/{created['id']}/units/{unit['id']}",
        json={"label": "1B", "building_id": north["id"]},
    )

    assert response.status_code == 200
    assert response.json()["label"] == "1B"
    assert response.json()["building_id"] == north["id"]
    [event] = events(db_session, EventType.UNIT_UPDATED)
    assert event.before == {"label": "1A", "building_id": None}
    assert event.after == {"label": "1B", "building_id": north["id"]}


def test_a_unit_is_only_reachable_through_its_own_property(
    admin: SignedInClient, world: World
) -> None:
    first = make_property(admin, world, "Maple Court")
    second = make_property(admin, world, "Oak Terrace")
    unit = make_unit(admin, world, first["id"])

    response = admin.put(
        f"{world.base}/properties/{second['id']}/units/{unit['id']}", json={"label": "Hijacked"}
    )

    assert response.status_code == 404


# --- Managers of a property -------------------------------------------------------------


def test_administrator_assigns_managers_and_they_gain_access_at_once(
    client_factory: ClientFactory, world: World, admin: SignedInClient, db_session: Session
) -> None:
    created = make_property(admin, world)
    manager = sign_in_as(client_factory, MANAGER)
    assert manager.get(f"{world.base}/properties/{created['id']}").status_code == 404

    listed = assign(admin, world, created["id"], MANAGER, db=db_session)

    assert {m["email"]: m["assigned"] for m in listed} == {MANAGER: True, OTHER_MANAGER: False}
    assert manager.get(f"{world.base}/properties/{created['id']}").status_code == 200
    [event] = events(db_session, EventType.PROPERTY_MANAGERS_CHANGED)
    assert event.before == {"membership_ids": []}
    assert event.after is not None and len(event.after["membership_ids"]) == 1


def test_unassigning_removes_access_and_unchanged_saves_record_nothing(
    client_factory: ClientFactory, world: World, admin: SignedInClient, db_session: Session
) -> None:
    created = make_property(admin, world)
    assign(admin, world, created["id"], MANAGER, db=db_session)
    assign(admin, world, created["id"], MANAGER, db=db_session)
    manager = sign_in_as(client_factory, MANAGER)

    assign(admin, world, created["id"], db=db_session)

    assert manager.get(f"{world.base}/properties/{created['id']}").status_code == 404
    assert len(events(db_session, EventType.PROPERTY_MANAGERS_CHANGED)) == 2


def test_only_managers_can_be_assigned(
    world: World, admin: SignedInClient, db_session: Session
) -> None:
    from app.models import Membership, User

    created = make_property(admin, world)
    resident_membership = db_session.scalars(
        select(Membership.id)
        .join(Membership.user)
        .where(Membership.organization_id == world.harbor_id, User.email == RESIDENT)
    ).one()

    response = admin.put(
        f"{world.base}/properties/{created['id']}/managers",
        json={"membership_ids": [str(resident_membership)]},
    )

    assert response.status_code == 422
    assert (
        admin.put(
            f"{world.base}/properties/{created['id']}/managers",
            json={"membership_ids": [str(uuid.uuid4())]},
        ).status_code
        == 422
    )


def test_assignment_is_for_administrators_only(
    client_factory: ClientFactory, world: World, admin: SignedInClient
) -> None:
    created = make_property(admin, world)
    manager = sign_in_as(client_factory, MANAGER)

    assert manager.get(f"{world.base}/properties/{created['id']}/managers").status_code == 403
    assert (
        manager.put(
            f"{world.base}/properties/{created['id']}/managers", json={"membership_ids": []}
        ).status_code
        == 403
    )


def test_access_ends_when_someone_stops_being_a_manager(
    client_factory: ClientFactory, world: World, admin: SignedInClient, db_session: Session
) -> None:
    from app.models import Membership, User

    created = make_property(admin, world)
    assign(admin, world, created["id"], MANAGER, db=db_session)
    membership_id = db_session.scalars(
        select(Membership.id)
        .join(Membership.user)
        .where(Membership.organization_id == world.harbor_id, User.email == MANAGER)
    ).one()

    admin.put(
        f"{world.base}/members/{membership_id}/roles",
        json={"roles": ["resident"]},
    )
    admin.put(
        f"{world.base}/members/{membership_id}/roles",
        json={"roles": ["manager"]},
    )

    # Becoming a manager again does not bring the old assignments back.
    manager = sign_in_as(client_factory, MANAGER)
    assert manager.get(f"{world.base}/properties").json() == []


def test_removing_a_manager_clears_their_assignments(
    world: World, admin: SignedInClient, db_session: Session
) -> None:
    from app.models import Membership, PropertyAssignment, User

    created = make_property(admin, world)
    assign(admin, world, created["id"], MANAGER, db=db_session)
    membership_id = db_session.scalars(
        select(Membership.id)
        .join(Membership.user)
        .where(Membership.organization_id == world.harbor_id, User.email == MANAGER)
    ).one()

    assert admin.delete(f"{world.base}/members/{membership_id}").status_code == 204

    db_session.expire_all()
    assert db_session.scalars(select(PropertyAssignment)).all() == []


# --- Residents and move-ins -------------------------------------------------------------


def test_residents_are_created_with_private_contact_details(
    admin: SignedInClient, world: World
) -> None:
    body = make_resident(
        admin,
        world,
        email=" Rae@Example.com ",
        phone="555-0100",
        access_instructions="Gate code 4821, ring twice",
    )

    assert body["email"] == "rae@example.com"
    assert body["phone"] == "555-0100"
    assert body["access_instructions"] == "Gate code 4821, ring twice"
    assert body["has_account"] is False
    assert body["tenancies"] == []


def test_blank_contact_fields_are_stored_as_empty(admin: SignedInClient, world: World) -> None:
    body = make_resident(admin, world, email="  ", phone="", access_instructions=" ")

    assert (body["email"], body["phone"], body["access_instructions"]) == (None, None, None)


def test_residents_need_a_name_and_a_valid_email(admin: SignedInClient, world: World) -> None:
    url = f"{world.base}/residents"

    assert admin.post(url, json={"full_name": " "}).status_code == 422
    assert admin.post(url, json={"full_name": "Rae", "email": "not-an-email"}).status_code == 422


def test_activity_history_never_contains_contact_details(
    admin: SignedInClient, world: World, db_session: Session
) -> None:
    created = make_resident(
        admin, world, email="rae@example.com", phone="555-0100", access_instructions="Gate 4821"
    )
    admin.put(
        f"{world.base}/residents/{created['id']}",
        json={
            "full_name": "Rae Resident",
            "email": "rae@example.com",
            "phone": "555-0199",
            "access_instructions": "Gate 9999",
        },
    )

    history = admin.get(f"{world.base}/activity").text

    assert "resident.created" in history
    assert "resident.updated" in history
    for secret in ("rae@example.com", "555-0100", "555-0199", "Gate 4821", "Gate 9999"):
        assert secret not in history
    [updated] = events(db_session, EventType.RESIDENT_UPDATED)
    assert updated.after == {"changed": ["phone", "access_instructions"]}


def test_a_move_in_shows_on_the_unit_and_the_resident(admin: SignedInClient, world: World) -> None:
    created = make_property(admin, world)
    building = make_building(admin, world, created["id"], "North")
    unit = make_unit(admin, world, created["id"], "4B", building["id"])
    resident = make_resident(admin, world)

    tenancy = move_in(admin, world, unit["id"], resident["id"], TODAY - timedelta(days=10))

    assert tenancy["is_current"] is True
    assert tenancy["unit_label"] == "4B"
    assert tenancy["building_name"] == "North"
    assert tenancy["property_name"] == "Maple Court"
    loaded = admin.get(f"{world.base}/residents/{resident['id']}").json()
    assert [t["id"] for t in loaded["tenancies"]] == [tenancy["id"]]


def test_a_unit_can_have_several_residents_and_a_resident_several_units(
    admin: SignedInClient, world: World
) -> None:
    created = make_property(admin, world)
    one = make_unit(admin, world, created["id"], "1")
    two = make_unit(admin, world, created["id"], "2")
    rae = make_resident(admin, world, "Rae Resident")
    sam = make_resident(admin, world, "Sam Sharer")

    move_in(admin, world, one["id"], rae["id"])
    move_in(admin, world, one["id"], sam["id"])
    move_in(admin, world, two["id"], rae["id"])

    units = admin.get(f"{world.base}/properties/{created['id']}/units").json()
    assert [r["full_name"] for r in units[0]["current_residents"]] == [
        "Rae Resident",
        "Sam Sharer",
    ]
    assert [r["full_name"] for r in units[1]["current_residents"]] == ["Rae Resident"]


def test_the_same_person_cannot_move_into_a_unit_twice_at_once(
    admin: SignedInClient, world: World
) -> None:
    created = make_property(admin, world)
    unit = make_unit(admin, world, created["id"])
    resident = make_resident(admin, world)
    first = move_in(admin, world, unit["id"], resident["id"], TODAY - timedelta(days=60))

    repeat = admin.post(
        f"{world.base}/tenancies",
        json={
            "unit_id": unit["id"],
            "resident_id": resident["id"],
            "move_in_date": TODAY.isoformat(),
        },
    )
    assert repeat.status_code == 409

    ended = admin.post(
        f"{world.base}/tenancies/{first['id']}/end",
        json={"move_out_date": (TODAY - timedelta(days=5)).isoformat()},
    )
    assert ended.status_code == 200
    again = admin.post(
        f"{world.base}/tenancies",
        json={
            "unit_id": unit["id"],
            "resident_id": resident["id"],
            "move_in_date": TODAY.isoformat(),
        },
    )
    assert again.status_code == 201


def test_moving_out_ends_the_tenancy_but_keeps_the_history(
    admin: SignedInClient, world: World, db_session: Session
) -> None:
    created = make_property(admin, world)
    unit = make_unit(admin, world, created["id"])
    resident = make_resident(admin, world)
    tenancy = move_in(admin, world, unit["id"], resident["id"], TODAY - timedelta(days=90))

    ended = admin.post(
        f"{world.base}/tenancies/{tenancy['id']}/end",
        json={"move_out_date": (TODAY - timedelta(days=1)).isoformat()},
    )

    assert ended.status_code == 200
    assert ended.json()["is_current"] is False
    units = admin.get(f"{world.base}/properties/{created['id']}/units").json()
    assert units[0]["current_residents"] == []
    loaded = admin.get(f"{world.base}/residents/{resident['id']}").json()
    assert len(loaded["tenancies"]) == 1
    [event] = events(db_session, EventType.TENANCY_ENDED)
    assert event.before == {"move_out_date": None}


def test_move_out_dates_are_checked(admin: SignedInClient, world: World) -> None:
    created = make_property(admin, world)
    unit = make_unit(admin, world, created["id"])
    resident = make_resident(admin, world)
    tenancy = move_in(admin, world, unit["id"], resident["id"], TODAY)
    url = f"{world.base}/tenancies/{tenancy['id']}/end"

    before = admin.post(url, json={"move_out_date": (TODAY - timedelta(days=1)).isoformat()})
    ok = admin.post(url, json={"move_out_date": TODAY.isoformat()})
    twice = admin.post(url, json={"move_out_date": TODAY.isoformat()})

    assert before.status_code == 409
    assert ok.status_code == 200
    assert twice.status_code == 409


def test_a_future_move_in_is_not_current_yet(admin: SignedInClient, world: World) -> None:
    created = make_property(admin, world)
    unit = make_unit(admin, world, created["id"])
    resident = make_resident(admin, world)

    tenancy = move_in(admin, world, unit["id"], resident["id"], TODAY + timedelta(days=14))

    assert tenancy["is_current"] is False
    units = admin.get(f"{world.base}/properties/{created['id']}/units").json()
    assert units[0]["current_residents"] == []


def test_move_ins_only_connect_things_from_the_same_organization(
    client_factory: ClientFactory, world: World, admin: SignedInClient
) -> None:
    created = make_property(admin, world)
    unit = make_unit(admin, world, created["id"])
    resident = make_resident(admin, world)
    elm = sign_in_as(client_factory, ELM_ADMIN)
    elm_base = f"/api/organizations/{world.elm_id}"
    elm_resident = elm.post(f"{elm_base}/residents", json={"full_name": "Eli"}).json()

    foreign_unit = elm.post(
        f"{elm_base}/tenancies",
        json={
            "unit_id": unit["id"],
            "resident_id": elm_resident["id"],
            "move_in_date": "2026-01-01",
        },
    )
    foreign_resident = admin.post(
        f"{world.base}/tenancies",
        json={
            "unit_id": unit["id"],
            "resident_id": elm_resident["id"],
            "move_in_date": "2026-01-01",
        },
    )

    assert foreign_unit.status_code == 404
    assert foreign_resident.status_code == 404
    assert elm.get(f"{elm_base}/residents/{resident['id']}").status_code == 404


# --- What managers may see of residents -------------------------------------------------


def test_managers_see_residents_only_through_their_own_properties(
    client_factory: ClientFactory, world: World, admin: SignedInClient, db_session: Session
) -> None:
    mine = make_property(admin, world, "Maple Court")
    other = make_property(admin, world, "Oak Terrace")
    my_unit = make_unit(admin, world, mine["id"], "1")
    other_unit = make_unit(admin, world, other["id"], "1")
    local = make_resident(admin, world, "Local Lee", phone="555-0101")
    elsewhere = make_resident(admin, world, "Faraway Fay", phone="555-0102")
    both = make_resident(admin, world, "Both Bo")
    make_resident(admin, world, "Unplaced Una")
    move_in(admin, world, my_unit["id"], local["id"])
    move_in(admin, world, other_unit["id"], elsewhere["id"])
    move_in(admin, world, my_unit["id"], both["id"])
    move_in(admin, world, other_unit["id"], both["id"])
    assign(admin, world, mine["id"], MANAGER, db=db_session)
    manager = sign_in_as(client_factory, MANAGER)

    listed = manager.get(f"{world.base}/residents").json()

    assert [r["full_name"] for r in listed] == ["Both Bo", "Local Lee"]
    assert next(r for r in listed if r["full_name"] == "Local Lee")["phone"] == "555-0101"
    shared = next(r for r in listed if r["full_name"] == "Both Bo")
    assert [t["property_name"] for t in shared["tenancies"]] == ["Maple Court"]
    assert manager.get(f"{world.base}/residents/{elsewhere['id']}").status_code == 404
    assert manager.get(f"{world.base}/residents/{local['id']}").status_code == 200
    assert len(admin.get(f"{world.base}/residents").json()) == 4


# --- A resident's own home --------------------------------------------------------------


def invite_resident_and_accept(
    client_factory: ClientFactory, admin: SignedInClient, world: World, outbox, email: str
) -> SignedInClient:
    """The resident account is created the normal way: by accepting an invitation."""
    import re

    response = admin.post(f"{world.base}/invitations", json={"email": email, "roles": ["resident"]})
    assert response.status_code == 201
    token = re.search(r"#token=([\w-]+)", outbox.sent[-1].body).group(1)
    public = client_factory(None)
    accepted = public.post(
        "/api/invitations/accept",
        json={"token": token, "full_name": "Nia New", "password": PASSWORD},
    )
    assert accepted.status_code == 200, accepted.text
    return SignedInClient(public, accepted.json()["csrf_token"])


def test_a_resident_sees_only_their_own_current_home(
    client_factory: ClientFactory, world: World, admin: SignedInClient
) -> None:
    created = make_property(admin, world, street="12 Maple Street", city="Portland")
    building = make_building(admin, world, created["id"], "North")
    mine = make_unit(admin, world, created["id"], "4B", building["id"])
    neighbor_unit = make_unit(admin, world, created["id"], "4C")
    old_unit = make_unit(admin, world, created["id"], "1A")
    me = make_resident(admin, world, "Rae Resident", email=RESIDENT, phone="555-0100")
    neighbor = make_resident(admin, world, "Ned Neighbor", phone="555-0111")
    move_in(admin, world, mine["id"], me["id"])
    move_in(admin, world, neighbor_unit["id"], neighbor["id"])
    old = move_in(admin, world, old_unit["id"], me["id"], TODAY - timedelta(days=400))
    admin.post(
        f"{world.base}/tenancies/{old['id']}/end",
        json={"move_out_date": (TODAY - timedelta(days=100)).isoformat()},
    )

    home = sign_in_as(client_factory, RESIDENT).get(f"{world.base}/my-home")

    assert home.status_code == 200
    [place] = home.json()
    assert place["unit_label"] == "4B"
    assert place["building_name"] == "North"
    assert place["property_name"] == "Maple Court"
    assert place["street"] == "12 Maple Street"
    # Nothing about other people, and none of the private fields, is part of this reply.
    assert "Ned" not in home.text and "555-0111" not in home.text
    assert "phone" not in place and "access_instructions" not in place


def test_a_resident_account_is_linked_when_the_email_matches(
    client_factory: ClientFactory, world: World, admin: SignedInClient
) -> None:
    linked = make_resident(admin, world, "Rae Resident", email=RESIDENT)
    unlinked = make_resident(admin, world, "Other Person", email="someone.else@example.com")

    assert linked["has_account"] is True
    assert unlinked["has_account"] is False


def test_a_waiting_record_is_claimed_when_the_person_joins(
    client_factory: ClientFactory, world: World, admin: SignedInClient, outbox
) -> None:
    created = make_property(admin, world)
    unit = make_unit(admin, world, created["id"], "7")
    waiting = make_resident(admin, world, "Nia New", email="nia@example.com")
    move_in(admin, world, unit["id"], waiting["id"])
    assert waiting["has_account"] is False

    newcomer = invite_resident_and_accept(client_factory, admin, world, outbox, "nia@example.com")

    assert admin.get(f"{world.base}/residents/{waiting['id']}").json()["has_account"] is True
    [place] = newcomer.get(f"{world.base}/my-home").json()
    assert place["unit_label"] == "7"


def test_changing_a_residents_email_changes_the_link(world: World, admin: SignedInClient) -> None:
    created = make_resident(admin, world, "Rae Resident", email=RESIDENT)
    url = f"{world.base}/residents/{created['id']}"

    away = admin.put(url, json={"full_name": "Rae Resident", "email": "new@example.com"})
    back = admin.put(url, json={"full_name": "Rae Resident", "email": RESIDENT})

    assert away.json()["has_account"] is False
    assert back.json()["has_account"] is True


def test_a_resident_without_a_directory_record_has_no_home(
    client_factory: ClientFactory, world: World
) -> None:
    assert sign_in_as(client_factory, RESIDENT).get(f"{world.base}/my-home").json() == []


@pytest.mark.parametrize("email", [MANAGER, CONTRACTOR, OWNER])
def test_only_residents_have_a_home_page(
    client_factory: ClientFactory, world: World, email: str
) -> None:
    assert sign_in_as(client_factory, email).get(f"{world.base}/my-home").status_code == 403


def test_a_residents_home_is_limited_to_the_organization_in_the_address(
    client_factory: ClientFactory, world: World, admin: SignedInClient
) -> None:
    created = make_property(admin, world)
    unit = make_unit(admin, world, created["id"])
    me = make_resident(admin, world, "Rae Resident", email=RESIDENT)
    move_in(admin, world, unit["id"], me["id"])
    elm_admin = sign_in_as(client_factory, ELM_ADMIN)

    # Someone from another organization cannot read it through their own organization.
    assert elm_admin.get(f"/api/organizations/{world.elm_id}/my-home").status_code == 403
    assert elm_admin.get(f"{world.base}/my-home").status_code == 404
