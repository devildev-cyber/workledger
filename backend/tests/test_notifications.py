import json
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from support import SignedInClient
from test_directory import (  # noqa: F401 - world is a fixture used below
    ELM_ADMIN,
    MANAGER,
    OTHER_MANAGER,
    RESIDENT,
    World,
    world,
)
from test_dispatch import act, assign_to, dispatched, membership_id
from test_estimates import SECRET_NOTE, decide, job, own, quote, set_threshold
from test_requests import (  # noqa: F401 - scene is a fixture used below
    Scene,
    payload,
    scene,
    submit,
)
from test_work_orders import ADMIN, CONTRACTOR, OWNER, convert, converted, move

from app.core.mail import MemoryEmailSender
from app.models import Notification

EVERYONE = [ADMIN, MANAGER, OTHER_MANAGER, RESIDENT, CONTRACTOR, OWNER]


# --- Helpers ----------------------------------------------------------------------------


def box(
    scene: Scene, world: World, email: str, *, client: SignedInClient | None = None, **params: Any
) -> dict[str, Any]:
    response = (client or scene.sign_in(email)).get(f"{world.base}/notifications", params=params)
    assert response.status_code == 200, response.text
    return response.json()


def heard(scene: Scene, world: World, email: str) -> list[str]:
    """What the person has been told, newest first."""
    return [item["title"] for item in box(scene, world, email)["items"]]


def everyone_heard(scene: Scene, world: World) -> dict[str, list[str]]:
    return {email: heard(scene, world, email) for email in EVERYONE}


def quiet(scene: Scene, world: World, *emails: str) -> None:
    for email in emails:
        assert heard(scene, world, email) == [], email


def path(world: World, tail: str) -> str:
    return f"/organizations/{world.harbor_id}/{tail}"


def ready_for_review(scene: Scene, world: World, db: Session) -> dict[str, Any]:
    order, _ = dispatched(scene, world, db, accepted=True)
    contractor = scene.sign_in(CONTRACTOR)
    assert act(contractor, world, order["id"], "status", status="in_progress").status_code == 200
    done = act(contractor, world, order["id"], "status", status="ready_for_review", note="Fixed")
    assert done.status_code == 200, done.text
    return order


# --- Requests ---------------------------------------------------------------------------


def test_a_new_request_tells_the_property_team_and_nobody_else(scene: Scene, world: World):
    request = submit(scene, world, scene.sign_in(RESIDENT))

    told = everyone_heard(scene, world)

    assert told[MANAGER] == ["New request REQ-0001: Kitchen tap drips"]
    for email in (ADMIN, OTHER_MANAGER, RESIDENT, CONTRACTOR, OWNER):
        assert told[email] == [], email
    (item,) = box(scene, world, MANAGER)["items"]
    assert item["path"] == path(world, f"requests/{request['id']}")
    assert item["read"] is False


def test_a_property_nobody_manages_falls_back_to_the_administrators(
    scene: Scene, world: World, db_session: Session
):
    from test_directory import assign

    assign(scene.sign_in(ADMIN), world, scene.maple["id"], db=db_session)

    submit(scene, world, scene.sign_in(RESIDENT))

    assert heard(scene, world, ADMIN) == ["New request REQ-0001: Kitchen tap drips"]
    quiet(scene, world, MANAGER, OTHER_MANAGER)


def test_a_request_logged_by_staff_also_tells_the_resident(scene: Scene, world: World):
    response = scene.sign_in(MANAGER).post(
        f"{world.base}/requests",
        json={**payload(scene.unit_1a["id"]), "resident_id": scene.rae["id"]},
    )
    assert response.status_code == 201, response.text

    assert heard(scene, world, RESIDENT) == [
        "A request was logged for you: REQ-0001, Kitchen tap drips"
    ]
    quiet(scene, world, MANAGER)


