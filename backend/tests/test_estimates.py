import json
import uuid
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from support import PASSWORD, SignedInClient
from test_directory import (  # noqa: F401 - world is a fixture used below
    ELM_ADMIN,
    MANAGER,
    OTHER_MANAGER,
    RESIDENT,
    World,
    events,
    world,
)
from test_dispatch import act, dispatched, membership_id, read_job
from test_requests import (  # noqa: F401 - scene is a fixture used below
    Scene,
    scene,
)
from test_work_orders import (
    ADMIN,
    CONTRACTOR,
    OWNER,
    move,
    read_request,
    read_work_order,
    resident_view,
)

from app.core.clock import utc_now
from app.models import (
    EntryKind,
    EstimateStatus,
    EventType,
    Membership,
    MembershipRole,
    Role,
    WorkOrder,
    WorkOrderEntry,
    WorkOrderStatus,
)
from app.services import work_orders
from app.services.organizations import add_membership
from app.services.users import create_user
from app.services.work_orders import ApprovalRequiredError

THRESHOLD = 50_000
QUOTE = "Replace the cartridge and both washers."
SECOND_OWNER = "owner2@harbor.example"
SECRET_NOTE = "The tenant is three months behind on rent"


# --- Helpers ----------------------------------------------------------------------------


def wo_url(world: World, work_order_id: str, action: str = "") -> str:
    return f"{world.base}/work-orders/{work_order_id}{action}"


def approvals_url(world: World, estimate_id: str | None = None, action: str = "") -> str:
    return f"{world.base}/my-approvals" + (f"/{estimate_id}{action}" if estimate_id else "")


def quote(
    client: SignedInClient, world: World, work_order_id: str, cents: int = 80_000, **body: Any
):
    return client.post(
        wo_url(world, work_order_id, "/estimates"),
        json={"amount_cents": cents, "description": QUOTE, **body},
    )


def decide(
    client: SignedInClient,
    world: World,
    estimate_id: str,
    decision: str = "approve",
    reason: str | None = None,
):
    return client.post(
        f"{world.base}/my-approvals/{estimate_id}/decision",
        json={"decision": decision, "reason": reason},
    )


def set_threshold(scene: Scene, world: World, cents: int | None = THRESHOLD) -> None:
    response = scene.sign_in(ADMIN).put(
        f"{world.base}/properties/{scene.maple['id']}",
        json={"name": scene.maple["name"], "approval_threshold_cents": cents},
    )
    assert response.status_code == 200, response.text


def own(
    scene: Scene,
    world: World,
    db: Session,
    *emails: str,
    property_id: str | None = None,
):
    ids = [membership_id(db, world, email) for email in emails]
    response = scene.sign_in(ADMIN).put(
        f"{world.base}/properties/{property_id or scene.maple['id']}/owners",
        json={"membership_ids": ids},
    )
    assert response.status_code == 200, response.text
    return response


def job(scene: Scene, world: World, db: Session, *, accepted: bool = True) -> dict[str, Any]:
    """An assigned work order at Maple Court, which has a threshold and an owner."""
    set_threshold(scene, world)
    own(scene, world, db, OWNER)
    assigned, _ = dispatched(scene, world, db, accepted=accepted)
    return assigned


def held(scene: Scene, world: World, db: Session, cents: int = 80_000) -> tuple[dict, dict]:
    """A work order waiting for the owner, and its estimate."""
    order = job(scene, world, db)
    response = quote(scene.sign_in(MANAGER), world, order["id"], cents)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "awaiting_approval"
    return body, body["estimates"][0]


def force_status(db: Session, work_order_id: str, status: WorkOrderStatus) -> WorkOrder:
    db.expire_all()
    order = db.scalars(select(WorkOrder).where(WorkOrder.id == uuid.UUID(work_order_id))).one()
    order.status = status
    db.commit()
    return order


def add_owner_account(db: Session, world: World, email: str = SECOND_OWNER) -> str:
    from app.models import Organization

    harbor = db.scalar(select(Organization).where(Organization.id == world.harbor_id))
    user = create_user(db, email=email, full_name="Second Owner", password=PASSWORD)
    add_membership(db, organization=harbor, user=user, roles=[Role.PROPERTY_OWNER], actor=None)
    db.commit()
    return membership_id(db, world, email)


# --- Recording an estimate --------------------------------------------------------------


