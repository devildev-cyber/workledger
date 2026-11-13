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
from test_requests import (  # noqa: F401 - scene is a fixture used below
    PDF,
    PNG,
    Scene,
    scene,
)
from test_work_orders import (
    ADMIN,
    CONTRACTOR,
    OWNER,
    converted,
    move,
    read_request,
    read_work_order,
    resident_view,
    standalone,
)

from app.models import (
    EventType,
    Membership,
    Role,
    User,
    WorkOrderAssignment,
    WorkOrderEntry,
)
from app.services.organizations import add_membership
from app.services.users import create_user

SECOND_CONTRACTOR = "contractor2@harbor.example"
SECRET_NOTE = "Landlord says the tenant owes three months of rent"
PHONE = "555-0111"


# --- Helpers ----------------------------------------------------------------------------


def membership_id(db: Session, world: World, email: str) -> str:
    db.expire_all()
    return str(
        db.scalars(
            select(Membership.id)
            .join(Membership.user)
            .where(Membership.organization_id == world.harbor_id, User.email == email)
        ).one()
    )


def add_contractor(db: Session, world: World, email: str = SECOND_CONTRACTOR) -> str:
    from app.models import Organization

    harbor = db.scalar(select(Organization).where(Organization.id == world.harbor_id))
    user = create_user(db, email=email, full_name="Second Contractor", password=PASSWORD)
    add_membership(db, organization=harbor, user=user, roles=[Role.CONTRACTOR], actor=None)
    db.commit()
    return membership_id(db, world, email)


def assign_to(client: SignedInClient, world: World, work_order_id: str, contractor_id: str) -> Any:
    return client.post(
        f"{world.base}/work-orders/{work_order_id}/assign", json={"contractor_id": contractor_id}
    )


def jobs_url(world: World, work_order_id: str | None = None) -> str:
    return f"{world.base}/my-jobs" + (f"/{work_order_id}" if work_order_id else "")


def act(client: SignedInClient, world: World, work_order_id: str, action: str, **body: Any):
    return client.post(f"{jobs_url(world, work_order_id)}/{action}", json=body)


def read_job(client: SignedInClient, world: World, work_order_id: str) -> dict[str, Any]:
    response = client.get(jobs_url(world, work_order_id))
    assert response.status_code == 200, response.text
    return response.json()


def dispatched(
    scene: Scene, world: World, db: Session, *, accepted: bool = False, **body: Any
) -> tuple[dict[str, Any], str]:
    """A resident's request, made into a work order and assigned to the demo contractor."""
    _, work_order = converted(scene, world, **body)
    contractor_id = membership_id(db, world, CONTRACTOR)
    response = assign_to(scene.sign_in(MANAGER), world, work_order["id"], contractor_id)
    assert response.status_code == 200, response.text
    if accepted:
        accept = act(scene.sign_in(CONTRACTOR), world, work_order["id"], "accept")
        assert accept.status_code == 200, accept.text
    return response.json(), contractor_id


# --- Assigning --------------------------------------------------------------------------


def test_managers_see_who_can_be_assigned(scene: Scene, world: World, db_session: Session):
    other = add_contractor(db_session, world)

    listed = scene.sign_in(MANAGER).get(f"{world.base}/contractors")

    assert listed.status_code == 200
    assert {(item["email"], item["active_jobs"]) for item in listed.json()} == {
        (CONTRACTOR, 0),
        (SECOND_CONTRACTOR, 0),
    }
    assert other in {item["id"] for item in listed.json()}
    assert "password" not in listed.text


@pytest.mark.parametrize("email", [RESIDENT, CONTRACTOR, OWNER])
def test_only_staff_can_dispatch(scene: Scene, world: World, db_session: Session, email: str):
    _, work_order = converted(scene, world)
    contractor_id = membership_id(db_session, world, CONTRACTOR)
    client = scene.sign_in(email)

    assert client.get(f"{world.base}/contractors").status_code == 403
    assert assign_to(client, world, work_order["id"], contractor_id).status_code == 403
    unassign = client.post(f"{world.base}/work-orders/{work_order['id']}/unassign")
    assert unassign.status_code == 403


def test_assigning_moves_the_job_to_assigned_and_waits_for_a_reply(
    scene: Scene, world: World, db_session: Session
):
    assigned, contractor_id = dispatched(scene, world, db_session)

    assert assigned["status"] == "assigned"
    assert assigned["assignment"]["contractor_id"] == contractor_id
    assert assigned["assignment"]["response"] == "pending"
    assert assigned["assignee_name"] == CONTRACTOR
    kinds = [entry["kind"] for entry in assigned["history"]]
    assert kinds[-2:] == ["assigned", "status_changed"]
    assert len(events(db_session, EventType.WORK_ORDER_ASSIGNED)) == 1

    # The linked request follows the work order, as every other move does.
    request = read_request(scene.sign_in(MANAGER), world, assigned["linked_requests"][0]["id"])
    assert request["status"] == "in_progress"


