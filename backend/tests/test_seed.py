import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session
from support import PASSWORD, ClientFactory, sign_in_as

from app.models import Organization, Resident, Tenancy, Unit, User
from app.seed import main
from app.services.seed import (
    ADMIN_EMAIL,
    MANAGER_EMAIL,
    ORGANIZATION_NAME,
    RESIDENT_EMAIL,
    AlreadySeededError,
    seed_demo_organization,
)


@pytest.fixture
def seeded(db_session: Session) -> Organization:
    result = seed_demo_organization(db_session, password=PASSWORD)
    db_session.commit()
    return result.organization


def test_the_demo_firm_is_a_usable_portfolio(db_session: Session, seeded: Organization) -> None:
    assert seeded.name == ORGANIZATION_NAME
    assert len(db_session.scalars(select(Unit)).all()) == 24
    assert len(db_session.scalars(select(Resident)).all()) == 18
    # Some units are vacant, and one resident has moved out.
    tenancies = db_session.scalars(select(Tenancy)).all()
    assert len(tenancies) == 16
    assert any(t.move_out_date is not None for t in tenancies)


def test_nothing_in_the_demo_data_belongs_to_a_real_person(
    db_session: Session, seeded: Organization
) -> None:
    for user in db_session.scalars(select(User)):
        assert user.email.endswith("@demo.example")
    for resident in db_session.scalars(select(Resident)):
        assert resident.email is not None and resident.email.endswith("@demo.example")
        assert resident.phone is not None and resident.phone.startswith("555-01")


def test_each_demo_role_can_sign_in(client_factory: ClientFactory, seeded: Organization) -> None:
    for email in (
        ADMIN_EMAIL,
        MANAGER_EMAIL,
        RESIDENT_EMAIL,
        "contractor@demo.example",
        "owner@demo.example",
    ):
        sign_in_as(client_factory, email)


def test_the_demo_shows_property_scoping(
    client_factory: ClientFactory, seeded: Organization
) -> None:
    base = f"/api/organizations/{seeded.id}"

    admin = sign_in_as(client_factory, ADMIN_EMAIL).get(f"{base}/properties").json()
    manager = sign_in_as(client_factory, MANAGER_EMAIL).get(f"{base}/properties").json()

    assert [p["name"] for p in admin] == ["Maple Court", "Oak Terrace Houses", "Riverside Lofts"]
    assert [p["name"] for p in manager] == ["Maple Court", "Riverside Lofts"]
    maple = next(p for p in admin if p["name"] == "Maple Court")
    assert [b["name"] for b in maple["buildings"]] == ["Building A", "Building B"]
    assert maple["unit_count"] == 10
    assert maple["approval_threshold_cents"] == 50000


def test_the_demo_resident_sees_their_own_home(
    client_factory: ClientFactory, seeded: Organization
) -> None:
    home = sign_in_as(client_factory, RESIDENT_EMAIL).get(f"/api/organizations/{seeded.id}/my-home")

    [place] = home.json()
    assert (place["property_name"], place["building_name"], place["unit_label"]) == (
        "Maple Court",
        "Building A",
        "2B",
    )


def test_seeding_twice_is_refused_and_changes_nothing(db_session: Session) -> None:
    seed_demo_organization(db_session, password=PASSWORD)
    db_session.commit()

    with pytest.raises(AlreadySeededError):
        seed_demo_organization(db_session, password=PASSWORD)
    db_session.rollback()

    assert len(db_session.scalars(select(Organization)).all()) == 1


