import json
from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session
from support import ClientFactory, SignedInClient, sign_in_as
from test_directory import (  # noqa: F401 - world is a fixture used below
    ELM_ADMIN,
    MANAGER,
    OTHER_MANAGER,
    RESIDENT,
    TODAY,
    World,
    events,
    make_resident,
    move_in,
    world,
)
from test_requests import (  # noqa: F401 - scene is a fixture used below
    SECOND_RESIDENT,
    Scene,
    scene,
    submit,
)

from app.models import EventType, WorkOrderCounter

ADMIN = "admin@harbor.example"
CONTRACTOR = "contractor@harbor.example"
OWNER = "owner@harbor.example"


# --- Helpers ----------------------------------------------------------------------------


def convert(client: SignedInClient, world: World, request_id: str, **body: Any):
    return client.post(f"{world.base}/requests/{request_id}/convert", json=body)


def move(client: SignedInClient, world: World, work_order_id: str, status: str, note: str = ""):
    return client.post(
        f"{world.base}/work-orders/{work_order_id}/status",
        json={"status": status, "note": note or None},
    )


def read_work_order(client: SignedInClient, world: World, work_order_id: str) -> dict[str, Any]:
    response = client.get(f"{world.base}/work-orders/{work_order_id}")
    assert response.status_code == 200, response.text
    return response.json()


def read_request(client: SignedInClient, world: World, request_id: str) -> dict[str, Any]:
    response = client.get(f"{world.base}/requests/{request_id}")
    assert response.status_code == 200, response.text
    return response.json()


def standalone(client: SignedInClient, world: World, property_id: str, **changes: Any):
    return client.post(
        f"{world.base}/work-orders",
        json={
            "property_id": property_id,
            "title": "Repaint the stairwell",
            "scope": "Two coats, including the handrail.",
            "category": "other",
            "priority": "routine",
            **changes,
        },
    )