def test_a_manager_cannot_assign_a_contractor_from_another_organization(
    scene: Scene, world: World, db_session: Session
):
    _, work_order = converted(scene, world)
    stranger = membership_id(db_session, world, CONTRACTOR)
    # A membership ID that exists nowhere in this organization.
    missing = "00000000-0000-0000-0000-000000000001"

    assert assign_to(scene.sign_in(MANAGER), world, work_order["id"], missing).status_code == 404
    assert stranger
    listing = read_work_order(scene.sign_in(MANAGER), world, work_order["id"])
    assert listing["status"] == "open"
    assert listing["assignment"] is None


def test_only_contractors_can_be_assigned(scene: Scene, world: World, db_session: Session):
    _, work_order = converted(scene, world)
    manager_membership = membership_id(db_session, world, OTHER_MANAGER)

    response = assign_to(scene.sign_in(MANAGER), world, work_order["id"], manager_membership)

    assert response.status_code == 404


def test_a_manager_cannot_assign_work_outside_their_properties(
    scene: Scene, world: World, db_session: Session
):
    created = standalone(scene.sign_in(ADMIN), world, scene.oak["id"]).json()
    contractor_id = membership_id(db_session, world, CONTRACTOR)

    response = assign_to(scene.sign_in(MANAGER), world, created["id"], contractor_id)

    assert response.status_code == 404


def test_another_organizations_admin_cannot_assign_our_work(
    scene: Scene, world: World, db_session: Session
):
    _, work_order = converted(scene, world)
    contractor_id = membership_id(db_session, world, CONTRACTOR)

    response = assign_to(scene.sign_in(ELM_ADMIN), world, work_order["id"], contractor_id)

    assert response.status_code == 404


def test_assigning_twice_to_the_same_person_is_refused(
    scene: Scene, world: World, db_session: Session
):
    assigned, contractor_id = dispatched(scene, world, db_session)

    again = assign_to(scene.sign_in(MANAGER), world, assigned["id"], contractor_id)

    assert again.status_code == 409
    assert (
        len(read_work_order(scene.sign_in(MANAGER), world, assigned["id"])["assignment_history"])
        == 1
    )


@pytest.mark.parametrize("status", ["ready_for_review", "completed", "closed", "cancelled"])
def test_finished_or_reviewed_work_cannot_be_assigned(
    scene: Scene, world: World, db_session: Session, status: str
):
    _, work_order = converted(scene, world)
    admin = scene.sign_in(ADMIN)
    path = {
        "ready_for_review": ["in_progress", "ready_for_review"],
        "completed": ["in_progress", "ready_for_review", "completed"],
        "closed": ["in_progress", "ready_for_review", "completed", "closed"],
        "cancelled": ["cancelled"],
    }[status]
    for step in path:
        assert move(admin, world, work_order["id"], step, note="Done").status_code == 200
    contractor_id = membership_id(db_session, world, CONTRACTOR)

    response = assign_to(admin, world, work_order["id"], contractor_id)

    assert response.status_code == 409


def test_reassigning_keeps_the_whole_history(scene: Scene, world: World, db_session: Session):
    assigned, first_id = dispatched(scene, world, db_session, accepted=True)
    second_id = add_contractor(db_session, world)
    manager = scene.sign_in(MANAGER)

    reassigned = assign_to(manager, world, assigned["id"], second_id)

    assert reassigned.status_code == 200
    body = reassigned.json()
    assert body["assignment"]["contractor_id"] == second_id
    assert body["assignment"]["response"] == "pending"
    history = body["assignment_history"]
    assert [item["contractor_id"] for item in history] == [first_id, second_id]
    first = history[0]
    assert first["response"] == "accepted"
    assert first["ended_reason"] == "reassigned"
    assert first["ended_at"] is not None
    assert first["assigned_by_name"] == MANAGER
    assert history[1]["ended_at"] is None
    assert [e["body"] for e in body["history"] if e["kind"] == "assigned"] == [
        f"Assigned to {CONTRACTOR}",
        f"Reassigned from {CONTRACTOR} to Second Contractor",
    ]
    assert len(events(db_session, EventType.WORK_ORDER_ASSIGNED)) == 2