def test_the_command_reports_what_it_made_and_how_to_sign_in(
    migrated_engine: Engine, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(session_factory=lambda: Session(migrated_engine), password="shown-once-12345")

    output = capsys.readouterr().out
    assert code == 0
    assert "3 properties, 24 units, 18 residents" in output
    assert "shown-once-12345" in output
    assert ADMIN_EMAIL in output


def test_the_command_refuses_to_run_twice(
    migrated_engine: Engine, capsys: pytest.CaptureFixture[str]
) -> None:
    main(session_factory=lambda: Session(migrated_engine), password="shown-once-12345")
    capsys.readouterr()

    code = main(session_factory=lambda: Session(migrated_engine), password="another-one-12345")

    captured = capsys.readouterr()
    assert code == 1
    assert "already exists" in captured.err
    assert "another-one-12345" not in captured.out + captured.err


def test_the_demo_has_requests_in_several_statuses(
    client_factory: ClientFactory, seeded: Organization
) -> None:
    base = f"/api/organizations/{seeded.id}"

    admin = sign_in_as(client_factory, ADMIN_EMAIL).get(f"{base}/requests").json()
    manager = sign_in_as(client_factory, MANAGER_EMAIL).get(f"{base}/requests").json()
    resident = sign_in_as(client_factory, RESIDENT_EMAIL).get(f"{base}/my-requests").json()

    assert len(admin) == 10
    assert {item["status"] for item in admin} >= {"submitted", "in_review", "in_progress", "closed"}
    # The manager looks after two of the three properties, so Oak Terrace is out of reach.
    assert 0 < len(manager) < len(admin)
    assert all(item["property_name"] != "Oak Terrace Houses" for item in manager)
    assert len(resident) == 3


def test_the_demo_has_a_queue_to_triage_and_work_orders_to_follow(
    client_factory: ClientFactory, seeded: Organization
) -> None:
    base = f"/api/organizations/{seeded.id}"
    manager = sign_in_as(client_factory, MANAGER_EMAIL)

    queue = manager.get(f"{base}/requests", params={"needs_triage": "true"}).json()
    work_orders = manager.get(f"{base}/work-orders").json()

    # Five reports wait for a decision, including two about the same mice.
    assert len(queue) == 5
    assert {item["urgency"] for item in queue} >= {"routine", "soon", "urgent"}
    # Five were turned into work orders. The manager does not look after Oak Terrace.
    everything = sign_in_as(client_factory, ADMIN_EMAIL).get(f"{base}/work-orders").json()
    assert len(everything) == 5
    assert {item["status"] for item in work_orders} == {"ready_for_review", "completed", "on_hold"}
    # The emergency at Oak Terrace is past its due date.
    assert [item["title"] for item in everything if item["overdue"]] == ["No hot water"]


def test_the_demo_contractor_has_jobs_in_different_states(
    client_factory: ClientFactory, seeded: Organization
) -> None:
    base = f"/api/organizations/{seeded.id}"
    contractor = sign_in_as(client_factory, "contractor@demo.example")

    jobs = contractor.get(f"{base}/my-jobs").json()
    everything = sign_in_as(client_factory, ADMIN_EMAIL).get(f"{base}/work-orders").json()

    assert len(jobs) == 3
    assert {(job["status"], job["response"]) for job in jobs} == {
        ("ready_for_review", "accepted"),
        ("completed", "accepted"),
        ("awaiting_approval", "pending"),
    }
    # Two work orders have no contractor, so the manager has something to assign.
    assert sum(1 for item in everything if item["assignee_id"] is None) == 2
    # The pending job is the one waiting for a reply, and shows no resident details yet.
    waiting = next(job for job in jobs if job["response"] == "pending")
    detail = contractor.get(f"{base}/my-jobs/{waiting['id']}").json()
    assert detail["residents"] == [] and detail["access_notes"] == []


def test_the_demo_has_work_to_verify_and_a_history_with_costs(
    client_factory: ClientFactory, seeded: Organization
) -> None:
    base = f"/api/organizations/{seeded.id}"
    manager = sign_in_as(client_factory, MANAGER_EMAIL)
    admin = sign_in_as(client_factory, ADMIN_EMAIL)

    waiting = manager.get(f"{base}/work-orders", params={"status": "ready_for_review"}).json()
    history = admin.get(f"{base}/work-orders", params={"history_only": "true"}).json()

    assert [item["title"] for item in waiting] == ["Kitchen faucet drips"]
    detail = manager.get(f"{base}/work-orders/{waiting[0]['id']}").json()
    assert detail["resolution"] is None
    assert any(entry["kind"] == "progress" for entry in detail["history"])
    # The radiator job and the smoke detector job are both on record, with what they cost.
    assert sorted((item["status"], item["final_cost_cents"]) for item in history) == [
        ("closed", 4500),
        ("completed", 18500),
    ]
    assert {item["currency"] for item in history} == {"USD"}


def test_the_demo_owner_has_one_estimate_to_decide_and_one_already_decided(
    client_factory: ClientFactory, seeded: Organization
) -> None:
    base = f"/api/organizations/{seeded.id}"
    owner = sign_in_as(client_factory, "owner@demo.example")
    admin = sign_in_as(client_factory, ADMIN_EMAIL)

    approvals = owner.get(f"{base}/my-approvals").json()
    everything = admin.get(f"{base}/work-orders").json()

    by_title = {item["title"]: item for item in approvals}
    assert set(by_title) == {"No hot water", "Dishwasher leaking"}
    waiting = by_title["No hot water"]
    assert (waiting["status"], waiting["amount_cents"], waiting["decidable"]) == (
        "pending",
        145000,
        True,
    )
    decided = by_title["Dishwasher leaking"]
    assert (decided["status"], decided["amount_cents"], decided["decidable"]) == (
        "approved",
        132000,
        False,
    )
    # The held work order is the one the owner is asked about; the quote under the threshold is
    # not theirs to decide, so it is not listed.
    assert next(item for item in everything if item["title"] == "No hot water")["status"] == (
        "awaiting_approval"
    )
    assert "Kitchen faucet drips" not in by_title
