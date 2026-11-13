from typing import Any

import pytest
from sqlalchemy.orm import Session
from support import SignedInClient
from test_directory import (  # noqa: F401 - world is a fixture used below
    ELM_ADMIN,
    MANAGER,
    OTHER_MANAGER,
    RESIDENT,
    World,
    events,
    world,
)
from test_dispatch import act, dispatched, jobs_url, read_job
from test_requests import (  # noqa: F401 - scene is a fixture used below
    Scene,
    scene,
    submit,
)
from test_work_orders import (
    ADMIN,
    CONTRACTOR,
    OWNER,
    convert,
    move,
    read_request,
    read_work_order,
    resident_view,
    standalone,
)

from app.models import EventType

RESOLUTION = "Replaced the cartridge. The tap no longer drips."
FINISHED = "Fitted a new cartridge and tested it for ten minutes"


# --- Helpers ----------------------------------------------------------------------------


def url(world: World, work_order_id: str, action: str = "") -> str:
    return f"{world.base}/work-orders/{work_order_id}{action}"


def verify(client: SignedInClient, world: World, work_order_id: str, **body: Any):
    return client.post(
        url(world, work_order_id, "/verify"), json={"resolution": RESOLUTION, **body}
    )


def send_back(
    client: SignedInClient, world: World, work_order_id: str, reason: str = "Still dripping"
):
    return client.post(url(world, work_order_id, "/send-back"), json={"reason": reason})


def ready(scene: Scene, world: World, db: Session) -> dict[str, Any]:
    """A job the contractor has finished, waiting for the manager."""
    assigned, _ = dispatched(scene, world, db, accepted=True)
    contractor = scene.sign_in(CONTRACTOR)
    assert act(contractor, world, assigned["id"], "status", status="in_progress").status_code == 200
    done = act(
        contractor, world, assigned["id"], "status", status="ready_for_review", note=FINISHED
    )
    assert done.status_code == 200, done.text
    return assigned


# --- Verifying --------------------------------------------------------------------------


def test_the_manager_verifies_the_work_and_records_what_it_cost(
    scene: Scene, world: World, db_session: Session
):
    order = ready(scene, world, db_session)
    request_id = order["linked_requests"][0]["id"]
    manager = scene.sign_in(MANAGER)

    response = verify(manager, world, order["id"], final_cost_cents=18550)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "completed"
    assert body["resolution"] == RESOLUTION
    assert body["final_cost_cents"] == 18550
    assert body["currency"] == "USD"
    assert body["verified_by_name"] == MANAGER
    assert body["verified_at"] is not None
    assert body["allowed_statuses"] == ["in_progress", "closed"]
    assert read_request(manager, world, request_id)["status"] == "resolved"
    assert resident_view(scene, world, RESIDENT, request_id)["status"] == "resolved"

    verified = [entry for entry in body["history"] if entry["kind"] == "verified"]
    assert [(e["body"], e["author_name"]) for e in verified] == [(RESOLUTION, MANAGER)]
    assert verified[0]["details"] == {
        "final_cost_cents": 18550,
        "currency": "USD",
        "cost_check": {
            "estimate_cents": None,
            "over_estimate_cents": None,
            "above_approval": False,
        },
    }
    statuses = [e["status"] for e in body["history"] if e["kind"] == "status_changed"]
    assert statuses[-2:] == ["ready_for_review", "completed"]
    recorded = events(db_session, EventType.WORK_ORDER_VERIFIED)
    assert len(recorded) == 1
    assert recorded[0].after == verified[0]["details"]


def test_the_cost_is_optional_and_the_currency_can_differ_from_the_property(
    scene: Scene, world: World, db_session: Session
):
    first = ready(scene, world, db_session)
    no_charge = verify(scene.sign_in(MANAGER), world, first["id"])
    assert no_charge.status_code == 200
    assert no_charge.json()["final_cost_cents"] is None
    assert no_charge.json()["currency"] is None

    second = ready(scene, world, db_session)
    euros = verify(scene.sign_in(MANAGER), world, second["id"], final_cost_cents=0, currency="eur")
    assert euros.json()["final_cost_cents"] == 0
    assert euros.json()["currency"] == "EUR"


def test_large_amounts_are_stored_exactly(scene: Scene, world: World, db_session: Session):
    order = ready(scene, world, db_session)
    cents = 123_456_789_012  # more than 2**32, and not a power of ten

    response = verify(scene.sign_in(MANAGER), world, order["id"], final_cost_cents=cents)

    assert response.json()["final_cost_cents"] == cents
    listing = scene.sign_in(MANAGER).get(
        f"{world.base}/work-orders", params={"history_only": "true"}
    )
    assert [item["final_cost_cents"] for item in listing.json()] == [cents]
    assert read_work_order(scene.sign_in(MANAGER), world, order["id"])["final_cost_cents"] == cents