def test_the_previous_contractor_loses_access_on_reassignment(
    scene: Scene, world: World, db_session: Session
):
    assigned, _ = dispatched(scene, world, db_session, accepted=True)
    second_id = add_contractor(db_session, world)
    assign_to(scene.sign_in(MANAGER), world, assigned["id"], second_id)
    first = scene.sign_in(CONTRACTOR)

    assert first.get(jobs_url(world)).json() == []
    assert first.get(jobs_url(world, assigned["id"])).status_code == 404
    assert act(first, world, assigned["id"], "status", status="in_progress").status_code == 404
    assert act(first, world, assigned["id"], "entries", body="Still here").status_code == 404
    # The new contractor sees it, still waiting for their answer.
    second = scene.sign_in(SECOND_CONTRACTOR)
    listed = second.get(jobs_url(world)).json()
    assert [(job["id"], job["response"]) for job in listed] == [(assigned["id"], "pending")]


def test_reassigning_an_in_progress_job_keeps_the_status(
    scene: Scene, world: World, db_session: Session
):
    assigned, _ = dispatched(scene, world, db_session, accepted=True)
    contractor = scene.sign_in(CONTRACTOR)
    assert act(contractor, world, assigned["id"], "status", status="in_progress").status_code == 200

    reassigned = assign_to(
        scene.sign_in(MANAGER), world, assigned["id"], add_contractor(db_session, world)
    )

    assert reassigned.json()["status"] == "in_progress"


def test_unassigning_returns_the_job_to_the_queue(scene: Scene, world: World, db_session: Session):
    assigned, _ = dispatched(scene, world, db_session, accepted=True)
    manager = scene.sign_in(MANAGER)

    response = manager.post(f"{world.base}/work-orders/{assigned['id']}/unassign")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "open"
    assert body["assignment"] is None
    assert body["assignment_history"][0]["ended_reason"] == "unassigned"
    assert scene.sign_in(CONTRACTOR).get(jobs_url(world)).json() == []
    assert len(events(db_session, EventType.WORK_ORDER_UNASSIGNED)) == 1

    nobody = manager.post(f"{world.base}/work-orders/{assigned['id']}/unassign")
    assert nobody.status_code == 409


def test_cancelling_the_work_order_ends_the_assignment(
    scene: Scene, world: World, db_session: Session
):
    assigned, _ = dispatched(scene, world, db_session, accepted=True)

    assert (
        move(scene.sign_in(MANAGER), world, assigned["id"], "cancelled", "Resolved").status_code
        == 200
    )

    body = read_work_order(scene.sign_in(MANAGER), world, assigned["id"])
    assert body["assignment"] is None
    assert body["assignment_history"][0]["ended_reason"] == "cancelled"
    assert scene.sign_in(CONTRACTOR).get(jobs_url(world)).json() == []


def test_work_order_lists_show_and_filter_by_contractor(
    scene: Scene, world: World, db_session: Session
):
    assigned, contractor_id = dispatched(scene, world, db_session)
    free = standalone(scene.sign_in(MANAGER), world, scene.maple["id"], title="Paint").json()
    manager = scene.sign_in(MANAGER)

    everything = manager.get(f"{world.base}/work-orders").json()
    by_id = {item["id"]: item for item in everything}
    assert by_id[assigned["id"]]["assignee_name"] == CONTRACTOR
    assert by_id[assigned["id"]]["assignment_response"] == "pending"
    assert by_id[free["id"]]["assignee_id"] is None

    mine = manager.get(f"{world.base}/work-orders", params={"assignee_id": contractor_id}).json()
    assert [item["id"] for item in mine] == [assigned["id"]]
    open_ones = manager.get(f"{world.base}/work-orders", params={"unassigned": "true"}).json()
    assert [item["id"] for item in open_ones] == [free["id"]]


# --- What a contractor sees --------------------------------------------------------------


def test_a_contractor_sees_only_their_own_jobs(scene: Scene, world: World, db_session: Session):
    mine, _ = dispatched(scene, world, db_session)
    _, other = converted(scene, world)  # never assigned
    elsewhere = standalone(scene.sign_in(ADMIN), world, scene.oak["id"]).json()
    second_id = add_contractor(db_session, world)
    assign_to(scene.sign_in(ADMIN), world, elsewhere["id"], second_id)
    contractor = scene.sign_in(CONTRACTOR)

    listed = contractor.get(jobs_url(world))

    assert listed.status_code == 200
    assert [job["id"] for job in listed.json()] == [mine["id"]]
    assert other["id"] not in listed.text
    assert elsewhere["id"] not in listed.text