def converted(scene: Scene, world: World, **body: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    """A resident's request that the manager has already turned into a work order."""
    request = submit(scene, world, scene.sign_in(RESIDENT))
    response = convert(scene.sign_in(MANAGER), world, request["id"], **body)
    assert response.status_code == 201, response.text
    return request, response.json()


def resident_view(scene: Scene, world: World, email: str, request_id: str) -> dict[str, Any]:
    response = scene.sign_in(email).get(f"{world.base}/my-requests/{request_id}")
    assert response.status_code == 200, response.text
    return response.json()


# --- Converting a request ---------------------------------------------------------------


def test_manager_turns_a_request_into_a_work_order(scene: Scene, world: World):
    request, work_order = converted(scene, world)

    assert work_order["reference"] == "WO-0001"
    assert work_order["title"] == request["title"]
    assert work_order["scope"] == "The cold tap in the kitchen has dripped all week."
    assert work_order["priority"] == "soon"
    assert work_order["category"] == "plumbing"
    assert work_order["status"] == "open"
    assert work_order["property_name"] == "Maple Court"
    assert work_order["unit_label"] == "1A"
    assert [item["reference"] for item in work_order["linked_requests"]] == ["REQ-0001"]
    assert [entry["kind"] for entry in work_order["history"]] == ["created", "request_linked"]

    after = read_request(scene.sign_in(MANAGER), world, request["id"])
    assert after["status"] == "in_review"
    assert after["needs_triage"] is False
    assert after["work_order"]["reference"] == "WO-0001"


def test_the_manager_can_change_the_details_while_converting(scene: Scene, world: World):
    _, work_order = converted(
        scene,
        world,
        title="Replace kitchen tap",
        scope="Fit a new cartridge and check the cabinet for damage.",
        priority="urgent",
        due_date=(TODAY + timedelta(days=3)).isoformat(),
    )

    assert work_order["title"] == "Replace kitchen tap"
    assert work_order["priority"] == "urgent"
    assert work_order["due_date"] == (TODAY + timedelta(days=3)).isoformat()


def test_a_request_can_be_converted_only_once(scene: Scene, world: World):
    request, _ = converted(scene, world)

    again = convert(scene.sign_in(MANAGER), world, request["id"])

    assert again.status_code == 409
    listing = scene.sign_in(MANAGER).get(f"{world.base}/work-orders").json()
    assert len(listing) == 1


def test_the_resident_follows_the_work_order_through_their_own_request(scene: Scene, world: World):
    request, work_order = converted(scene, world)
    manager = scene.sign_in(MANAGER)

    assert move(manager, world, work_order["id"], "in_progress").status_code == 200
    assert resident_view(scene, world, RESIDENT, request["id"])["status"] == "in_progress"

    assert move(manager, world, work_order["id"], "ready_for_review").status_code == 200
    assert move(manager, world, work_order["id"], "completed").status_code == 200
    seen = resident_view(scene, world, RESIDENT, request["id"])
    assert seen["status"] == "resolved"
    assert "work_order" not in seen
    assert "WO-" not in json.dumps(seen)


def test_a_request_with_a_work_order_cannot_be_moved_by_hand(scene: Scene, world: World):
    request, _ = converted(scene, world)

    response = scene.sign_in(MANAGER).post(
        f"{world.base}/requests/{request['id']}/updates",
        json={"body": None, "visibility": "internal", "status": "resolved"},
    )

    assert response.status_code == 409
    assert read_request(scene.sign_in(MANAGER), world, request["id"])["status"] == "in_review"


def test_a_resident_cannot_withdraw_a_request_once_work_is_planned(scene: Scene, world: World):
    request, _ = converted(scene, world)

    seen = resident_view(scene, world, RESIDENT, request["id"])
    response = scene.sign_in(RESIDENT).post(f"{world.base}/my-requests/{request['id']}/cancel")

    assert seen["can_cancel"] is False
    assert response.status_code == 409


def test_a_withdrawn_request_is_left_alone_by_its_work_order(scene: Scene, world: World):
    first, second = two_reports(scene, world)
    manager = scene.sign_in(MANAGER)
    work_order = convert(manager, world, first["id"]).json()
    # Sam withdrew before the duplicate was matched, so it never joins the work.
    scene.sign_in(SECOND_RESIDENT).post(f"{world.base}/my-requests/{second['id']}/cancel")

    assert mark_duplicate(manager, world, second["id"], first["id"]).status_code == 409
    move(manager, world, work_order["id"], "in_progress")
    assert resident_view(scene, world, SECOND_RESIDENT, second["id"])["status"] == "cancelled"


# --- Declining ---------------------------------------------------------------------------


def test_declining_needs_a_reason_and_tells_the_resident(scene: Scene, world: World):
    request = submit(scene, world, scene.sign_in(RESIDENT))
    manager = scene.sign_in(MANAGER)
    url = f"{world.base}/requests/{request['id']}/decline"

    assert manager.post(url, json={}).status_code == 422
    assert manager.post(url, json={"reason": "  "}).status_code == 422

    done = manager.post(url, json={"reason": "This is the owner's fixture, not ours to repair."})

    assert done.status_code == 200
    assert done.json()["status"] == "declined"
    seen = resident_view(scene, world, RESIDENT, request["id"])
    assert seen["status"] == "declined"
    assert seen["can_message"] is False
    assert seen["timeline"][-1]["body"] == "This is the owner's fixture, not ours to repair."


def test_a_declined_request_is_finished_for_triage(scene: Scene, world: World):
    request = submit(scene, world, scene.sign_in(RESIDENT))
    manager = scene.sign_in(MANAGER)
    manager.post(f"{world.base}/requests/{request['id']}/decline", json={"reason": "Not ours"})

    assert convert(manager, world, request["id"]).status_code == 409
    assert (
        manager.post(
            f"{world.base}/requests/{request['id']}/decline", json={"reason": "Again"}
        ).status_code
        == 409
    )
    queue = manager.get(f"{world.base}/requests", params={"needs_triage": "true"}).json()
    assert queue == []


def test_declining_cannot_be_done_through_a_plain_status_change(scene: Scene, world: World):
    request = submit(scene, world, scene.sign_in(RESIDENT))

    response = scene.sign_in(MANAGER).post(
        f"{world.base}/requests/{request['id']}/updates",
        json={"body": None, "visibility": "internal", "status": "declined"},
    )

    assert response.status_code == 409


# --- Duplicates --------------------------------------------------------------------------


def two_reports(scene: Scene, world: World) -> tuple[dict[str, Any], dict[str, Any]]:
    first = submit(scene, world, scene.sign_in(RESIDENT))
    second = submit(scene, world, scene.sign_in(SECOND_RESIDENT), "unit_2b", title="Tap leaks")
    return first, second


def mark_duplicate(client: SignedInClient, world: World, request_id: str, original_id: str):
    return client.post(
        f"{world.base}/requests/{request_id}/duplicate", json={"duplicate_of_id": original_id}
    )


def test_a_duplicate_is_linked_without_telling_the_resident_who_else_reported(
    scene: Scene, world: World
):
    first, second = two_reports(scene, world)
    manager = scene.sign_in(MANAGER)

    response = mark_duplicate(manager, world, second["id"], first["id"])

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "in_review"
    assert body["needs_triage"] is False
    assert body["duplicate_of"]["reference"] == "REQ-0001"

    seen = resident_view(scene, world, SECOND_RESIDENT, second["id"])
    assert seen["status"] == "in_review"
    text = json.dumps(seen)
    assert "REQ-0001" not in text
    assert "Rae" not in text
    assert "duplicate" not in text
    assert any("linked your report" in entry["body"] for entry in seen["timeline"] if entry["body"])


def test_converting_the_original_brings_its_duplicates_along(scene: Scene, world: World):
    first, second = two_reports(scene, world)
    manager = scene.sign_in(MANAGER)
    mark_duplicate(manager, world, second["id"], first["id"])

    work_order = convert(manager, world, first["id"]).json()

    assert work_order["request_count"] == 2
    assert {item["reference"] for item in work_order["linked_requests"]} == {"REQ-0001", "REQ-0002"}

    move(manager, world, work_order["id"], "in_progress")
    assert resident_view(scene, world, SECOND_RESIDENT, second["id"])["status"] == "in_progress"
    assert resident_view(scene, world, RESIDENT, first["id"])["status"] == "in_progress"


def test_a_duplicate_of_a_request_that_already_has_a_work_order_joins_it(
    scene: Scene, world: World
):
    first, second = two_reports(scene, world)
    manager = scene.sign_in(MANAGER)
    work_order = convert(manager, world, first["id"]).json()
    move(manager, world, work_order["id"], "in_progress")

    response = mark_duplicate(manager, world, second["id"], first["id"])

    assert response.status_code == 200
    assert response.json()["work_order"]["reference"] == "WO-0001"
    assert response.json()["status"] == "in_progress"
    assert read_work_order(manager, world, work_order["id"])["request_count"] == 2


def test_duplicate_rules(scene: Scene, world: World, db_session: Session):
    first, second = two_reports(scene, world)
    manager = scene.sign_in(MANAGER)
    admin = scene.sign_in(ADMIN)

    assert mark_duplicate(manager, world, first["id"], first["id"]).status_code == 422

    # Another property is a different problem.
    oak_resident = make_resident(admin, world, "Oak Person")
    move_in(admin, world, scene.oak_unit["id"], oak_resident["id"])
    elsewhere = admin.post(
        f"{world.base}/requests",
        json={
            "unit_id": scene.oak_unit["id"],
            "resident_id": oak_resident["id"],
            "category": "plumbing",
            "urgency": "soon",
            "title": "Tap",
            "description": "Another tap dripping elsewhere",
        },
    )
    assert elsewhere.status_code == 201, elsewhere.text
    assert mark_duplicate(admin, world, elsewhere.json()["id"], first["id"]).status_code == 409

    # A chain of duplicates is refused: point at the original.
    assert mark_duplicate(manager, world, second["id"], first["id"]).status_code == 200
    third = submit(scene, world, scene.sign_in(RESIDENT), title="Tap again")
    assert mark_duplicate(manager, world, third["id"], second["id"]).status_code == 409

    # And a request that is already linked cannot be triaged again.
    assert mark_duplicate(manager, world, second["id"], first["id"]).status_code == 409
    assert convert(manager, world, second["id"]).status_code == 409

    assert len(events(db_session, EventType.REQUEST_MARKED_DUPLICATE)) == 1


# --- The triage queue --------------------------------------------------------------------


def test_the_queue_shows_only_requests_still_waiting_for_triage(scene: Scene, world: World):
    manager = scene.sign_in(MANAGER)
    rae = scene.sign_in(RESIDENT)
    first = submit(scene, world, rae, urgency="emergency", title="Burst pipe")
    second = submit(scene, world, rae, urgency="routine", title="Squeaky door")
    third = submit(scene, world, rae, urgency="routine", title="Loose handle")
    queue_url = f"{world.base}/requests"

    def queue(**params: str) -> list[str]:
        rows = manager.get(queue_url, params={"needs_triage": "true", **params}).json()
        return [row["title"] for row in rows]

    assert sorted(queue()) == ["Burst pipe", "Loose handle", "Squeaky door"]
    assert queue(urgency="emergency") == ["Burst pipe"]
    assert sorted(queue(urgency="routine")) == ["Loose handle", "Squeaky door"]

    convert(manager, world, first["id"])
    manager.post(f"{queue_url}/{second['id']}/decline", json={"reason": "Not a repair"})
    assert queue() == ["Loose handle"]

    # In review, with nobody acting on it yet, is still waiting.
    manager.post(
        f"{queue_url}/{third['id']}/updates",
        json={"body": None, "visibility": "internal", "status": "in_review"},
    )
    assert queue() == ["Loose handle"]

    everything = manager.get(queue_url).json()
    assert len(everything) == 3


def test_the_queue_can_be_searched_and_filtered_by_age(scene: Scene, world: World):
    manager = scene.sign_in(MANAGER)
    rae = scene.sign_in(RESIDENT)
    submit(scene, world, rae, title="Humming fridge", description="It hums loudly at night.")
    submit(scene, world, rae, title="Door sticks")

    def titles(**params: str) -> list[str]:
        return [row["title"] for row in manager.get(f"{world.base}/requests", params=params).json()]

    assert titles(q="fridge") == ["Humming fridge"]
    assert titles(q="loudly") == ["Humming fridge"]
    assert sorted(titles(q="rae resident")) == ["Door sticks", "Humming fridge"]
    assert titles(q="REQ-0002") == ["Door sticks"]
    assert titles(q="nothing like this") == []
    # Both were made a moment ago.
    assert titles(older_than_days="1") == []
    assert len(titles(older_than_days="0")) == 2


# --- Status lifecycle --------------------------------------------------------------------


def test_a_work_order_goes_through_its_whole_life(scene: Scene, world: World):
    request, work_order = converted(scene, world)
    manager = scene.sign_in(MANAGER)
    seen: list[tuple[str, str]] = []

    for step in (
        "in_progress",
        "on_hold",
        "in_progress",
        "ready_for_review",
        "completed",
        "closed",
    ):
        response = move(manager, world, work_order["id"], step, note=f"to {step}")
        assert response.status_code == 200, (step, response.text)
        seen.append((step, resident_view(scene, world, RESIDENT, request["id"])["status"]))

    assert seen == [
        ("in_progress", "in_progress"),
        ("on_hold", "in_progress"),
        ("in_progress", "in_progress"),
        ("ready_for_review", "in_progress"),
        ("completed", "resolved"),
        ("closed", "closed"),
    ]
    history = read_work_order(manager, world, work_order["id"])["history"]
    changes = [entry for entry in history if entry["kind"] == "status_changed"]
    assert [entry["status"] for entry in changes] == [step for step, _ in seen]
    assert changes[0]["body"] == "to in_progress"


def test_cancelling_a_work_order_closes_its_requests(scene: Scene, world: World):
    request, work_order = converted(scene, world)

    response = move(
        scene.sign_in(MANAGER), world, work_order["id"], "cancelled", note="Duplicate job"
    )

    assert response.status_code == 200
    assert resident_view(scene, world, RESIDENT, request["id"])["status"] == "closed"


def snapshot(scene: Scene, world: World, work_order_id: str, request_id: str) -> dict[str, Any]:
    admin = scene.sign_in(ADMIN)
    work_order = read_work_order(admin, world, work_order_id)
    request = read_request(admin, world, request_id)
    return {
        "status": work_order["status"],
        "updated_at": work_order["updated_at"],
        "history": work_order["history"],
        "request_status": request["status"],
        "request_timeline": request["timeline"],
    }


def test_a_refused_change_leaves_nothing_behind(scene: Scene, world: World, db_session: Session):
    request, work_order = converted(scene, world)
    manager = scene.sign_in(MANAGER)
    recorded = len(events(db_session, EventType.WORK_ORDER_STATUS_CHANGED))
    before = snapshot(scene, world, work_order["id"], request["id"])

    refused = [
        move(manager, world, work_order["id"], "completed"),  # skips the lifecycle
        move(manager, world, work_order["id"], "ready_for_review"),
        move(manager, world, work_order["id"], "closed"),
        move(manager, world, work_order["id"], "open"),  # already there
        move(manager, world, work_order["id"], "assigned"),  # set by assignment, not by hand
        move(manager, world, work_order["id"], "awaiting_approval"),
    ]

    assert [response.status_code for response in refused] == [409] * 6
    assert snapshot(scene, world, work_order["id"], request["id"]) == before
    assert len(events(db_session, EventType.WORK_ORDER_STATUS_CHANGED)) == recorded


def test_a_status_the_server_does_not_know_is_rejected(scene: Scene, world: World):
    _, work_order = converted(scene, world)

    response = move(scene.sign_in(MANAGER), world, work_order["id"], "teleported")

    assert response.status_code == 422


def test_the_work_order_says_which_moves_are_open_to_the_viewer(scene: Scene, world: World):
    _, work_order = converted(scene, world)
    manager = scene.sign_in(MANAGER)

    assert work_order["allowed_statuses"] == ["in_progress", "on_hold", "cancelled"]

    for step in ("in_progress", "ready_for_review", "completed", "closed"):
        move(manager, world, work_order["id"], step)

    assert read_work_order(manager, world, work_order["id"])["allowed_statuses"] == []
    assert read_work_order(scene.sign_in(ADMIN), world, work_order["id"])["allowed_statuses"] == [
        "in_progress"
    ]


def test_only_an_administrator_can_reopen_finished_work(scene: Scene, world: World):
    request, work_order = converted(scene, world)
    manager = scene.sign_in(MANAGER)
    admin = scene.sign_in(ADMIN)
    for step in ("in_progress", "ready_for_review", "completed", "closed"):
        move(manager, world, work_order["id"], step)
    before = snapshot(scene, world, work_order["id"], request["id"])

    assert move(manager, world, work_order["id"], "in_progress").status_code == 403
    assert snapshot(scene, world, work_order["id"], request["id"]) == before

    assert (
        move(admin, world, work_order["id"], "in_progress", note="Leak is back").status_code == 200
    )
    assert resident_view(scene, world, RESIDENT, request["id"])["status"] == "in_progress"


def test_only_an_administrator_can_bring_back_a_cancelled_work_order(scene: Scene, world: World):
    _, work_order = converted(scene, world)
    manager = scene.sign_in(MANAGER)
    move(manager, world, work_order["id"], "cancelled")

    assert move(manager, world, work_order["id"], "open").status_code == 403
    assert move(scene.sign_in(ADMIN), world, work_order["id"], "open").status_code == 200


def test_every_change_records_who_and_when(scene: Scene, world: World, db_session: Session):
    _, work_order = converted(scene, world)
    manager = scene.sign_in(MANAGER)
    admin = scene.sign_in(ADMIN)
    move(manager, world, work_order["id"], "in_progress")
    manager.post(
        f"{world.base}/work-orders/{work_order['id']}/notes",
        json={"body": "Part ordered", "visibility": "internal"},
    )
    manager.put(
        f"{world.base}/work-orders/{work_order['id']}",
        json={
            "title": "New title",
            "scope": work_order["scope"],
            "category": "plumbing",
            "priority": "urgent",
            "due_date": None,
        },
    )
    move(admin, world, work_order["id"], "cancelled")

    history = read_work_order(admin, world, work_order["id"])["history"]

    assert [entry["kind"] for entry in history] == [
        "created",
        "request_linked",
        "status_changed",
        "note",
        "edited",
        "status_changed",
    ]
    assert all(entry["created_at"] for entry in history)
    assert [entry["author_name"] for entry in history] == [
        MANAGER,
        MANAGER,
        MANAGER,
        MANAGER,
        MANAGER,
        ADMIN,
    ]
    stamps = [entry["created_at"] for entry in history]
    assert stamps == sorted(stamps)

    for kind in (
        EventType.WORK_ORDER_CREATED,
        EventType.WORK_ORDER_STATUS_CHANGED,
        EventType.WORK_ORDER_UPDATED,
    ):
        assert all(item.actor_user_id is not None for item in events(db_session, kind))
    assert len(events(db_session, EventType.WORK_ORDER_STATUS_CHANGED)) == 2


# --- Editing and notes -------------------------------------------------------------------


def edit(client: SignedInClient, world: World, work_order: dict[str, Any], **changes: Any):
    body = {
        "title": work_order["title"],
        "scope": work_order["scope"],
        "category": work_order["category"],
        "priority": work_order["priority"],
        "due_date": work_order["due_date"],
        **changes,
    }
    return client.put(f"{world.base}/work-orders/{work_order['id']}", json=body)


def test_edits_are_recorded_with_before_and_after(scene: Scene, world: World):
    _, work_order = converted(scene, world)
    manager = scene.sign_in(MANAGER)
    due = (TODAY + timedelta(days=7)).isoformat()

    response = edit(manager, world, work_order, priority="urgent", due_date=due)

    assert response.status_code == 200
    entry = response.json()["history"][-1]
    assert entry["kind"] == "edited"
    assert entry["details"] == {"priority": ["soon", "urgent"], "due_date": [None, due]}


def test_saving_without_changes_adds_nothing(scene: Scene, world: World, db_session: Session):
    _, work_order = converted(scene, world)

    response = edit(scene.sign_in(MANAGER), world, work_order)

    assert response.status_code == 200
    assert len(response.json()["history"]) == len(work_order["history"])
    assert events(db_session, EventType.WORK_ORDER_UPDATED) == []


def test_a_closed_work_order_cannot_be_edited(scene: Scene, world: World):
    _, work_order = converted(scene, world)
    manager = scene.sign_in(MANAGER)
    for step in ("in_progress", "ready_for_review", "completed", "closed"):
        move(manager, world, work_order["id"], step)

    assert edit(manager, world, work_order, title="Sneaky").status_code == 409


def test_an_internal_note_stays_off_the_residents_page(scene: Scene, world: World):
    request, work_order = converted(scene, world)
    manager = scene.sign_in(MANAGER)

    response = manager.post(
        f"{world.base}/work-orders/{work_order['id']}/notes",
        json={"body": "Landlord wants the cheap valve", "visibility": "internal"},
    )

    assert response.status_code == 201
    assert response.json()["history"][-1]["body"] == "Landlord wants the cheap valve"
    assert "cheap valve" not in json.dumps(resident_view(scene, world, RESIDENT, request["id"]))


def test_a_shared_note_reaches_every_linked_request(scene: Scene, world: World):
    first, second = two_reports(scene, world)
    manager = scene.sign_in(MANAGER)
    mark_duplicate(manager, world, second["id"], first["id"])
    work_order = convert(manager, world, first["id"]).json()

    manager.post(
        f"{world.base}/work-orders/{work_order['id']}/notes",
        json={"body": "Plumber visits Thursday morning", "visibility": "resident"},
    )

    for email, request in ((RESIDENT, first), (SECOND_RESIDENT, second)):
        timeline = resident_view(scene, world, email, request["id"])["timeline"]
        assert "Plumber visits Thursday morning" in [entry["body"] for entry in timeline]


def test_notes_need_text(scene: Scene, world: World):
    _, work_order = converted(scene, world)

    response = scene.sign_in(MANAGER).post(
        f"{world.base}/work-orders/{work_order['id']}/notes", json={"body": "  "}
    )

    assert response.status_code == 422


# --- Creating without a request ----------------------------------------------------------


def test_a_work_order_can_be_raised_without_a_request(scene: Scene, world: World):
    response = standalone(
        scene.sign_in(MANAGER),
        world,
        scene.maple["id"],
        unit_id=scene.unit_1a["id"],
        due_date=(TODAY + timedelta(days=10)).isoformat(),
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["reference"] == "WO-0001"
    assert body["status"] == "open"
    assert body["unit_label"] == "1A"
    assert body["linked_requests"] == []
    assert [entry["kind"] for entry in body["history"]] == ["created"]


def test_standalone_work_order_checks_its_inputs(scene: Scene, world: World):
    manager = scene.sign_in(MANAGER)

    assert standalone(manager, world, scene.maple["id"], title="x").status_code == 422
    assert standalone(manager, world, scene.maple["id"], scope=" ").status_code == 422
    assert standalone(manager, world, scene.maple["id"], priority="whenever").status_code == 422
    # A unit from another property.
    assert (
        standalone(manager, world, scene.maple["id"], unit_id=scene.oak_unit["id"]).status_code
        == 422
    )


def test_numbers_follow_one_another_and_each_organization_has_its_own(
    scene: Scene, world: World, db_session: Session
):
    admin = scene.sign_in(ADMIN)

    numbers = [standalone(admin, world, scene.maple["id"]).json()["reference"] for _ in range(3)]

    assert numbers == ["WO-0001", "WO-0002", "WO-0003"]
    elm_counter = db_session.scalar(
        select(WorkOrderCounter).where(WorkOrderCounter.organization_id == world.elm_id)
    )
    assert elm_counter is not None and elm_counter.last_number == 0


# --- Access ------------------------------------------------------------------------------


def test_managers_only_reach_work_orders_at_their_properties(scene: Scene, world: World):
    admin = scene.sign_in(ADMIN)
    mine = standalone(admin, world, scene.maple["id"], title="Maple job").json()
    theirs = standalone(admin, world, scene.oak["id"], title="Oak job").json()

    manager = scene.sign_in(MANAGER)
    titles = [item["title"] for item in manager.get(f"{world.base}/work-orders").json()]
    assert titles == ["Maple job"]
    assert manager.get(f"{world.base}/work-orders/{mine['id']}").status_code == 200
    assert manager.get(f"{world.base}/work-orders/{theirs['id']}").status_code == 404
    assert move(manager, world, theirs["id"], "in_progress").status_code == 404
    assert (
        manager.post(
            f"{world.base}/work-orders/{theirs['id']}/notes", json={"body": "hello"}
        ).status_code
        == 404
    )
    assert edit(manager, world, theirs, title="Mine now").status_code == 404
    assert standalone(manager, world, scene.oak["id"]).status_code == 404

    assert scene.sign_in(OTHER_MANAGER).get(f"{world.base}/work-orders").json() == []
    assert len(admin.get(f"{world.base}/work-orders").json()) == 2


def test_a_manager_cannot_triage_requests_at_other_properties(scene: Scene, world: World):
    admin = scene.sign_in(ADMIN)
    oak_resident = make_resident(admin, world, "Oak Person")
    move_in(admin, world, scene.oak_unit["id"], oak_resident["id"])
    created = admin.post(
        f"{world.base}/requests",
        json={
            "unit_id": scene.oak_unit["id"],
            "resident_id": oak_resident["id"],
            "category": "plumbing",
            "urgency": "soon",
            "title": "Tap",
            "description": "Dripping all week",
        },
    ).json()
    manager = scene.sign_in(MANAGER)

    assert convert(manager, world, created["id"]).status_code == 404
    assert (
        manager.post(
            f"{world.base}/requests/{created['id']}/decline", json={"reason": "Nope"}
        ).status_code
        == 404
    )
    assert mark_duplicate(manager, world, created["id"], created["id"]).status_code == 404


def test_only_staff_can_use_work_orders(scene: Scene, world: World):
    _, work_order = converted(scene, world)
    for email in (RESIDENT, CONTRACTOR, OWNER):
        client = scene.sign_in(email)
        assert client.get(f"{world.base}/work-orders").status_code == 403
        assert client.get(f"{world.base}/work-orders/{work_order['id']}").status_code == 403
        assert move(client, world, work_order["id"], "in_progress").status_code == 403
        assert standalone(client, world, scene.maple["id"]).status_code == 403


def test_another_organizations_staff_cannot_see_them(
    scene: Scene, world: World, client_factory: ClientFactory
):
    _, work_order = converted(scene, world)
    elm = scene.sign_in(ELM_ADMIN)

    assert elm.get(f"{world.base}/work-orders").status_code == 404
    assert elm.get(f"{world.base}/work-orders/{work_order['id']}").status_code == 404
    assert sign_in_as(client_factory, ELM_ADMIN).get(f"{world.base}/work-orders").status_code == 404


# --- Searching ---------------------------------------------------------------------------


def test_work_orders_can_be_filtered_and_searched(scene: Scene, world: World):
    admin = scene.sign_in(ADMIN)
    leak = standalone(admin, world, scene.maple["id"], title="Fix roof leak", priority="urgent")
    paint = standalone(admin, world, scene.maple["id"], title="Paint stairwell").json()
    oak = standalone(admin, world, scene.oak["id"], title="Oak gutters").json()
    move(admin, world, paint["id"], "in_progress")
    move(admin, world, oak["id"], "cancelled")
    assert leak.status_code == 201

    def titles(**params: str) -> list[str]:
        rows = admin.get(f"{world.base}/work-orders", params=params).json()
        return sorted(row["title"] for row in rows)

    assert titles() == ["Fix roof leak", "Oak gutters", "Paint stairwell"]
    assert titles(status="in_progress") == ["Paint stairwell"]
    assert titles(open_only="true") == ["Fix roof leak", "Paint stairwell"]
    assert titles(priority="urgent") == ["Fix roof leak"]
    assert titles(property_id=scene.oak["id"]) == ["Oak gutters"]
    assert titles(q="stairwell") == ["Paint stairwell"]
    assert titles(q="WO-0001") == ["Fix roof leak"]
    assert titles(q="wo-0002") == ["Paint stairwell"]
    assert titles(q="nothing") == []
    assert titles(older_than_days="1") == []
    assert len(titles(older_than_days="0")) == 3
    assert admin.get(f"{world.base}/work-orders", params={"status": "bogus"}).status_code == 422


def test_overdue_is_worked_out_from_the_due_date_and_status(scene: Scene, world: World):
    admin = scene.sign_in(ADMIN)
    yesterday = (TODAY - timedelta(days=1)).isoformat()
    late = standalone(admin, world, scene.maple["id"], title="Late", due_date=yesterday).json()
    done = standalone(admin, world, scene.maple["id"], title="Done", due_date=yesterday).json()
    standalone(admin, world, scene.maple["id"], title="Later", due_date=TODAY.isoformat())
    for step in ("in_progress", "ready_for_review", "completed"):
        move(admin, world, done["id"], step)

    rows = {row["title"]: row for row in admin.get(f"{world.base}/work-orders").json()}

    assert rows["Late"]["overdue"] is True
    assert rows["Done"]["overdue"] is False
    assert rows["Later"]["overdue"] is False
    assert late["overdue"] is True


def test_the_list_counts_linked_requests(scene: Scene, world: World):
    first, second = two_reports(scene, world)
    manager = scene.sign_in(MANAGER)
    mark_duplicate(manager, world, second["id"], first["id"])
    convert(manager, world, first["id"])
    standalone(manager, world, scene.maple["id"])

    rows = manager.get(f"{world.base}/work-orders").json()

    assert sorted(row["request_count"] for row in rows) == [0, 2]


def test_the_requests_list_points_at_each_work_order(scene: Scene, world: World):
    first, _ = two_reports(scene, world)
    manager = scene.sign_in(MANAGER)
    convert(manager, world, first["id"])

    rows = {row["reference"]: row for row in manager.get(f"{world.base}/requests").json()}

    assert rows["REQ-0001"]["work_order"]["reference"] == "WO-0001"
    assert rows["REQ-0001"]["needs_triage"] is False
    assert rows["REQ-0002"]["work_order"] is None
    assert rows["REQ-0002"]["needs_triage"] is True


def test_triage_is_recorded_in_the_activity_log(scene: Scene, world: World, db_session: Session):
    first, second = two_reports(scene, world)
    manager = scene.sign_in(MANAGER)
    third = submit(scene, world, scene.sign_in(RESIDENT), title="Third")
    mark_duplicate(manager, world, second["id"], first["id"])
    convert(manager, world, first["id"])
    manager.post(f"{world.base}/requests/{third['id']}/decline", json={"reason": "Not ours"})

    for kind in (
        EventType.REQUEST_CONVERTED,
        EventType.REQUEST_MARKED_DUPLICATE,
        EventType.REQUEST_DECLINED,
        EventType.WORK_ORDER_CREATED,
    ):
        recorded = events(db_session, kind)
        assert len(recorded) == 1, kind
        assert recorded[0].actor_user_id is not None
        assert recorded[0].occurred_at is not None