def test_the_resident_hears_when_their_request_moves_and_the_team_when_they_reply(
    scene: Scene, world: World
):
    request = submit(scene, world, scene.sign_in(RESIDENT))
    manager = scene.sign_in(MANAGER)
    url = f"{world.base}/requests/{request['id']}/updates"

    assert manager.post(url, json={"status": "in_review"}).status_code == 201
    assert (
        manager.post(url, json={"body": "We will call.", "visibility": "resident"}).status_code
        == 201
    )
    assert (
        manager.post(url, json={"body": "Check the lease", "visibility": "internal"}).status_code
        == 201
    )

    assert heard(scene, world, RESIDENT) == [
        "New message on your request REQ-0001",
        "Your request REQ-0001 is now being reviewed",
    ]
    (latest, _) = box(scene, world, RESIDENT)["items"]
    assert latest["path"] == path(world, f"my-requests/{request['id']}")

    reply = scene.sign_in(RESIDENT).post(
        f"{world.base}/my-requests/{request['id']}/messages", json={"body": "Thanks"}
    )
    assert reply.status_code == 201, reply.text
    assert heard(scene, world, MANAGER)[0] == "The resident replied on REQ-0001"


# --- Work orders ------------------------------------------------------------------------


def test_assigning_tells_the_contractor_and_reassigning_tells_the_one_who_lost_it(
    scene: Scene, world: World, db_session: Session
):
    from test_dispatch import add_contractor

    order, _ = dispatched(scene, world, db_session)

    first = box(scene, world, CONTRACTOR)["items"]
    assert [item["title"] for item in first] == [
        f"{order['reference']} was assigned to you: Kitchen tap drips"
    ]
    assert first[0]["path"] == path(world, f"my-jobs/{order['id']}")
    quiet(scene, world, OWNER, ADMIN)
    assert all("assigned" not in line for line in heard(scene, world, MANAGER))

    second = add_contractor(db_session, world)
    response = assign_to(scene.sign_in(MANAGER), world, order["id"], second)
    assert response.status_code == 200, response.text

    told = heard(scene, world, CONTRACTOR)
    assert told[0] == f"You are no longer assigned to {order['reference']}"
    assert box(scene, world, CONTRACTOR)["items"][0]["path"] == path(world, "my-jobs")
    assert heard(scene, world, "contractor2@harbor.example") == [
        f"{order['reference']} was assigned to you: Kitchen tap drips"
    ]


def test_the_team_hears_whether_the_contractor_accepted_or_declined(
    scene: Scene, world: World, db_session: Session
):
    order, _ = dispatched(scene, world, db_session)
    contractor = scene.sign_in(CONTRACTOR)

    accepted = act(contractor, world, order["id"], "accept")
    assert accepted.status_code == 200, accepted.text
    assert heard(scene, world, MANAGER)[0] == f"The contractor accepted {order['reference']}"

    other, _ = dispatched(scene, world, db_session)
    declined = act(contractor, world, other["id"], "decline", reason="Too far away")
    assert declined.status_code == 204, declined.text
    told = heard(scene, world, MANAGER)
    assert told[0] == f"The contractor declined {other['reference']}. It needs a new contractor"
    # The reason is for the manager to read on the work order, not in the notification.
    assert all("Too far" not in line for line in told)
    quiet(scene, world, OWNER)


def test_finishing_work_asks_for_review_then_tells_the_contractor(
    scene: Scene, world: World, db_session: Session
):
    order = ready_for_review(scene, world, db_session)
    assert heard(scene, world, MANAGER)[0] == f"{order['reference']} is ready for your review"

    verified = scene.sign_in(MANAGER).post(
        f"{world.base}/work-orders/{order['id']}/verify", json={"resolution": "Washer replaced"}
    )
    assert verified.status_code == 200, verified.text

    assert heard(scene, world, CONTRACTOR)[0] == f"Your work on {order['reference']} was verified"
    # The owner is only told about work they approved spending on.
    quiet(scene, world, OWNER)


def test_sending_work_back_tells_the_contractor_without_the_reason(
    scene: Scene, world: World, db_session: Session
):
    order = ready_for_review(scene, world, db_session)

    sent = scene.sign_in(MANAGER).post(
        f"{world.base}/work-orders/{order['id']}/send-back",
        json={"reason": "The tap still drips at the base"},
    )
    assert sent.status_code == 200, sent.text

    told = heard(scene, world, CONTRACTOR)
    assert told[0] == f"{order['reference']} was sent back to you. See what still needs doing"
    assert all("drips at the base" not in line for line in told)