def test_an_estimate_under_the_threshold_needs_nobody(
    scene: Scene, world: World, db_session: Session
):
    order = job(scene, world, db_session)

    response = quote(scene.sign_in(MANAGER), world, order["id"], 14_000, provider_name="Harbor Co")

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "assigned"
    assert body["approval_hold"] is None
    assert body["owner_names"] == [OWNER]
    (estimate,) = body["estimates"]
    assert estimate["status"] == "not_required"
    assert estimate["approval_required"] is False
    assert estimate["amount_cents"] == 14_000
    assert estimate["currency"] == "USD"
    assert estimate["provider_name"] == "Harbor Co"
    assert estimate["submitted_by_name"] == MANAGER
    assert estimate["threshold_cents"] == THRESHOLD
    assert estimate["current"] is True
    entries = [e for e in body["history"] if e["kind"] == "estimate_submitted"]
    assert [(e["body"], e["author_name"]) for e in entries] == [(QUOTE, MANAGER)]
    assert entries[0]["details"]["amount_cents"] == 14_000
    recorded = events(db_session, EventType.ESTIMATE_SUBMITTED)
    assert len(recorded) == 1 and recorded[0].after is not None
    assert recorded[0].after["approval_required"] is False


def test_the_threshold_itself_is_allowed_and_one_cent_more_is_not(
    scene: Scene, world: World, db_session: Session
):
    order = job(scene, world, db_session)
    manager = scene.sign_in(MANAGER)

    at_threshold = quote(manager, world, order["id"], THRESHOLD).json()
    assert at_threshold["estimates"][0]["status"] == "not_required"
    assert at_threshold["status"] == "assigned"

    over = quote(manager, world, order["id"], THRESHOLD + 1).json()
    assert over["estimates"][0]["status"] == "pending"
    assert over["status"] == "awaiting_approval"


def test_a_property_without_a_threshold_never_asks_for_approval(
    scene: Scene, world: World, db_session: Session
):
    order = job(scene, world, db_session)
    set_threshold(scene, world, None)

    body = quote(scene.sign_in(MANAGER), world, order["id"], 10**9).json()

    assert body["estimates"][0]["status"] == "not_required"
    assert body["status"] == "assigned"
    assert body["approval_threshold_cents"] is None


def test_an_estimate_above_the_threshold_holds_the_work(
    scene: Scene, world: World, db_session: Session
):
    order = job(scene, world, db_session)
    request_id = order["linked_requests"][0]["id"]

    body = quote(scene.sign_in(MANAGER), world, order["id"], 80_000).json()

    assert body["status"] == "awaiting_approval"
    assert body["estimates"][0]["status"] == "pending"
    assert body["estimates"][0]["approval_required"] is True
    assert body["approval_hold"] is not None
    assert "in_progress" not in body["allowed_statuses"]
    assert body["can_record_estimate"] is True
    # The resident is told only that it is in progress.
    assert resident_view(scene, world, RESIDENT, request_id)["status"] == "in_progress"


@pytest.mark.parametrize("cents", [0, -5, 10**12 + 1])
def test_an_estimate_must_be_a_sensible_amount(
    scene: Scene, world: World, db_session: Session, cents: int
):
    order = job(scene, world, db_session)

    response = quote(scene.sign_in(MANAGER), world, order["id"], cents)

    assert response.status_code == 422
    assert read_work_order(scene.sign_in(MANAGER), world, order["id"])["estimates"] == []


def test_an_estimate_must_say_what_it_covers(scene: Scene, world: World, db_session: Session):
    order = job(scene, world, db_session)
    manager = scene.sign_in(MANAGER)

    blank = manager.post(
        wo_url(world, order["id"], "/estimates"), json={"amount_cents": 100, "description": "  "}
    )
    missing = manager.post(wo_url(world, order["id"], "/estimates"), json={"amount_cents": 100})

    assert blank.status_code == 422 and missing.status_code == 422


def test_large_estimates_are_stored_exactly(scene: Scene, world: World, db_session: Session):
    order = job(scene, world, db_session)
    cents = 123_456_789_012  # more than 2**32, and not a power of ten

    body = quote(scene.sign_in(MANAGER), world, order["id"], cents).json()

    assert body["estimates"][0]["amount_cents"] == cents


@pytest.mark.parametrize("status", ["ready_for_review", "completed", "closed", "cancelled"])
def test_an_estimate_cannot_be_recorded_once_the_work_is_done_or_cancelled(
    scene: Scene, world: World, db_session: Session, status: str
):
    order = job(scene, world, db_session)
    force_status(db_session, order["id"], WorkOrderStatus(status))

    response = quote(scene.sign_in(MANAGER), world, order["id"], 100)

    assert response.status_code == 409
    assert read_work_order(scene.sign_in(MANAGER), world, order["id"])["estimates"] == []