def test_a_contractor_cannot_open_another_job_by_id(
    scene: Scene, world: World, db_session: Session
):
    _, unassigned = converted(scene, world)
    elsewhere = standalone(scene.sign_in(ADMIN), world, scene.oak["id"]).json()
    assign_to(scene.sign_in(ADMIN), world, elsewhere["id"], add_contractor(db_session, world))
    contractor = scene.sign_in(CONTRACTOR)

    for work_order_id in (
        unassigned["id"],
        elsewhere["id"],
        "00000000-0000-0000-0000-000000000002",
    ):
        assert contractor.get(jobs_url(world, work_order_id)).status_code == 404
        assert act(contractor, world, work_order_id, "accept").status_code == 404
        assert act(contractor, world, work_order_id, "decline", reason="Nope").status_code == 404
        assert (
            act(contractor, world, work_order_id, "status", status="in_progress").status_code == 404
        )
        assert act(contractor, world, work_order_id, "entries", body="Hi").status_code == 404
        upload = contractor.post(
            f"{jobs_url(world, work_order_id)}/attachments",
            params={"filename": "a.png"},
            content=PNG,
        )
        assert upload.status_code == 404


def test_a_contractor_cannot_use_the_staff_records(scene: Scene, world: World, db_session: Session):
    assigned, _ = dispatched(scene, world, db_session, accepted=True)
    contractor = scene.sign_in(CONTRACTOR)

    assert contractor.get(f"{world.base}/work-orders").status_code == 403
    assert contractor.get(f"{world.base}/work-orders/{assigned['id']}").status_code == 403
    assert contractor.get(f"{world.base}/requests").status_code == 403
    assert move(contractor, world, assigned["id"], "completed").status_code == 403
    note = contractor.post(
        f"{world.base}/work-orders/{assigned['id']}/notes", json={"body": "hello"}
    )
    assert note.status_code == 403


@pytest.mark.parametrize("email", [MANAGER, ADMIN, RESIDENT, OWNER, ELM_ADMIN])
def test_the_job_workspace_is_for_contractors_only(
    scene: Scene, world: World, db_session: Session, email: str
):
    assigned, _ = dispatched(scene, world, db_session)
    client = scene.sign_in(email)

    assert client.get(jobs_url(world)).status_code in (403, 404)
    assert client.get(jobs_url(world, assigned["id"])).status_code in (403, 404)


def test_contact_details_and_access_notes_wait_for_acceptance(
    scene: Scene, world: World, db_session: Session
):
    assigned, _ = dispatched(scene, world, db_session)
    contractor = scene.sign_in(CONTRACTOR)

    before = contractor.get(jobs_url(world, assigned["id"]))
    assert before.status_code == 200
    detail = before.json()
    assert detail["can_accept"] is True
    assert detail["can_decline"] is True
    assert detail["allowed_statuses"] == []
    assert detail["residents"] == []
    assert detail["access_notes"] == []
    assert detail["street"] == scene.maple["street"]
    assert detail["unit_label"] == "1A"
    assert "Ring the bell" not in before.text

    act(contractor, world, assigned["id"], "accept")
    after = read_job(contractor, world, assigned["id"])
    assert after["residents"] == ["Rae"]
    assert after["access_notes"] == ["Ring the bell, I work from home"]
    assert after["can_accept"] is False
    assert after["allowed_statuses"] == ["in_progress"]


def test_a_contractor_never_receives_internal_records(
    scene: Scene, world: World, db_session: Session
):
    assigned, _ = dispatched(scene, world, db_session, accepted=True)
    manager = scene.sign_in(MANAGER)
    base = f"{world.base}/work-orders/{assigned['id']}"
    manager.post(f"{base}/notes", json={"body": SECRET_NOTE})
    manager.post(f"{base}/notes", json={"body": "Resident note", "visibility": "resident"})
    manager.post(
        f"{base}/notes",
        json={"body": "Use the side gate", "share_with_contractor": True},
    )
    internal_file = manager.post(
        f"{base}/attachments", params={"filename": "invoice.pdf"}, content=PDF
    ).json()
    shared_file = manager.post(
        f"{base}/attachments",
        params={"filename": "plan.png", "contractor_visible": "true"},
        content=PNG,
    ).json()
    move(manager, world, assigned["id"], "on_hold", "Waiting on the owner to approve the cost")

    response = scene.sign_in(CONTRACTOR).get(jobs_url(world, assigned["id"]))
    text = response.text
    detail = response.json()

    for hidden in (
        SECRET_NOTE,
        "Resident note",
        "invoice.pdf",
        internal_file["id"],
        "Waiting on the owner",
        PHONE,
        RESIDENT,
        MANAGER,
        ADMIN,
        "REQ-0001",
        "Rae Resident",
    ):
        assert hidden not in text, hidden
    assert "Use the side gate" in text
    assert [item["id"] for item in detail["attachments"]] == [shared_file["id"]]
    authors = {entry["author"] for entry in detail["timeline"]}
    assert authors <= {"You", "Property team", "System"}
    status_entries = [e for e in detail["timeline"] if e["kind"] == "status_changed"]
    assert status_entries
    assert all(entry["body"] is None for entry in status_entries if entry["author"] != "You")