def test_the_resident_follows_the_work_through_to_resolution_and_closure(
    scene: Scene, world: World, db_session: Session
):
    request, order = converted(scene, world)
    manager = scene.sign_in(MANAGER)
    contractor_id = membership_id(db_session, world, CONTRACTOR)
    assert assign_to(manager, world, order["id"], contractor_id).status_code == 200
    contractor = scene.sign_in(CONTRACTOR)
    assert act(contractor, world, order["id"], "accept").status_code == 200
    assert act(contractor, world, order["id"], "status", status="in_progress").status_code == 200
    done = act(contractor, world, order["id"], "status", status="ready_for_review", note="Done")
    assert done.status_code == 200, done.text
    assert move(manager, world, order["id"], "completed", "Washer replaced").status_code == 200
    assert move(manager, world, order["id"], "closed").status_code == 200

    told = heard(scene, world, RESIDENT)

    assert told[0] == f"Your request {request['reference']} is now closed"
    assert f"Your request {request['reference']} is now resolved" in told
    assert f"Your request {request['reference']} is now being reviewed" in told
    # A closed job is announced to the contractor too.
    assert f"{order['reference']} is now closed: Kitchen tap drips" in heard(
        scene, world, CONTRACTOR
    )


def test_the_contractor_pausing_tells_the_team_and_the_team_pausing_tells_the_contractor(
    scene: Scene, world: World, db_session: Session
):
    order, _ = dispatched(scene, world, db_session, accepted=True)
    contractor = scene.sign_in(CONTRACTOR)
    manager = scene.sign_in(MANAGER)
    assert act(contractor, world, order["id"], "status", status="in_progress").status_code == 200

    paused = act(contractor, world, order["id"], "status", status="on_hold", note="Part ordered")
    assert paused.status_code == 200, paused.text
    assert (
        heard(scene, world, MANAGER)[0] == f"{order['reference']} was put on hold by the contractor"
    )
    assert all("Part ordered" not in line for line in heard(scene, world, MANAGER))

    assert move(manager, world, order["id"], "in_progress").status_code == 200
    assert move(manager, world, order["id"], "on_hold", "Waiting").status_code == 200
    told = heard(scene, world, CONTRACTOR)
    assert told[0] == f"{order['reference']} is now on hold: Kitchen tap drips"
    assert f"{order['reference']} is now in progress: Kitchen tap drips" in told


def test_cancelling_tells_the_contractor_and_points_to_their_list(
    scene: Scene, world: World, db_session: Session
):
    order, _ = dispatched(scene, world, db_session, accepted=True)

    assert move(scene.sign_in(MANAGER), world, order["id"], "cancelled").status_code == 200

    latest = box(scene, world, CONTRACTOR)["items"][0]
    assert latest["title"] == f"{order['reference']} is now cancelled: Kitchen tap drips"
    # The job has left their list, so the link opens the list rather than a missing job.
    assert latest["path"] == path(world, "my-jobs")


# --- Estimates --------------------------------------------------------------------------


def test_an_estimate_over_the_threshold_asks_only_the_owner_to_decide(
    scene: Scene, world: World, db_session: Session
):
    order = job(scene, world, db_session)

    response = quote(scene.sign_in(MANAGER), world, order["id"], 80_000)
    assert response.status_code == 201, response.text
    estimate_id = response.json()["estimates"][0]["id"]

    (item,) = box(scene, world, OWNER)["items"]
    assert item["title"] == f"{order['reference']} needs your decision: Kitchen tap drips"
    assert item["path"] == path(world, f"my-approvals/{estimate_id}")
    quiet(scene, world, ADMIN, OTHER_MANAGER)
    assert all("decision" not in line for line in heard(scene, world, RESIDENT))
    # The contractor learns the job is waiting, not what it costs.
    contractor_told = heard(scene, world, CONTRACTOR)
    assert contractor_told[0].startswith(
        f"{order['reference']} is now waiting for the owner's approval"
    )
    assert all("800" not in line for line in contractor_told)


def test_an_estimate_under_the_threshold_tells_nobody_to_decide(
    scene: Scene, world: World, db_session: Session
):
    order = job(scene, world, db_session)

    assert quote(scene.sign_in(MANAGER), world, order["id"], 14_000).status_code == 201

    quiet(scene, world, OWNER)