def test_a_revision_replaces_the_estimate_and_keeps_the_old_one(
    scene: Scene, world: World, db_session: Session
):
    order = job(scene, world, db_session)
    manager = scene.sign_in(MANAGER)
    quote(manager, world, order["id"], 20_000)

    body = quote(manager, world, order["id"], 30_000).json()

    assert [(e["version"], e["amount_cents"], e["current"]) for e in body["estimates"]] == [
        (2, 30_000, True),
        (1, 20_000, False),
    ]
    kinds = [e["kind"] for e in body["history"]]
    assert kinds.count("estimate_submitted") == 2


def test_revising_a_pending_estimate_down_releases_the_work(
    scene: Scene, world: World, db_session: Session
):
    order, first = held(scene, world, db_session)

    body = quote(scene.sign_in(MANAGER), world, order["id"], 40_000).json()

    assert body["status"] == "assigned"
    assert body["approval_hold"] is None
    assert [e["status"] for e in body["estimates"]] == ["not_required", "pending"]
    assert body["estimates"][1]["id"] == first["id"]


def test_revising_a_pending_estimate_keeps_waiting_and_remembers_where_to_resume(
    scene: Scene, world: World, db_session: Session
):
    order = job(scene, world, db_session)
    contractor = scene.sign_in(CONTRACTOR)
    act(contractor, world, order["id"], "status", status="in_progress")
    manager = scene.sign_in(MANAGER)
    quote(manager, world, order["id"], 80_000)

    revised = quote(manager, world, order["id"], 90_000).json()
    assert revised["status"] == "awaiting_approval"

    owner = scene.sign_in(OWNER)
    approved = decide(owner, world, revised["estimates"][0]["id"])
    assert approved.status_code == 200, approved.text
    assert read_work_order(manager, world, order["id"])["status"] == "in_progress"


def test_only_staff_at_the_property_can_record_an_estimate(
    scene: Scene, world: World, db_session: Session
):
    order = job(scene, world, db_session)

    assert quote(scene.sign_in(OTHER_MANAGER), world, order["id"]).status_code == 404
    for email in (CONTRACTOR, RESIDENT, OWNER):
        assert quote(scene.sign_in(email), world, order["id"]).status_code == 403
    assert quote(scene.sign_in(ADMIN), world, order["id"], 100).status_code == 201


# --- The approval gate ------------------------------------------------------------------


def test_the_gate_blocks_every_route_to_starting_work(
    scene: Scene, world: World, db_session: Session
):
    order, _ = held(scene, world, db_session)
    manager = scene.sign_in(MANAGER)
    contractor = scene.sign_in(CONTRACTOR)

    # The manager parks the work order. Moving it on by hand is still refused.
    assert move(manager, world, order["id"], "on_hold", "Waiting").status_code == 200
    by_manager = move(manager, world, order["id"], "in_progress")
    assert by_manager.status_code == 409
    assert "approval" in by_manager.json()["detail"]
    by_admin = move(scene.sign_in(ADMIN), world, order["id"], "in_progress")
    assert by_admin.status_code == 409
    # So is the contractor's own Start button.
    by_contractor = act(contractor, world, order["id"], "status", status="in_progress")
    assert by_contractor.status_code == 409
    assert "approval" in by_contractor.json()["detail"]
    # None of that left a trace.
    after = read_work_order(manager, world, order["id"])
    assert after["status"] == "on_hold"
    assert "in_progress" not in after["allowed_statuses"]
    assert [e["status"] for e in after["history"] if e["kind"] == "status_changed"][-1] == (
        "on_hold"
    )


def test_a_held_contractor_job_gives_away_no_money(scene: Scene, world: World, db_session: Session):
    order, _ = held(scene, world, db_session, 80_000)
    manager = scene.sign_in(MANAGER)
    move(manager, world, order["id"], "on_hold", "Waiting")
    contractor = scene.sign_in(CONTRACTOR)

    refused = act(contractor, world, order["id"], "status", status="in_progress")
    detail = read_job(contractor, world, order["id"])

    for text in (refused.text, json.dumps(detail)):
        assert "80000" not in text and "80,000" not in text and "800.00" not in text
        assert "estimate" not in text.lower()
    assert detail["status"] == "on_hold"
    assert all(item["kind"] != "estimate_submitted" for item in detail["timeline"])