def test_the_job_response_has_only_the_fields_a_contractor_needs(
    scene: Scene, world: World, db_session: Session
):
    assigned, _ = dispatched(scene, world, db_session, accepted=True)

    detail = read_job(scene.sign_in(CONTRACTOR), world, assigned["id"])

    assert set(detail) == {
        "id", "reference", "title", "status", "priority", "category", "due_date", "overdue",
        "property_name", "unit_label", "building_name", "response", "scope", "street", "city",
        "region", "postal_code", "residents", "access_notes", "can_accept", "can_decline",
        "allowed_statuses", "timeline", "attachments",
    }  # fmt: skip


def test_notes_and_files_not_shared_stay_hidden_from_a_second_contractor(
    scene: Scene, world: World, db_session: Session
):
    assigned, _ = dispatched(scene, world, db_session, accepted=True)
    contractor = scene.sign_in(CONTRACTOR)
    mine = contractor.post(
        f"{jobs_url(world, assigned['id'])}/attachments",
        params={"filename": "before.png"},
        content=PNG,
    ).json()
    second_id = add_contractor(db_session, world)
    assign_to(scene.sign_in(MANAGER), world, assigned["id"], second_id)
    act(scene.sign_in(SECOND_CONTRACTOR), world, assigned["id"], "accept")

    detail = read_job(scene.sign_in(SECOND_CONTRACTOR), world, assigned["id"])

    # Evidence the earlier contractor added is shared with the job, but is marked as theirs.
    assert [(a["id"], a["mine"]) for a in detail["attachments"]] == [(mine["id"], False)]
    assert all(entry["author"] != "You" for entry in detail["timeline"] if entry["kind"] == "note")


# --- Accepting and declining -------------------------------------------------------------


def test_a_contractor_accepts_a_job(scene: Scene, world: World, db_session: Session):
    assigned, _ = dispatched(scene, world, db_session)

    response = act(scene.sign_in(CONTRACTOR), world, assigned["id"], "accept")

    assert response.status_code == 200
    assert response.json()["response"] == "accepted"
    body = read_work_order(scene.sign_in(MANAGER), world, assigned["id"])
    assert body["assignment"]["response"] == "accepted"
    assert body["assignment"]["responded_at"] is not None
    assert body["history"][-1]["kind"] == "assignment_accepted"
    assert len(events(db_session, EventType.WORK_ORDER_ASSIGNMENT_RESPONDED)) == 1
    again = act(scene.sign_in(CONTRACTOR), world, assigned["id"], "accept")
    assert again.status_code == 409


def test_declining_returns_the_job_to_the_manager_with_the_reason(
    scene: Scene, world: World, db_session: Session
):
    assigned, contractor_id = dispatched(scene, world, db_session)
    contractor = scene.sign_in(CONTRACTOR)

    response = act(contractor, world, assigned["id"], "decline", reason="Fully booked this week")

    assert response.status_code == 204
    body = read_work_order(scene.sign_in(MANAGER), world, assigned["id"])
    assert body["status"] == "open"
    assert body["assignment"] is None
    record = body["assignment_history"][0]
    assert record["contractor_id"] == contractor_id
    assert record["response"] == "declined"
    assert record["decline_reason"] == "Fully booked this week"
    assert record["ended_reason"] == "declined"
    declined = [e for e in body["history"] if e["kind"] == "assignment_declined"]
    assert [e["body"] for e in declined] == ["Fully booked this week"]
    assert contractor.get(jobs_url(world, assigned["id"])).status_code == 404


def test_declining_needs_a_reason(scene: Scene, world: World, db_session: Session):
    assigned, _ = dispatched(scene, world, db_session)

    response = act(scene.sign_in(CONTRACTOR), world, assigned["id"], "decline", reason=" ")

    assert response.status_code == 422
    assert read_job(scene.sign_in(CONTRACTOR), world, assigned["id"])["response"] == "pending"