def test_the_decision_tells_whoever_recorded_the_estimate_and_never_repeats_the_reason(
    scene: Scene, world: World, db_session: Session
):
    order = job(scene, world, db_session)
    estimate_id = quote(scene.sign_in(MANAGER), world, order["id"], 80_000).json()["estimates"][0][
        "id"
    ]

    response = decide(scene.sign_in(OWNER), world, estimate_id, "reject", SECRET_NOTE)
    assert response.status_code == 200, response.text

    told = heard(scene, world, MANAGER)
    assert (
        told[0] == f"The owner rejected the estimate for {order['reference']}. The work is on hold"
    )
    assert all(SECRET_NOTE not in line for line in told)
    # The owner made the decision, so they are not told about it.
    assert heard(scene, world, OWNER) == [
        f"{order['reference']} needs your decision: Kitchen tap drips"
    ]
    assert (
        heard(scene, world, CONTRACTOR)[0]
        == f"{order['reference']} is now on hold: Kitchen tap drips"
    )


def test_approved_work_tells_the_owner_when_it_is_complete(
    scene: Scene, world: World, db_session: Session
):
    order = job(scene, world, db_session)
    estimate_id = quote(scene.sign_in(MANAGER), world, order["id"], 80_000).json()["estimates"][0][
        "id"
    ]
    assert decide(scene.sign_in(OWNER), world, estimate_id).status_code == 200
    contractor = scene.sign_in(CONTRACTOR)
    assert act(contractor, world, order["id"], "status", status="in_progress").status_code == 200
    done = act(contractor, world, order["id"], "status", status="ready_for_review", note="Done")
    assert done.status_code == 200, done.text

    assert move(scene.sign_in(MANAGER), world, order["id"], "completed").status_code == 200

    latest = box(scene, world, OWNER)["items"][0]
    assert latest["title"] == f"Approved work is complete: {order['reference']}, Kitchen tap drips"
    assert latest["path"] == path(world, f"my-approvals/{estimate_id}")


def test_an_owner_who_no_longer_owns_the_property_is_not_asked(
    scene: Scene, world: World, db_session: Session
):
    order = job(scene, world, db_session)
    own(scene, world, db_session)  # no owners left

    assert quote(scene.sign_in(MANAGER), world, order["id"], 80_000).status_code == 201

    quiet(scene, world, OWNER)


# --- Privacy ----------------------------------------------------------------------------


def test_no_notification_carries_amounts_notes_or_reasons(
    scene: Scene, world: World, db_session: Session
):
    order = job(scene, world, db_session)
    manager = scene.sign_in(MANAGER)
    assert (
        manager.post(
            f"{world.base}/work-orders/{order['id']}/notes",
            json={"body": SECRET_NOTE, "visibility": "internal"},
        ).status_code
        == 201
    )
    estimate_id = quote(manager, world, order["id"], 80_123).json()["estimates"][0]["id"]
    assert (
        decide(scene.sign_in(OWNER), world, estimate_id, "approve", SECRET_NOTE).status_code == 200
    )

    everything = json.dumps(everyone_heard(scene, world))

    for secret in (SECRET_NOTE, "80123", "801.23", "cartridge", "555-0111", "Rae Resident"):
        assert secret not in everything, secret


def test_people_see_only_their_own_notifications(scene: Scene, world: World):
    submit(scene, world, scene.sign_in(RESIDENT))
    mine = box(scene, world, MANAGER)["items"][0]["id"]

    other = scene.sign_in(OTHER_MANAGER)
    assert other.post(f"{world.base}/notifications/{mine}/read").status_code == 404
    assert box(scene, world, MANAGER)["unread_count"] == 1

    outsider = scene.sign_in(ELM_ADMIN)
    assert outsider.get(f"{world.base}/notifications").status_code == 404
    assert outsider.post(f"{world.base}/notifications/{mine}/read").status_code == 404


def test_notifications_require_signing_in(scene: Scene, world: World, client_factory):
    anonymous = client_factory(None)

    assert anonymous.get(f"{world.base}/notifications").status_code == 401
    assert anonymous.post(f"{world.base}/notifications/read").status_code in (401, 403)


# --- Reading and preferences ------------------------------------------------------------