@pytest.mark.parametrize(
    ("current", "target", "review"),
    [
        (WorkOrderStatus.ON_HOLD, WorkOrderStatus.IN_PROGRESS, False),
        (WorkOrderStatus.ASSIGNED, WorkOrderStatus.IN_PROGRESS, False),
        (WorkOrderStatus.OPEN, WorkOrderStatus.IN_PROGRESS, False),
        (WorkOrderStatus.IN_PROGRESS, WorkOrderStatus.READY_FOR_REVIEW, False),
        (WorkOrderStatus.READY_FOR_REVIEW, WorkOrderStatus.COMPLETED, True),
        (WorkOrderStatus.COMPLETED, WorkOrderStatus.IN_PROGRESS, False),
    ],
)
def test_no_internal_path_slips_past_the_gate(
    scene: Scene,
    world: World,
    db_session: Session,
    current: WorkOrderStatus,
    target: WorkOrderStatus,
    review: bool,
):
    order, _ = held(scene, world, db_session)
    work_order = force_status(db_session, order["id"], current)
    work_order_id = work_order.id
    manager = db_session.scalars(
        select(Membership).join(Membership.user).where(Membership.user.has(email=MANAGER))
    ).one()

    # `system` and `review` exist for dispatch, approvals and verification. Neither one is a
    # way around the owner.
    for system in (False, True):
        with pytest.raises(ApprovalRequiredError):
            work_orders.change_status(
                db_session,
                work_order,
                actor=manager.user,
                new_status=target,
                note=None,
                is_administrator=True,
                system=system,
                review=review,
            )
    db_session.rollback()
    db_session.expire_all()
    unchanged = db_session.get(WorkOrder, work_order_id)
    assert unchanged is not None and unchanged.status == current


def test_verifying_is_refused_while_an_approval_is_outstanding(
    scene: Scene, world: World, db_session: Session
):
    order, _ = held(scene, world, db_session)
    force_status(db_session, order["id"], WorkOrderStatus.READY_FOR_REVIEW)

    response = scene.sign_in(MANAGER).post(
        wo_url(world, order["id"], "/verify"), json={"resolution": "All done"}
    )

    assert response.status_code == 409
    assert read_work_order(scene.sign_in(MANAGER), world, order["id"])["status"] == (
        "ready_for_review"
    )


def test_a_held_work_order_cannot_be_reassigned_around_the_gate(
    scene: Scene, world: World, db_session: Session
):
    order, _ = held(scene, world, db_session)
    contractor = scene.sign_in(MANAGER).get(f"{world.base}/contractors").json()[0]

    response = scene.sign_in(MANAGER).post(
        wo_url(world, order["id"], "/assign"), json={"contractor_id": contractor["id"]}
    )

    assert response.status_code == 409


def test_the_hold_survives_cancelling_and_reopening(
    scene: Scene, world: World, db_session: Session
):
    order, _ = held(scene, world, db_session)
    manager = scene.sign_in(MANAGER)
    assert move(manager, world, order["id"], "cancelled").status_code == 200
    assert move(scene.sign_in(ADMIN), world, order["id"], "open").status_code == 200

    reopened = read_work_order(manager, world, order["id"])
    assert reopened["approval_hold"] is not None
    assert move(manager, world, order["id"], "in_progress").status_code == 409


def test_work_proceeds_normally_when_no_approval_is_needed(
    scene: Scene, world: World, db_session: Session
):
    order = job(scene, world, db_session)
    quote(scene.sign_in(MANAGER), world, order["id"], 10_000)

    started = act(scene.sign_in(CONTRACTOR), world, order["id"], "status", status="in_progress")

    assert started.status_code == 200, started.text


# --- Deciding ---------------------------------------------------------------------------


def test_the_owner_approves_and_the_work_resumes(scene: Scene, world: World, db_session: Session):
    order, estimate = held(scene, world, db_session, 80_000)
    owner = scene.sign_in(OWNER)

    response = decide(owner, world, estimate["id"], "approve", "Go ahead.")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "approved"
    assert body["decided_by_name"] == OWNER
    assert body["decided_at"] is not None
    assert body["decision_reason"] == "Go ahead."
    assert body["decidable"] is False
    manager = scene.sign_in(MANAGER)
    after = read_work_order(manager, world, order["id"])
    assert after["status"] == "assigned"
    assert after["approval_hold"] is None
    assert after["estimates"][0]["status"] == "approved"
    decided = [e for e in after["history"] if e["kind"] == "estimate_approved"]
    assert [(e["body"], e["author_name"]) for e in decided] == [("Go ahead.", OWNER)]
    assert decided[0]["details"]["amount_cents"] == 80_000
    recorded = events(db_session, EventType.ESTIMATE_DECIDED)
    assert len(recorded) == 1
    assert recorded[0].after is not None
    assert recorded[0].after["status"] == "approved" and recorded[0].after["amount_cents"] == 80_000
    # And the contractor can now start.
    started = act(scene.sign_in(CONTRACTOR), world, order["id"], "status", status="in_progress")
    assert started.status_code == 200, started.text