@pytest.mark.parametrize(
    "body",
    [
        {"resolution": "  "},
        {"resolution": "ok"},
        {"final_cost_cents": -1},
        {"final_cost_cents": 10**12 + 1},
        {"final_cost_cents": 12.5},
        {"currency": "US"},
        {"currency": "12$"},
    ],
)
def test_a_bad_review_is_refused_and_changes_nothing(
    scene: Scene, world: World, db_session: Session, body: dict[str, Any]
):
    order = ready(scene, world, db_session)
    manager = scene.sign_in(MANAGER)
    before = read_work_order(manager, world, order["id"])

    response = manager.post(
        url(world, order["id"], "/verify"), json={"resolution": RESOLUTION, **body}
    )

    assert response.status_code in (409, 422)
    after = read_work_order(manager, world, order["id"])
    assert after["status"] == "ready_for_review"
    assert after["history"] == before["history"]
    assert after["resolution"] is None
    assert events(db_session, EventType.WORK_ORDER_VERIFIED) == []


def test_only_work_that_is_ready_can_be_verified(scene: Scene, world: World, db_session: Session):
    assigned, _ = dispatched(scene, world, db_session, accepted=True)
    manager = scene.sign_in(MANAGER)

    assert verify(manager, world, assigned["id"]).status_code == 409
    assert send_back(manager, world, assigned["id"]).status_code == 409

    order = ready(scene, world, db_session)
    assert verify(manager, world, order["id"]).status_code == 200
    assert verify(manager, world, order["id"]).status_code == 409
    assert send_back(manager, world, order["id"]).status_code == 409


def test_finished_work_cannot_skip_the_review(scene: Scene, world: World, db_session: Session):
    order = ready(scene, world, db_session)
    admin = scene.sign_in(ADMIN)
    before = read_work_order(admin, world, order["id"])

    for status in ("completed", "in_progress"):
        response = admin.post(url(world, order["id"], "/status"), json={"status": status})
        assert response.status_code == 409, status
    assert before["allowed_statuses"] == []
    assert read_work_order(admin, world, order["id"])["history"] == before["history"]


def test_a_work_order_cannot_be_closed_without_a_resolution(
    scene: Scene, world: World, db_session: Session
):
    from sqlalchemy import select

    from app.models import WorkOrder, WorkOrderStatus

    order = ready(scene, world, db_session)
    verify(scene.sign_in(MANAGER), world, order["id"])
    row = db_session.scalars(select(WorkOrder)).one()
    row.resolution = None
    db_session.commit()
    assert WorkOrderStatus(row.status) == WorkOrderStatus.COMPLETED

    response = move(scene.sign_in(MANAGER), world, order["id"], "closed")

    assert response.status_code == 409
    assert "Verify the work" in response.json()["detail"]


# --- Sending work back ------------------------------------------------------------------


def test_sending_work_back_tells_the_contractor_why(
    scene: Scene, world: World, db_session: Session
):
    order = ready(scene, world, db_session)
    request_id = order["linked_requests"][0]["id"]
    manager = scene.sign_in(MANAGER)

    response = send_back(manager, world, order["id"], "The tap still drips when it is cold")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "in_progress"
    assert body["resolution"] is None
    sent = [entry for entry in body["history"] if entry["kind"] == "sent_back"]
    assert [(e["body"], e["author_name"]) for e in sent] == [
        ("The tap still drips when it is cold", MANAGER)
    ]
    assert body["assignment"]["response"] == "accepted"
    assert len(events(db_session, EventType.WORK_ORDER_SENT_BACK)) == 1
    assert read_request(manager, world, request_id)["status"] == "in_progress"

    contractor = scene.sign_in(CONTRACTOR)
    job = read_job(contractor, world, order["id"])
    assert job["status"] == "in_progress"
    assert job["allowed_statuses"] == ["on_hold", "ready_for_review"]
    reasons = [e for e in job["timeline"] if e["kind"] == "sent_back"]
    assert [(e["body"], e["author"]) for e in reasons] == [
        ("The tap still drips when it is cold", "Property team")
    ]
    assert MANAGER not in str(job)

    again = act(
        contractor,
        world,
        order["id"],
        "status",
        status="ready_for_review",
        note="Fixed it properly",
    )
    assert again.status_code == 200
    assert verify(manager, world, order["id"]).status_code == 200