def test_notifications_can_be_read_one_at_a_time_or_all_at_once(scene: Scene, world: World):
    submit(scene, world, scene.sign_in(RESIDENT))
    submit(scene, world, scene.sign_in(RESIDENT), title="Light is out")
    manager = scene.sign_in(MANAGER)
    listing = box(scene, world, MANAGER, client=manager)
    assert listing["unread_count"] == 2
    assert [item["title"] for item in listing["items"]] == [
        "New request REQ-0002: Light is out",
        "New request REQ-0001: Kitchen tap drips",
    ]

    one = manager.post(f"{world.base}/notifications/{listing['items'][0]['id']}/read")
    assert one.status_code == 200
    assert one.json()["unread_count"] == 1
    unread = box(scene, world, MANAGER, client=manager, unread_only=True)
    assert [item["title"] for item in unread["items"]] == [
        "New request REQ-0001: Kitchen tap drips"
    ]

    everything = manager.post(f"{world.base}/notifications/read")
    assert everything.status_code == 200
    assert everything.json()["unread_count"] == 0
    assert all(item["read"] for item in everything.json()["items"])


def test_unknown_notifications_are_not_found(scene: Scene, world: World):
    missing = "00000000-0000-4000-8000-000000000000"

    response = scene.sign_in(MANAGER).post(f"{world.base}/notifications/{missing}/read")

    assert response.status_code == 404


# --- Email copies -----------------------------------------------------------------------


def test_email_copies_go_to_the_recipient_with_a_link_and_no_detail(
    scene: Scene, world: World, outbox: MemoryEmailSender
):
    outbox.clear()
    request = submit(scene, world, scene.sign_in(RESIDENT))

    (message,) = [m for m in outbox.sent if m.to == MANAGER]
    assert message.subject == "New request REQ-0001: Kitchen tap drips"
    link = f"{scene.settings.frontend_url}/organizations/{world.harbor_id}/requests/{request['id']}"
    assert link in message.body
    assert "dripped all week" not in message.body
    # The person who acted is not emailed about their own action.
    assert [m.to for m in outbox.sent] == [MANAGER]


def test_email_can_be_turned_off_without_losing_the_in_app_notification(
    scene: Scene, world: World, outbox: MemoryEmailSender
):
    manager = scene.sign_in(MANAGER)
    assert manager.get(f"{world.base}/notifications/preferences").json() == {"email_enabled": True}
    saved = manager.put(f"{world.base}/notifications/preferences", json={"email_enabled": False})
    assert saved.status_code == 200
    assert saved.json() == {"email_enabled": False}
    outbox.clear()

    submit(scene, world, scene.sign_in(RESIDENT))

    assert outbox.sent == []
    assert heard(scene, world, MANAGER) == ["New request REQ-0001: Kitchen tap drips"]


def test_a_refused_change_sends_no_email_and_leaves_no_notification(
    scene: Scene, world: World, db_session: Session, outbox: MemoryEmailSender
):
    order, _ = dispatched(scene, world, db_session)
    before = len(box(scene, world, CONTRACTOR)["items"])
    outbox.clear()

    refused = move(scene.sign_in(MANAGER), world, order["id"], "closed")

    assert refused.status_code == 409
    assert outbox.sent == []
    assert len(box(scene, world, CONTRACTOR)["items"]) == before
    db_session.expire_all()
    assert len(db_session.scalars(select(Notification)).all()) == (
        len(box(scene, world, MANAGER)["items"]) + before + len(heard(scene, world, RESIDENT))
    )


def test_a_failing_email_does_not_undo_the_change(
    scene: Scene, world: World, outbox: MemoryEmailSender, monkeypatch: pytest.MonkeyPatch
):
    def fail(_message: object) -> None:
        raise RuntimeError("the mail server is down")

    monkeypatch.setattr(outbox, "send", fail)

    request = submit(scene, world, scene.sign_in(RESIDENT))

    assert request["reference"] == "REQ-0001"
    assert heard(scene, world, MANAGER) == ["New request REQ-0001: Kitchen tap drips"]


def test_the_other_firm_is_never_told(scene: Scene, world: World):
    submit(scene, world, scene.sign_in(RESIDENT))

    response = scene.sign_in(ELM_ADMIN).get(f"/api/organizations/{world.elm_id}/notifications")

    assert response.status_code == 200
    assert response.json() == {"items": [], "unread_count": 0}


# --- Overdue and blocked work -----------------------------------------------------------


def listed(client: SignedInClient, world: World, **params: Any) -> list[dict[str, Any]]:
    response = client.get(f"{world.base}/work-orders", params=params)
    assert response.status_code == 200, response.text
    return response.json()