def test_a_reason_is_optional_when_approving(scene: Scene, world: World, db_session: Session):
    _, estimate = held(scene, world, db_session)

    response = decide(scene.sign_in(OWNER), world, estimate["id"], "approve")

    assert response.status_code == 200
    assert response.json()["decision_reason"] is None


def test_the_owner_rejects_with_a_reason_and_the_work_stops(
    scene: Scene, world: World, db_session: Session
):
    order, estimate = held(scene, world, db_session)
    owner = scene.sign_in(OWNER)

    blank = decide(owner, world, estimate["id"], "reject", "   ")
    assert blank.status_code == 409
    assert read_work_order(scene.sign_in(MANAGER), world, order["id"])["status"] == (
        "awaiting_approval"
    )

    response = decide(owner, world, estimate["id"], "reject", "Too expensive. Get a second quote.")

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "rejected"
    after = read_work_order(scene.sign_in(MANAGER), world, order["id"])
    assert after["status"] == "on_hold"
    assert after["approval_hold"] is not None
    rejected = [e for e in after["history"] if e["kind"] == "estimate_rejected"]
    assert [(e["body"], e["author_name"]) for e in rejected] == [
        ("Too expensive. Get a second quote.", OWNER)
    ]
    assert move(scene.sign_in(MANAGER), world, order["id"], "in_progress").status_code == 409


def test_after_a_rejection_a_revised_estimate_can_be_decided_again(
    scene: Scene, world: World, db_session: Session
):
    order, first = held(scene, world, db_session, 80_000)
    decide(scene.sign_in(OWNER), world, first["id"], "reject", "Too much")
    manager = scene.sign_in(MANAGER)

    revised = quote(manager, world, order["id"], 65_000).json()

    assert revised["status"] == "awaiting_approval"
    second = revised["estimates"][0]
    assert second["version"] == 2 and second["status"] == "pending"
    assert decide(scene.sign_in(OWNER), world, second["id"], "approve").status_code == 200
    assert read_work_order(manager, world, order["id"])["status"] == "on_hold"
    # Approved, so the manager can now move the work on.
    assert move(manager, world, order["id"], "in_progress").status_code == 200


def test_after_a_rejection_a_cheaper_estimate_needs_no_decision(
    scene: Scene, world: World, db_session: Session
):
    order, first = held(scene, world, db_session, 80_000)
    decide(scene.sign_in(OWNER), world, first["id"], "reject", "Too much")

    revised = quote(scene.sign_in(MANAGER), world, order["id"], 45_000).json()

    assert revised["approval_hold"] is None
    assert move(scene.sign_in(MANAGER), world, order["id"], "in_progress").status_code == 200


def test_a_decision_is_made_once(scene: Scene, world: World, db_session: Session):
    _, estimate = held(scene, world, db_session)
    owner = scene.sign_in(OWNER)
    assert decide(owner, world, estimate["id"], "approve").status_code == 200

    again = decide(owner, world, estimate["id"], "reject", "Changed my mind")

    assert again.status_code == 409
    assert owner.get(approvals_url(world, estimate["id"])).json()["status"] == "approved"
    assert len(events(db_session, EventType.ESTIMATE_DECIDED)) == 1


def test_a_replaced_estimate_cannot_be_decided(scene: Scene, world: World, db_session: Session):
    order, old = held(scene, world, db_session, 80_000)
    quote(scene.sign_in(MANAGER), world, order["id"], 90_000)

    response = decide(scene.sign_in(OWNER), world, old["id"], "approve")

    assert response.status_code == 409
    assert read_work_order(scene.sign_in(MANAGER), world, order["id"])["status"] == (
        "awaiting_approval"
    )


def test_a_cancelled_work_order_cannot_be_decided(scene: Scene, world: World, db_session: Session):
    order, estimate = held(scene, world, db_session)
    move(scene.sign_in(MANAGER), world, order["id"], "cancelled")

    response = decide(scene.sign_in(OWNER), world, estimate["id"], "approve")

    assert response.status_code == 409
    listed = scene.sign_in(OWNER).get(approvals_url(world)).json()
    assert [item["decidable"] for item in listed] == [False]


def test_a_decision_must_be_approve_or_reject(scene: Scene, world: World, db_session: Session):
    _, estimate = held(scene, world, db_session)

    response = decide(scene.sign_in(OWNER), world, estimate["id"], "maybe")

    assert response.status_code == 422