@pytest.mark.parametrize("reason", ["", "  ", "no"])
def test_sending_back_needs_a_reason(scene: Scene, world: World, db_session: Session, reason: str):
    order = ready(scene, world, db_session)

    response = send_back(scene.sign_in(MANAGER), world, order["id"], reason)

    assert response.status_code == 422
    assert (
        read_work_order(scene.sign_in(MANAGER), world, order["id"])["status"] == "ready_for_review"
    )


# --- Who can review ---------------------------------------------------------------------


@pytest.mark.parametrize("email", [RESIDENT, CONTRACTOR, OWNER])
def test_only_staff_can_review_work(scene: Scene, world: World, db_session: Session, email: str):
    order = ready(scene, world, db_session)
    client = scene.sign_in(email)

    assert verify(client, world, order["id"]).status_code == 403
    assert send_back(client, world, order["id"]).status_code == 403
    assert (
        read_work_order(scene.sign_in(MANAGER), world, order["id"])["status"] == "ready_for_review"
    )


@pytest.mark.parametrize("email", [OTHER_MANAGER, ELM_ADMIN])
def test_reviews_follow_property_and_organization_scope(
    scene: Scene, world: World, db_session: Session, email: str
):
    order = ready(scene, world, db_session)
    client = scene.sign_in(email)

    assert verify(client, world, order["id"]).status_code == 404
    assert send_back(client, world, order["id"]).status_code == 404


def test_a_contractor_never_sees_the_resolution_or_the_cost(
    scene: Scene, world: World, db_session: Session
):
    order = ready(scene, world, db_session)
    verify(scene.sign_in(MANAGER), world, order["id"], final_cost_cents=987654)
    contractor = scene.sign_in(CONTRACTOR)

    response = contractor.get(jobs_url(world, order["id"]))

    assert response.status_code == 200
    assert response.json()["status"] == "completed"
    for hidden in (RESOLUTION, "987654", "9876.54", "final_cost", "resolution"):
        assert hidden not in response.text, hidden
    assert not any(entry["kind"] == "verified" for entry in response.json()["timeline"])
    assert contractor.get(f"{world.base}/work-orders/{order['id']}").status_code == 403


def test_a_resident_never_sees_the_resolution_or_the_cost(
    scene: Scene, world: World, db_session: Session
):
    order = ready(scene, world, db_session)
    request_id = order["linked_requests"][0]["id"]
    verify(scene.sign_in(MANAGER), world, order["id"], final_cost_cents=987654)

    seen = scene.sign_in(RESIDENT).get(f"{world.base}/my-requests/{request_id}")

    assert seen.status_code == 200
    for hidden in (RESOLUTION, "987654", "final_cost", "resolution"):
        assert hidden not in seen.text, hidden


# --- Closing and reopening --------------------------------------------------------------


def test_closing_keeps_the_outcome_and_closes_the_request(
    scene: Scene, world: World, db_session: Session
):
    order = ready(scene, world, db_session)
    request_id = order["linked_requests"][0]["id"]
    manager = scene.sign_in(MANAGER)
    verify(manager, world, order["id"], final_cost_cents=4500)

    closed = move(manager, world, order["id"], "closed", "Invoice paid")

    assert closed.status_code == 200
    body = closed.json()
    assert body["status"] == "closed"
    assert (body["resolution"], body["final_cost_cents"]) == (RESOLUTION, 4500)
    assert resident_view(scene, world, RESIDENT, request_id)["status"] == "closed"


def test_reopening_clears_the_outcome_but_the_history_keeps_every_review(
    scene: Scene, world: World, db_session: Session
):
    order = ready(scene, world, db_session)
    manager = scene.sign_in(MANAGER)
    verify(manager, world, order["id"], final_cost_cents=4500)

    reopened = move(manager, world, order["id"], "in_progress", "The leak is back")
    assert reopened.status_code == 200
    body = reopened.json()
    assert body["status"] == "in_progress"
    assert (body["resolution"], body["final_cost_cents"], body["currency"]) == (None, None, None)
    assert body["verified_at"] is None and body["verified_by_name"] is None

    act(
        scene.sign_in(CONTRACTOR),
        world,
        order["id"],
        "status",
        status="ready_for_review",
        note="Redone",
    )
    second = verify(
        manager, world, order["id"], final_cost_cents=9000, resolution="Replaced the pipe"
    )
    assert second.status_code == 200
    kinds = [
        (e["kind"], (e["details"] or {}).get("final_cost_cents")) for e in second.json()["history"]
    ]
    assert [item for item in kinds if item[0] == "verified"] == [
        ("verified", 4500),
        ("verified", 9000),
    ]
    assert second.json()["final_cost_cents"] == 9000


# --- The whole loop ---------------------------------------------------------------------