def test_overdue_and_blocked_work_can_be_picked_out(
    scene: Scene, world: World, db_session: Session
):
    manager = scene.sign_in(MANAGER)
    late = converted(scene, world, due_date="2020-01-01")[1]
    paused = converted(scene, world)[1]
    waiting = converted(scene, world)[1]
    fine = converted(scene, world, due_date="2999-01-01")[1]
    assert move(manager, world, paused["id"], "on_hold", "Waiting for parts").status_code == 200
    set_threshold(scene, world)
    own(scene, world, db_session, OWNER)
    assert quote(manager, world, waiting["id"], 80_000).status_code == 201

    overdue = listed(manager, world, attention="overdue")
    blocked = listed(manager, world, attention="blocked")

    assert [item["id"] for item in overdue] == [late["id"]]
    assert {item["id"] for item in blocked} == {paused["id"], waiting["id"]}
    reasons = {item["id"]: item["blocked_reason"] for item in blocked}
    assert reasons[paused["id"]] == "On hold"
    assert reasons[waiting["id"]] == "Waiting for the owner's approval"
    everything = {item["id"]: item for item in listed(manager, world)}
    assert everything[fine["id"]]["blocked"] is False
    assert everything[fine["id"]]["blocked_reason"] is None
    assert everything[late["id"]]["overdue"] is True


def test_finished_work_is_never_overdue(scene: Scene, world: World):
    manager = scene.sign_in(MANAGER)
    late = converted(scene, world, due_date="2020-01-01")[1]
    assert move(manager, world, late["id"], "cancelled").status_code == 200

    assert listed(manager, world, attention="overdue") == []


def test_attention_lists_respect_the_managers_properties(scene: Scene, world: World):
    late = converted(scene, world, due_date="2020-01-01")[1]

    assert [i["id"] for i in listed(scene.sign_in(ADMIN), world, attention="overdue")] == [
        late["id"]
    ]
    assert listed(scene.sign_in(OTHER_MANAGER), world, attention="overdue") == []


def test_only_known_attention_filters_are_accepted(scene: Scene, world: World):
    response = scene.sign_in(MANAGER).get(f"{world.base}/work-orders?attention=everything")

    assert response.status_code == 422


# --- Who did what -----------------------------------------------------------------------


def test_staff_histories_show_the_role_each_author_acted_in(
    scene: Scene, world: World, db_session: Session
):
    request, order = converted(scene, world)
    contractor_id = membership_id(db_session, world, CONTRACTOR)
    assert assign_to(scene.sign_in(MANAGER), world, order["id"], contractor_id).status_code == 200
    contractor = scene.sign_in(CONTRACTOR)
    assert act(contractor, world, order["id"], "accept").status_code == 200
    entry = act(contractor, world, order["id"], "entries", kind="progress", body="On my way")
    assert entry.status_code == 201, entry.text

    history = scene.sign_in(ADMIN).get(f"{world.base}/work-orders/{order['id']}").json()["history"]
    roles = {(e["author_name"], e["author_role"]) for e in history}
    timeline = (
        scene.sign_in(MANAGER).get(f"{world.base}/requests/{request['id']}").json()["timeline"]
    )

    assert {role for _, role in roles} >= {"manager", "contractor"}
    assert {e["author_role"] for e in timeline} >= {"resident", "manager"}
    assert all(e["author_role"] is not None for e in history if e["author_name"])


def test_the_resident_and_contractor_views_stay_attribution_neutral(
    scene: Scene, world: World, db_session: Session
):
    request, order = converted(scene, world)
    contractor_id = membership_id(db_session, world, CONTRACTOR)
    assert assign_to(scene.sign_in(MANAGER), world, order["id"], contractor_id).status_code == 200

    resident_timeline = scene.sign_in(RESIDENT).get(f"{world.base}/my-requests/{request['id']}")
    job_view = scene.sign_in(CONTRACTOR).get(f"{world.base}/my-jobs/{order['id']}")

    assert "author_role" not in resident_timeline.text
    assert "author_role" not in job_view.text
    assert "Property team" in resident_timeline.text or "You" in resident_timeline.text


def test_converting_a_request_keeps_the_conversion_actor_out_of_their_own_inbox(
    scene: Scene, world: World
):
    request = submit(scene, world, scene.sign_in(RESIDENT))
    assert convert(scene.sign_in(MANAGER), world, request["id"]).status_code == 201

    assert heard(scene, world, MANAGER) == ["New request REQ-0001: Kitchen tap drips"]
    assert "Your request REQ-0001 is now being reviewed" in heard(scene, world, RESIDENT)