def test_only_the_owner_of_that_property_can_decide(
    scene: Scene, world: World, db_session: Session
):
    order, estimate = held(scene, world, db_session)
    add_owner_account(db_session, world)
    own(scene, world, db_session, SECOND_OWNER, property_id=scene.oak["id"])

    # An owner of a different property cannot even see it.
    stranger = scene.sign_in(SECOND_OWNER)
    assert stranger.get(approvals_url(world, estimate["id"])).status_code == 404
    assert decide(stranger, world, estimate["id"]).status_code == 404
    assert stranger.get(approvals_url(world)).json() == []
    # Nor can anyone from another organization.
    elm_url = f"/api/organizations/{world.elm_id}/my-approvals/{estimate['id']}"
    assert scene.sign_in(OWNER).get(elm_url).status_code == 404
    assert read_work_order(scene.sign_in(MANAGER), world, order["id"])["status"] == (
        "awaiting_approval"
    )


@pytest.mark.parametrize("email", [MANAGER, ADMIN, RESIDENT, CONTRACTOR])
def test_only_property_owners_use_the_approval_workspace(
    scene: Scene, world: World, db_session: Session, email: str
):
    _, estimate = held(scene, world, db_session)
    client = scene.sign_in(email)

    assert client.get(approvals_url(world)).status_code == 403
    assert client.get(approvals_url(world, estimate["id"])).status_code == 403
    assert decide(client, world, estimate["id"]).status_code == 403


def test_nobody_decides_on_their_own_estimate(scene: Scene, world: World, db_session: Session):
    set_threshold(scene, world)
    # The manager also holds the property owner role, and owns the property.
    manager = db_session.scalars(
        select(Membership).join(Membership.user).where(Membership.user.has(email=MANAGER))
    ).one()
    manager.role_assignments.append(MembershipRole(role=Role.PROPERTY_OWNER))
    db_session.commit()
    own(scene, world, db_session, MANAGER)
    assigned, _ = dispatched(scene, world, db_session, accepted=True)
    held_order = quote(scene.sign_in(MANAGER), world, assigned["id"], 80_000).json()
    estimate = held_order["estimates"][0]

    own_decision = decide(scene.sign_in(MANAGER), world, estimate["id"])

    assert own_decision.status_code == 403
    listed = scene.sign_in(MANAGER).get(approvals_url(world)).json()
    assert [item["decidable"] for item in listed] == [False]
    assert read_work_order(scene.sign_in(MANAGER), world, assigned["id"])["status"] == (
        "awaiting_approval"
    )


# --- What the owner sees ----------------------------------------------------------------


def test_the_owner_lists_estimates_that_need_a_decision(
    scene: Scene, world: World, db_session: Session
):
    order = job(scene, world, db_session)
    manager = scene.sign_in(MANAGER)
    quote(manager, world, order["id"], 30_000)  # under the threshold: not the owner's to decide
    held_order = quote(manager, world, order["id"], 80_000).json()

    listed = scene.sign_in(OWNER).get(approvals_url(world))

    assert listed.status_code == 200
    (item,) = listed.json()
    assert item["id"] == held_order["estimates"][0]["id"]
    assert item["reference"] == order["reference"]
    assert item["property_name"] == "Maple Court"
    assert item["location"] == "1A"
    assert (item["amount_cents"], item["currency"], item["status"]) == (80_000, "USD", "pending")
    assert (item["current"], item["decidable"], item["version"]) == (True, True, 2)


def test_the_owner_sees_the_work_requested_and_every_decision(
    scene: Scene, world: World, db_session: Session
):
    order, first = held(scene, world, db_session, 80_000)
    owner = scene.sign_in(OWNER)
    decide(owner, world, first["id"], "reject", "Too much")
    revised = quote(scene.sign_in(MANAGER), world, order["id"], 65_000).json()

    detail = owner.get(approvals_url(world, revised["estimates"][0]["id"]))

    assert detail.status_code == 200
    body = detail.json()
    assert body["scope"] == order["scope"]
    assert body["street"] == "" and body["threshold_cents"] == THRESHOLD
    assert body["description"] == QUOTE
    assert [
        (v["version"], v["amount_cents"], v["status"], v["decided_by_name"], v["decision_reason"])
        for v in body["versions"]
    ] == [(2, 65_000, "pending", None, None), (1, 80_000, "rejected", OWNER, "Too much")]


def test_the_owner_never_receives_the_internal_record(
    scene: Scene, world: World, db_session: Session
):
    order = job(scene, world, db_session)
    manager = scene.sign_in(MANAGER)
    manager.post(
        wo_url(world, order["id"], "/notes"), json={"body": SECRET_NOTE, "visibility": "internal"}
    )
    held_order = quote(manager, world, order["id"], 80_000).json()
    owner = scene.sign_in(OWNER)

    detail = owner.get(approvals_url(world, held_order["estimates"][0]["id"]))
    listing = owner.get(approvals_url(world))

    for text in (detail.text, listing.text):
        assert SECRET_NOTE not in text
        for private in ("Rae Resident", "555-0111", RESIDENT, CONTRACTOR, "contractor"):
            assert private not in text
    assert not {
        "history",
        "attachments",
        "assignment",
        "linked_requests",
        "final_cost_cents",
    } & set(detail.json())