def test_a_report_travels_all_the_way_to_closure_with_a_complete_timeline(
    scene: Scene, world: World, db_session: Session
):
    from test_dispatch import assign_to, membership_id

    resident = scene.sign_in(RESIDENT)
    manager = scene.sign_in(MANAGER)
    contractor = scene.sign_in(CONTRACTOR)
    seen: list[str] = []

    request = submit(scene, world, resident)
    seen.append(resident_view(scene, world, RESIDENT, request["id"])["status"])
    order = convert(manager, world, request["id"]).json()
    seen.append(resident_view(scene, world, RESIDENT, request["id"])["status"])
    assign_to(manager, world, order["id"], membership_id(db_session, world, CONTRACTOR))
    seen.append(resident_view(scene, world, RESIDENT, request["id"])["status"])
    act(contractor, world, order["id"], "accept")
    act(contractor, world, order["id"], "status", status="in_progress")
    act(contractor, world, order["id"], "status", status="ready_for_review", note=FINISHED)
    seen.append(resident_view(scene, world, RESIDENT, request["id"])["status"])
    assert verify(manager, world, order["id"], final_cost_cents=18550).status_code == 200
    seen.append(resident_view(scene, world, RESIDENT, request["id"])["status"])
    assert move(manager, world, order["id"], "closed").status_code == 200
    seen.append(resident_view(scene, world, RESIDENT, request["id"])["status"])

    assert seen == [
        "submitted",
        "in_review",
        "in_progress",
        "in_progress",
        "resolved",
        "closed",
    ]

    history = read_work_order(manager, world, order["id"])["history"]
    story = [(e["kind"], e["status"], e["author_name"]) for e in history]
    assert story == [
        ("created", "open", MANAGER),
        ("request_linked", None, MANAGER),
        ("assigned", None, MANAGER),
        ("status_changed", "assigned", MANAGER),
        ("assignment_accepted", None, CONTRACTOR),
        ("status_changed", "in_progress", CONTRACTOR),
        ("status_changed", "ready_for_review", CONTRACTOR),
        ("status_changed", "completed", MANAGER),
        ("verified", None, MANAGER),
        ("status_changed", "closed", MANAGER),
    ]
    assert all(e["author_name"] is not None for e in history)
    finished = [e for e in history if e["status"] == "ready_for_review"][0]
    assert finished["body"] == FINISHED
    final = read_work_order(manager, world, order["id"])
    assert (final["status"], final["final_cost_cents"]) == ("closed", 18550)


# --- Maintenance history ----------------------------------------------------------------


def test_maintenance_history_lists_finished_work_by_property_and_unit(
    scene: Scene, world: World, db_session: Session
):
    done = ready(scene, world, db_session)
    verify(scene.sign_in(MANAGER), world, done["id"], final_cost_cents=1200)
    open_order = standalone(
        scene.sign_in(MANAGER),
        world,
        scene.maple["id"],
        title="Repaint",
        unit_id=scene.unit_2b["id"],
    ).json()
    other_unit = standalone(
        scene.sign_in(MANAGER),
        world,
        scene.maple["id"],
        title="Fix the door",
        unit_id=scene.unit_2b["id"],
    ).json()
    manager = scene.sign_in(MANAGER)
    for step in ("in_progress", "ready_for_review", "completed"):
        move(manager, world, other_unit["id"], step)
    cancelled = standalone(manager, world, scene.maple["id"], title="Never needed").json()
    move(manager, world, cancelled["id"], "cancelled")
    base = f"{world.base}/work-orders"

    everything = manager.get(
        base, params={"property_id": scene.maple["id"], "history_only": "true"}
    )
    assert sorted(item["title"] for item in everything.json()) == sorted(
        [done["title"], "Fix the door"]
    )
    unit = manager.get(base, params={"unit_id": scene.unit_2b["id"], "history_only": "true"})
    assert [item["title"] for item in unit.json()] == ["Fix the door"]
    assert open_order["title"] not in everything.text
    assert "Never needed" not in everything.text


def test_maintenance_history_respects_property_scope(
    scene: Scene, world: World, db_session: Session
):
    done = ready(scene, world, db_session)
    verify(scene.sign_in(MANAGER), world, done["id"])
    oak = standalone(scene.sign_in(ADMIN), world, scene.oak["id"], title="Oak job").json()
    admin = scene.sign_in(ADMIN)
    for step in ("in_progress", "ready_for_review", "completed"):
        move(admin, world, oak["id"], step)

    manager_view = scene.sign_in(MANAGER).get(
        f"{world.base}/work-orders", params={"history_only": "true"}
    )
    admin_view = admin.get(f"{world.base}/work-orders", params={"history_only": "true"})

    assert [item["title"] for item in manager_view.json()] == [done["title"]]
    assert len(admin_view.json()) == 2