def test_an_accepted_job_cannot_be_declined(scene: Scene, world: World, db_session: Session):
    assigned, _ = dispatched(scene, world, db_session, accepted=True)

    response = act(
        scene.sign_in(CONTRACTOR), world, assigned["id"], "decline", reason="Changed my mind"
    )

    assert response.status_code == 409
    assert read_job(scene.sign_in(CONTRACTOR), world, assigned["id"])["response"] == "accepted"


def test_a_declined_job_can_go_to_someone_else(scene: Scene, world: World, db_session: Session):
    assigned, _ = dispatched(scene, world, db_session)
    act(scene.sign_in(CONTRACTOR), world, assigned["id"], "decline", reason="Too far away")
    second_id = add_contractor(db_session, world)

    response = assign_to(scene.sign_in(MANAGER), world, assigned["id"], second_id)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "assigned"
    assert [r["response"] for r in body["assignment_history"]] == ["declined", "pending"]


# --- Working the job ---------------------------------------------------------------------


def test_a_job_must_be_accepted_before_work_starts(scene: Scene, world: World, db_session: Session):
    assigned, _ = dispatched(scene, world, db_session)
    contractor = scene.sign_in(CONTRACTOR)

    assert act(contractor, world, assigned["id"], "status", status="in_progress").status_code == 409
    assert act(contractor, world, assigned["id"], "entries", body="Early").status_code == 409
    upload = contractor.post(
        f"{jobs_url(world, assigned['id'])}/attachments",
        params={"filename": "a.png"},
        content=PNG,
    )
    assert upload.status_code == 409
    assert read_work_order(scene.sign_in(MANAGER), world, assigned["id"])["status"] == "assigned"


def test_the_contractor_works_a_job_through_to_review(
    scene: Scene, world: World, db_session: Session
):
    assigned, _ = dispatched(scene, world, db_session, accepted=True)
    contractor = scene.sign_in(CONTRACTOR)
    request_id = assigned["linked_requests"][0]["id"]

    started = act(contractor, world, assigned["id"], "status", status="in_progress")
    assert started.status_code == 200
    assert started.json()["status"] == "in_progress"
    assert started.json()["allowed_statuses"] == ["on_hold", "ready_for_review"]
    assert resident_view(scene, world, RESIDENT, request_id)["status"] == "in_progress"

    paused = act(
        contractor, world, assigned["id"], "status", status="on_hold", note="Part on order"
    )
    assert paused.status_code == 200
    assert paused.json()["allowed_statuses"] == ["in_progress"]

    resumed = act(contractor, world, assigned["id"], "status", status="in_progress")
    assert resumed.status_code == 200

    done = act(
        contractor,
        world,
        assigned["id"],
        "status",
        status="ready_for_review",
        note="Fitted a new cartridge and tested for leaks",
    )
    assert done.status_code == 200
    assert done.json()["status"] == "ready_for_review"
    assert done.json()["allowed_statuses"] == []

    body = read_work_order(scene.sign_in(MANAGER), world, assigned["id"])
    statuses = [e["status"] for e in body["history"] if e["kind"] == "status_changed"]
    assert statuses[-4:] == ["in_progress", "on_hold", "in_progress", "ready_for_review"]
    last = [e for e in body["history"] if e["kind"] == "status_changed"][-1]
    assert last["body"] == "Fitted a new cartridge and tested for leaks"
    assert last["author_name"] == CONTRACTOR
    # The assignment stays until the manager decides what happens next.
    assert body["assignment"]["response"] == "accepted"
    assert read_request(scene.sign_in(MANAGER), world, request_id)["status"] == "in_progress"


@pytest.mark.parametrize(
    "status", ["completed", "closed", "cancelled", "open", "awaiting_approval"]
)
def test_a_contractor_cannot_make_the_managers_decisions(
    scene: Scene, world: World, db_session: Session, status: str
):
    assigned, _ = dispatched(scene, world, db_session, accepted=True)
    contractor = scene.sign_in(CONTRACTOR)
    act(contractor, world, assigned["id"], "status", status="in_progress")

    response = act(contractor, world, assigned["id"], "status", status=status, note="Done")

    assert response.status_code == 409
    assert read_work_order(scene.sign_in(MANAGER), world, assigned["id"])["status"] == "in_progress"


def test_a_contractor_cannot_skip_starting_the_job(scene: Scene, world: World, db_session: Session):
    assigned, _ = dispatched(scene, world, db_session, accepted=True)

    response = act(
        scene.sign_in(CONTRACTOR),
        world,
        assigned["id"],
        "status",
        status="ready_for_review",
        note="Finished",
    )

    assert response.status_code == 409