def test_an_owner_has_no_other_way_into_the_organization(
    scene: Scene, world: World, db_session: Session
):
    order = job(scene, world, db_session)
    owner = scene.sign_in(OWNER)

    for path in (
        f"/work-orders/{order['id']}",
        "/work-orders",
        "/requests",
        "/properties",
        "/my-jobs",
    ):
        assert owner.get(f"{world.base}{path}").status_code == 403
    assert quote(owner, world, order["id"], 100).status_code == 403


def test_residents_and_contractors_do_not_see_estimates(
    scene: Scene, world: World, db_session: Session
):
    order, _ = held(scene, world, db_session, 80_000)
    request_id = order["linked_requests"][0]["id"]

    resident = json.dumps(resident_view(scene, world, RESIDENT, request_id))
    contractor = json.dumps(read_job(scene.sign_in(CONTRACTOR), world, order["id"]))

    for text in (resident, contractor):
        assert "80000" not in text and "estimate" not in text.lower()


# --- Owners of a property ---------------------------------------------------------------


def test_an_administrator_chooses_a_propertys_owners(
    scene: Scene, world: World, db_session: Session
):
    add_owner_account(db_session, world)
    admin = scene.sign_in(ADMIN)
    url = f"{world.base}/properties/{scene.maple['id']}/owners"

    before = admin.get(url).json()
    assert {o["email"]: o["assigned"] for o in before} == {OWNER: False, SECOND_OWNER: False}

    own(scene, world, db_session, OWNER)

    after = admin.get(url).json()
    assert {o["email"]: o["assigned"] for o in after} == {OWNER: True, SECOND_OWNER: False}
    recorded = events(db_session, EventType.PROPERTY_OWNERS_CHANGED)
    assert len(recorded) == 1
    # Saving the same choice again changes nothing.
    own(scene, world, db_session, OWNER)
    assert len(events(db_session, EventType.PROPERTY_OWNERS_CHANGED)) == 1


def test_only_members_with_the_owner_role_can_be_given_a_property(
    scene: Scene, world: World, db_session: Session
):
    url = f"{world.base}/properties/{scene.maple['id']}/owners"

    response = scene.sign_in(ADMIN).put(
        url, json={"membership_ids": [membership_id(db_session, world, MANAGER)]}
    )

    assert response.status_code == 422


def test_only_administrators_manage_owners(scene: Scene, world: World, db_session: Session):
    url = f"{world.base}/properties/{scene.maple['id']}/owners"
    ids = [membership_id(db_session, world, OWNER)]

    for email in (MANAGER, OWNER, RESIDENT, CONTRACTOR):
        client = scene.sign_in(email)
        assert client.get(url).status_code == 403
        assert client.put(url, json={"membership_ids": ids}).status_code == 403
    assert scene.sign_in(ELM_ADMIN).get(url).status_code == 404


def test_an_owner_who_is_taken_off_a_property_loses_sight_of_its_estimates(
    scene: Scene, world: World, db_session: Session
):
    _, estimate = held(scene, world, db_session)
    owner = scene.sign_in(OWNER)
    assert owner.get(approvals_url(world, estimate["id"])).status_code == 200

    own(scene, world, db_session)

    assert owner.get(approvals_url(world, estimate["id"])).status_code == 404
    assert decide(owner, world, estimate["id"]).status_code == 404


def test_losing_the_owner_role_ends_ownership(scene: Scene, world: World, db_session: Session):
    _, estimate = held(scene, world, db_session)
    target = membership_id(db_session, world, OWNER)

    response = scene.sign_in(ADMIN).put(
        f"{world.base}/members/{target}/roles", json={"roles": ["resident"]}
    )

    assert response.status_code == 200, response.text
    # Whatever they hold later, the property is no longer theirs.
    scene.sign_in(ADMIN).put(
        f"{world.base}/members/{target}/roles", json={"roles": ["property_owner"]}
    )
    assert scene.sign_in(OWNER).get(approvals_url(world, estimate["id"])).status_code == 404


# --- Checking the cost against the estimate ---------------------------------------------


def finish(scene: Scene, world: World, order: dict[str, Any]) -> None:
    contractor = scene.sign_in(CONTRACTOR)
    assert act(contractor, world, order["id"], "status", status="in_progress").status_code == 200
    done = act(contractor, world, order["id"], "status", status="ready_for_review", note="Done")
    assert done.status_code == 200, done.text


def verify_cost(scene: Scene, world: World, order: dict[str, Any], cents: int) -> dict[str, Any]:
    response = scene.sign_in(MANAGER).post(
        wo_url(world, order["id"], "/verify"),
        json={"resolution": "Fixed", "final_cost_cents": cents},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_a_cost_within_the_approved_amount_raises_no_flag(
    scene: Scene, world: World, db_session: Session
):
    order, estimate = held(scene, world, db_session, 80_000)
    decide(scene.sign_in(OWNER), world, estimate["id"])
    finish(scene, world, order)

    body = verify_cost(scene, world, order, 75_000)

    assert body["cost_check"] == {
        "estimate_cents": 80_000,
        "over_estimate_cents": None,
        "above_approval": False,
    }


def test_a_cost_above_the_estimate_is_recorded_but_not_refused(
    scene: Scene, world: World, db_session: Session
):
    order, estimate = held(scene, world, db_session, 80_000)
    decide(scene.sign_in(OWNER), world, estimate["id"])
    finish(scene, world, order)

    body = verify_cost(scene, world, order, 95_000)

    assert body["status"] == "completed"
    assert body["cost_check"] == {
        "estimate_cents": 80_000,
        "over_estimate_cents": 15_000,
        "above_approval": True,
    }
    verified = [e for e in body["history"] if e["kind"] == "verified"][0]
    assert verified["details"]["cost_check"]["over_estimate_cents"] == 15_000
    recorded = events(db_session, EventType.WORK_ORDER_VERIFIED)
    assert recorded[0].after is not None
    assert recorded[0].after["cost_check"]["above_approval"] is True


def test_spending_above_the_threshold_with_no_estimate_is_flagged(
    scene: Scene, world: World, db_session: Session
):
    order = job(scene, world, db_session)
    finish(scene, world, order)

    body = verify_cost(scene, world, order, THRESHOLD + 1)

    assert body["cost_check"] == {
        "estimate_cents": None,
        "over_estimate_cents": None,
        "above_approval": True,
    }


def test_a_small_cost_with_no_estimate_is_not_flagged(
    scene: Scene, world: World, db_session: Session
):
    order = job(scene, world, db_session)
    finish(scene, world, order)

    body = verify_cost(scene, world, order, 1_000)

    assert body["cost_check"] == {
        "estimate_cents": None,
        "over_estimate_cents": None,
        "above_approval": False,
    }


def test_the_history_keeps_every_estimate_and_decision_in_order(
    scene: Scene, world: World, db_session: Session
):
    order, first = held(scene, world, db_session, 80_000)
    decide(scene.sign_in(OWNER), world, first["id"], "reject", "Too much")
    revised = quote(scene.sign_in(MANAGER), world, order["id"], 60_000).json()
    decide(scene.sign_in(OWNER), world, revised["estimates"][0]["id"], "approve", "Fine")

    body = read_work_order(scene.sign_in(MANAGER), world, order["id"])

    kinds = [entry["kind"] for entry in body["history"] if entry["kind"].startswith("estimate_")]
    assert kinds == [
        "estimate_submitted",
        "estimate_rejected",
        "estimate_submitted",
        "estimate_approved",
    ]
    db_session.expire_all()
    stored = db_session.scalars(
        select(WorkOrderEntry).where(
            WorkOrderEntry.work_order_id == uuid.UUID(order["id"]),
            WorkOrderEntry.kind == EntryKind.ESTIMATE_APPROVED,
        )
    ).all()
    assert len(stored) == 1


def test_estimate_times_are_stored_in_utc(scene: Scene, world: World, db_session: Session):
    _, estimate = held(scene, world, db_session)
    decide(scene.sign_in(OWNER), world, estimate["id"])
    db_session.expire_all()

    from app.models import Estimate

    saved = db_session.scalars(select(Estimate)).one()

    assert saved.status == EstimateStatus.APPROVED
    assert saved.decided_at is not None and saved.decided_at.utcoffset() is not None
    assert saved.decided_at.utcoffset().total_seconds() == 0  # type: ignore[union-attr]
    assert saved.created_at <= utc_now()


def test_rejected_estimates_do_not_change_what_the_resident_is_told(
    scene: Scene, world: World, db_session: Session
):
    order, estimate = held(scene, world, db_session)
    request_id = order["linked_requests"][0]["id"]
    decide(scene.sign_in(OWNER), world, estimate["id"], "reject", "No")

    assert read_request(scene.sign_in(MANAGER), world, request_id)["status"] == "in_progress"