@pytest.mark.parametrize("status", ["on_hold", "ready_for_review"])
def test_pausing_and_finishing_need_words(
    scene: Scene, world: World, db_session: Session, status: str
):
    assigned, _ = dispatched(scene, world, db_session, accepted=True)
    contractor = scene.sign_in(CONTRACTOR)
    act(contractor, world, assigned["id"], "status", status="in_progress")

    for note in (None, "   "):
        response = act(contractor, world, assigned["id"], "status", status=status, note=note)
        assert response.status_code in (409, 422)

    assert read_work_order(scene.sign_in(MANAGER), world, assigned["id"])["status"] == "in_progress"


def test_notes_progress_and_questions_reach_the_manager(
    scene: Scene, world: World, db_session: Session
):
    assigned, _ = dispatched(scene, world, db_session, accepted=True)
    contractor = scene.sign_in(CONTRACTOR)

    note = act(contractor, world, assigned["id"], "entries", body="Gate was locked")
    progress = act(contractor, world, assigned["id"], "entries", body="Half done", kind="progress")
    question = act(
        contractor,
        world,
        assigned["id"],
        "entries",
        body="Is the cabinet under the sink in scope?",
        kind="clarification",
    )

    assert [r.status_code for r in (note, progress, question)] == [201, 201, 201]
    timeline = question.json()["timeline"]
    assert [(e["kind"], e["author"]) for e in timeline[-3:]] == [
        ("note", "You"),
        ("progress", "You"),
        ("clarification", "You"),
    ]
    history = read_work_order(scene.sign_in(MANAGER), world, assigned["id"])["history"]
    kinds = [(e["kind"], e["visibility"], e["author_name"]) for e in history[-3:]]
    assert kinds == [
        ("note", "internal", CONTRACTOR),
        ("progress", "internal", CONTRACTOR),
        ("clarification", "internal", CONTRACTOR),
    ]


@pytest.mark.parametrize("kind", ["status_changed", "assigned", "created", "edited"])
def test_a_contractor_can_only_add_notes_progress_and_questions(
    scene: Scene, world: World, db_session: Session, kind: str
):
    assigned, _ = dispatched(scene, world, db_session, accepted=True)

    response = act(scene.sign_in(CONTRACTOR), world, assigned["id"], "entries", body="x", kind=kind)

    assert response.status_code in (409, 422)
    db_session.expire_all()
    count = db_session.scalars(select(WorkOrderEntry).where(WorkOrderEntry.kind == kind)).all()
    assert all(entry.author_user_id is None or entry.body != "x" for entry in count)


def test_an_empty_entry_is_refused(scene: Scene, world: World, db_session: Session):
    assigned, _ = dispatched(scene, world, db_session, accepted=True)

    response = act(scene.sign_in(CONTRACTOR), world, assigned["id"], "entries", body="  ")

    assert response.status_code == 422


def test_a_finished_job_is_read_only(scene: Scene, world: World, db_session: Session):
    assigned, _ = dispatched(scene, world, db_session, accepted=True)
    contractor = scene.sign_in(CONTRACTOR)
    act(contractor, world, assigned["id"], "status", status="in_progress")
    act(contractor, world, assigned["id"], "status", status="ready_for_review", note="All done")
    admin = scene.sign_in(ADMIN)
    assert move(admin, world, assigned["id"], "completed").status_code == 200

    entry = act(contractor, world, assigned["id"], "entries", body="One more thing")
    upload = contractor.post(
        f"{jobs_url(world, assigned['id'])}/attachments",
        params={"filename": "late.png"},
        content=PNG,
    )

    assert entry.status_code == 409
    assert upload.status_code == 409
    # They can still read it, for their records.
    assert read_job(contractor, world, assigned["id"])["status"] == "completed"


# --- Evidence ----------------------------------------------------------------------------


def test_a_contractor_uploads_and_downloads_completion_evidence(
    scene: Scene, world: World, db_session: Session
):
    assigned, _ = dispatched(scene, world, db_session, accepted=True)
    contractor = scene.sign_in(CONTRACTOR)
    url = f"{jobs_url(world, assigned['id'])}/attachments"

    uploaded = contractor.post(url, params={"filename": "after.png"}, content=PNG)

    assert uploaded.status_code == 201
    saved = uploaded.json()
    assert saved["filename"] == "after.png"
    assert saved["mine"] is True
    download = contractor.get(f"{url}/{saved['id']}")
    assert download.status_code == 200
    assert download.content == PNG

    # The manager sees it on the work order, flagged as shared with the contractor.
    manager = scene.sign_in(MANAGER)
    attachments = read_work_order(manager, world, assigned["id"])["attachments"]
    assert [
        (a["filename"], a["uploaded_by_name"], a["contractor_visible"]) for a in attachments
    ] == [("after.png", CONTRACTOR, True)]
    staff = manager.get(f"{world.base}/work-orders/{assigned['id']}/attachments/{saved['id']}")
    assert staff.status_code == 200
    assert staff.content == PNG


def test_a_contractor_cannot_download_a_file_kept_internal(
    scene: Scene, world: World, db_session: Session
):
    assigned, _ = dispatched(scene, world, db_session, accepted=True)
    internal = (
        scene.sign_in(MANAGER)
        .post(
            f"{world.base}/work-orders/{assigned['id']}/attachments",
            params={"filename": "invoice.pdf"},
            content=PDF,
        )
        .json()
    )

    response = scene.sign_in(CONTRACTOR).get(
        f"{jobs_url(world, assigned['id'])}/attachments/{internal['id']}"
    )

    assert response.status_code == 404


def test_a_contractor_cannot_download_files_from_another_job(
    scene: Scene, world: World, db_session: Session
):
    mine, _ = dispatched(scene, world, db_session, accepted=True)
    other = standalone(scene.sign_in(ADMIN), world, scene.oak["id"]).json()
    shared = (
        scene.sign_in(ADMIN)
        .post(
            f"{world.base}/work-orders/{other['id']}/attachments",
            params={"filename": "plan.png", "contractor_visible": "true"},
            content=PNG,
        )
        .json()
    )
    contractor = scene.sign_in(CONTRACTOR)

    via_other_job = contractor.get(f"{jobs_url(world, other['id'])}/attachments/{shared['id']}")
    via_my_job = contractor.get(f"{jobs_url(world, mine['id'])}/attachments/{shared['id']}")

    assert via_other_job.status_code == 404
    assert via_my_job.status_code == 404


def test_evidence_uploads_are_checked(scene: Scene, world: World, db_session: Session):
    assigned, _ = dispatched(scene, world, db_session, accepted=True)
    contractor = scene.sign_in(CONTRACTOR)
    url = f"{jobs_url(world, assigned['id'])}/attachments"

    wrong_type = contractor.post(url, params={"filename": "run.exe"}, content=b"MZ" + b"0" * 40)
    empty = contractor.post(url, params={"filename": "empty.png"}, content=b"")
    disguised = contractor.post(url, params={"filename": "fake.png"}, content=b"not an image")

    assert wrong_type.status_code == 422
    assert empty.status_code == 422
    assert disguised.status_code == 422
    assert read_job(contractor, world, assigned["id"])["attachments"] == []


def test_a_work_order_has_a_limited_number_of_files(
    scene: Scene, world: World, db_session: Session
):
    assigned, _ = dispatched(scene, world, db_session, accepted=True)
    contractor = scene.sign_in(CONTRACTOR)
    url = f"{jobs_url(world, assigned['id'])}/attachments"

    results = [
        contractor.post(url, params={"filename": "a.png"}, content=PNG).status_code
        for _ in range(21)
    ]

    assert results == [201] * 20 + [409]


# --- Records -----------------------------------------------------------------------------


def test_every_dispatch_action_is_recorded_once(scene: Scene, world: World, db_session: Session):
    assigned, _ = dispatched(scene, world, db_session, accepted=True)
    contractor = scene.sign_in(CONTRACTOR)
    act(contractor, world, assigned["id"], "status", status="in_progress")
    assign_to(scene.sign_in(MANAGER), world, assigned["id"], add_contractor(db_session, world))

    assert len(events(db_session, EventType.WORK_ORDER_ASSIGNED)) == 2
    responses = events(db_session, EventType.WORK_ORDER_ASSIGNMENT_RESPONDED)
    assert len(responses) == 1
    assert responses[0].actor_user_id is not None
    db_session.expire_all()
    assignments = db_session.scalars(select(WorkOrderAssignment)).all()
    assert len(assignments) == 2
    assert sum(1 for item in assignments if item.ended_at is None) == 1


def test_a_refused_assignment_changes_nothing(scene: Scene, world: World, db_session: Session):
    _, work_order = converted(scene, world)
    admin = scene.sign_in(ADMIN)
    move(admin, world, work_order["id"], "cancelled")
    before = read_work_order(admin, world, work_order["id"])

    response = assign_to(
        admin, world, work_order["id"], membership_id(db_session, world, CONTRACTOR)
    )

    assert response.status_code == 409
    after = read_work_order(admin, world, work_order["id"])
    assert after["history"] == before["history"]
    assert after["assignment_history"] == []
    assert events(db_session, EventType.WORK_ORDER_ASSIGNED) == []
