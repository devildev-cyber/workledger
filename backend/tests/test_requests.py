import json
import uuid
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from support import PASSWORD, ClientFactory, SignedInClient, sign_in_as
from test_directory import (  # noqa: F401 - world is a fixture used below
    ELM_ADMIN,
    MANAGER,
    OTHER_MANAGER,
    RESIDENT,
    TODAY,
    World,
    assign,
    events,
    make_property,
    make_resident,
    make_unit,
    move_in,
    world,
)

from app.core.config import Settings
from app.models import EventType, RequestCounter, Role
from app.services.organizations import add_membership
from app.services.users import create_user

SECOND_RESIDENT = "sam@harbor.example"
PNG = b"\x89PNG\r\n\x1a\n" + b"fake image data " * 8
JPEG = b"\xff\xd8\xff\xe0" + b"fake jpeg data " * 8
PDF = b"%PDF-1.7\n" + b"fake pdf data " * 8
SECRET_NOTE = "Tenant has complained before, check the lease file"


@dataclass
class Scene:
    uploads: Path
    settings: Settings
    maple: dict[str, Any]
    oak: dict[str, Any]
    unit_1a: dict[str, Any]
    unit_2b: dict[str, Any]
    oak_unit: dict[str, Any]
    rae: dict[str, Any]
    sam: dict[str, Any]
    build: Any

    def sign_in(self, email: str) -> SignedInClient:
        return sign_in_as(lambda _settings: self.build(self.settings), email)


@pytest.fixture
def scene(
    world: World, db_session: Session, client_factory: ClientFactory, tmp_path: Path
) -> Scene:
    from sqlalchemy import select

    from app.models import Organization

    uploads = tmp_path / "uploads"
    settings = Settings(upload_dir=uploads, max_upload_megabytes=1)  # type: ignore[call-arg]

    harbor = db_session.scalar(select(Organization).where(Organization.id == world.harbor_id))
    sam_user = create_user(db_session, email=SECOND_RESIDENT, full_name="Sam", password=PASSWORD)
    add_membership(
        db_session, organization=harbor, user=sam_user, roles=[Role.RESIDENT], actor=None
    )
    db_session.commit()

    admin = sign_in_as(lambda _settings: client_factory(settings), "admin@harbor.example")
    maple = make_property(admin, world, "Maple Court")
    oak = make_property(admin, world, "Oak Terrace")
    unit_1a = make_unit(admin, world, maple["id"], "1A")
    unit_2b = make_unit(admin, world, maple["id"], "2B")
    oak_unit = make_unit(admin, world, oak["id"], "Cottage")
    rae = make_resident(admin, world, "Rae Resident", email=RESIDENT, phone="555-0111")
    sam = make_resident(admin, world, "Sam Second", email=SECOND_RESIDENT)
    move_in(admin, world, unit_1a["id"], rae["id"])
    move_in(admin, world, unit_2b["id"], sam["id"])
    assign(admin, world, maple["id"], MANAGER, db=db_session)
    return Scene(
        uploads, settings, maple, oak, unit_1a, unit_2b, oak_unit, rae, sam, client_factory
    )


def payload(unit_id: str, **changes: Any) -> dict[str, Any]:
    return {
        "unit_id": unit_id,
        "category": "plumbing",
        "urgency": "soon",
        "title": "Kitchen tap drips",
        "description": "The cold tap in the kitchen has dripped all week.",
        "location": "Kitchen",
        "access_notes": "Ring the bell, I work from home",
        **changes,
    }


def submit(
    scene: Scene, world: World, client: SignedInClient, unit_key: str = "unit_1a", **changes
):
    response = client.post(
        f"{world.base}/my-requests", json=payload(getattr(scene, unit_key)["id"], **changes)
    )
    assert response.status_code == 201, response.text
    return response.json()


# --- Submitting -------------------------------------------------------------------------


def test_resident_submits_a_request_and_receives_a_reference(
    scene: Scene, world: World, db_session: Session
):
    rae = scene.sign_in(RESIDENT)

    first = submit(scene, world, rae)
    second = submit(scene, world, rae, title="Light is out")

    assert first["reference"] == "REQ-0001"
    assert second["reference"] == "REQ-0002"
    assert first["status"] == "submitted"
    assert first["unit_label"] == "1A"
    assert first["property_name"] == "Maple Court"
    assert first["can_cancel"] is True
    assert [(e["kind"], e["author"]) for e in first["timeline"]] == [("submitted", "You")]

    recorded = events(db_session, EventType.REQUEST_SUBMITTED)
    assert len(recorded) == 2
    assert "drips" not in json.dumps(recorded[0].after)


def test_new_organizations_have_their_own_numbering(world: World, db_session: Session):
    elm_counter = db_session.scalar(
        select(RequestCounter).where(RequestCounter.organization_id == world.elm_id)
    )
    assert elm_counter is not None and elm_counter.last_number == 0


def test_resident_can_only_report_against_their_current_homes(scene: Scene, world: World):
    rae = scene.sign_in(RESIDENT)

    for unit in (scene.unit_2b, scene.oak_unit):
        response = rae.post(f"{world.base}/my-requests", json=payload(unit["id"]))
        assert response.status_code == 422

    unknown = rae.post(f"{world.base}/my-requests", json=payload(str(uuid.uuid4())))
    assert unknown.status_code == 422


@pytest.mark.parametrize(
    "changes",
    [
        {"title": "ab"},
        {"description": "   "},
        {"category": "magic"},
        {"urgency": "whenever"},
        {"title": "x" * 201},
        {"description": "x" * 5001},
    ],
)
def test_invalid_requests_are_rejected(scene: Scene, world: World, changes: dict[str, Any]):
    rae = scene.sign_in(RESIDENT)
    response = rae.post(f"{world.base}/my-requests", json=payload(scene.unit_1a["id"], **changes))
    assert response.status_code == 422


def test_only_residents_use_the_resident_endpoints(scene: Scene, world: World):
    for email in (MANAGER, "admin@harbor.example", "contractor@harbor.example"):
        client = scene.sign_in(email)
        assert client.get(f"{world.base}/my-requests").status_code == 403
        response = client.post(f"{world.base}/my-requests", json=payload(scene.unit_1a["id"]))
        assert response.status_code == 403


# --- What a resident can see -------------------------------------------------------------


def test_residents_see_only_their_own_requests(scene: Scene, world: World):
    rae = scene.sign_in(RESIDENT)
    sam = scene.sign_in(SECOND_RESIDENT)
    mine = submit(scene, world, rae)
    submit(scene, world, sam, unit_key="unit_2b", title="Door sticks")

    listed = rae.get(f"{world.base}/my-requests").json()
    assert [item["id"] for item in listed] == [mine["id"]]
    assert sam.get(f"{world.base}/my-requests/{mine['id']}").status_code == 404
    assert sam.post(f"{world.base}/my-requests/{mine['id']}/cancel").status_code == 404
    message = sam.post(f"{world.base}/my-requests/{mine['id']}/messages", json={"body": "hi"})
    assert message.status_code == 404


def test_resident_responses_never_include_internal_records(scene: Scene, world: World):
    rae = scene.sign_in(RESIDENT)
    manager = scene.sign_in(MANAGER)
    created = submit(scene, world, rae)
    url = f"{world.base}/requests/{created['id']}"

    manager.post(f"{url}/updates", json={"body": SECRET_NOTE})
    manager.post(
        f"{url}/updates", json={"body": "We will send a plumber", "visibility": "resident"}
    )
    hidden = manager.post(
        f"{url}/attachments", params={"filename": "lease.pdf"}, content=PDF
    ).json()
    shown = manager.post(
        f"{url}/attachments",
        params={"filename": "diagram.png", "visibility": "resident"},
        content=PNG,
    ).json()

    detail = rae.get(f"{world.base}/my-requests/{created['id']}")
    text = detail.text
    assert SECRET_NOTE not in text
    assert "lease.pdf" not in text
    assert hidden["id"] not in text
    assert "We will send a plumber" in text
    assert [a["id"] for a in detail.json()["attachments"]] == [shown["id"]]
    # Nothing about the staff member, and nothing beyond the fields a resident is meant to have.
    assert MANAGER not in text
    assert "Property team" in text
    assert set(detail.json()) == {
        "id", "reference", "status", "category", "urgency", "title", "property_name",
        "unit_label", "building_name", "created_at", "updated_at", "description", "location",
        "access_notes", "can_cancel", "can_message", "timeline", "attachments",
    }  # fmt: skip
    assert set(detail.json()["timeline"][0]) == {
        "id", "kind", "body", "status", "created_at", "author",
    }  # fmt: skip
    assert set(rae.get(f"{world.base}/my-requests").json()[0]) == {
        "id", "reference", "status", "category", "urgency", "title", "property_name",
        "unit_label", "building_name", "created_at", "updated_at",
    }  # fmt: skip

    denied = rae.get(f"{world.base}/my-requests/{created['id']}/attachments/{hidden['id']}")
    assert denied.status_code == 404
    allowed = rae.get(f"{world.base}/my-requests/{created['id']}/attachments/{shown['id']}")
    assert allowed.status_code == 200


def test_a_resident_who_moved_out_keeps_their_history_but_cannot_report_again(
    scene: Scene, world: World, client_factory: ClientFactory
):
    rae = scene.sign_in(RESIDENT)
    created = submit(scene, world, rae)

    admin = sign_in_as(lambda _s: client_factory(scene.settings), "admin@harbor.example")
    tenancy_id = admin.get(f"{world.base}/residents/{scene.rae['id']}").json()["tenancies"][0]["id"]
    ended = admin.post(
        f"{world.base}/tenancies/{tenancy_id}/end",
        json={"move_out_date": (TODAY - timedelta(days=1)).isoformat()},
    )
    assert ended.status_code == 200, ended.text

    assert [r["id"] for r in rae.get(f"{world.base}/my-requests").json()] == [created["id"]]
    assert rae.get(f"{world.base}/my-requests/{created['id']}").status_code == 200
    again = rae.post(f"{world.base}/my-requests", json=payload(scene.unit_1a["id"]))
    assert again.status_code == 422


# --- Withdrawing and messaging ------------------------------------------------------------


def test_resident_withdraws_a_request_nobody_has_started(scene: Scene, world: World):
    rae = scene.sign_in(RESIDENT)
    created = submit(scene, world, rae)

    response = rae.post(f"{world.base}/my-requests/{created['id']}/cancel")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "cancelled"
    assert body["can_cancel"] is False
    assert body["can_message"] is False
    assert [e["status"] for e in body["timeline"]] == ["submitted", "cancelled"]
    message = rae.post(f"{world.base}/my-requests/{created['id']}/messages", json={"body": "hi"})
    assert message.status_code == 409


def test_resident_cannot_withdraw_once_work_has_started(scene: Scene, world: World):
    rae = scene.sign_in(RESIDENT)
    manager = scene.sign_in(MANAGER)
    created = submit(scene, world, rae)
    manager.post(f"{world.base}/requests/{created['id']}/updates", json={"status": "in_progress"})

    response = rae.post(f"{world.base}/my-requests/{created['id']}/cancel")

    assert response.status_code == 409
    assert rae.get(f"{world.base}/my-requests/{created['id']}").json()["status"] == "in_progress"


def test_resident_messages_reach_staff(scene: Scene, world: World):
    rae = scene.sign_in(RESIDENT)
    manager = scene.sign_in(MANAGER)
    created = submit(scene, world, rae)

    sent = rae.post(
        f"{world.base}/my-requests/{created['id']}/messages", json={"body": "Home after 5pm"}
    )

    assert sent.status_code == 201
    assert sent.json()["timeline"][-1]["body"] == "Home after 5pm"
    staff_view = manager.get(f"{world.base}/requests/{created['id']}").json()
    assert staff_view["timeline"][-1]["author_name"] == RESIDENT


# --- Staff ---------------------------------------------------------------------------------


def test_managers_see_only_requests_in_their_properties(scene: Scene, world: World, client_factory):
    rae = scene.sign_in(RESIDENT)
    created = submit(scene, world, rae)

    manager = scene.sign_in(MANAGER)
    other = scene.sign_in(OTHER_MANAGER)
    admin = scene.sign_in("admin@harbor.example")

    assert [r["id"] for r in manager.get(f"{world.base}/requests").json()] == [created["id"]]
    assert other.get(f"{world.base}/requests").json() == []
    assert [r["id"] for r in admin.get(f"{world.base}/requests").json()] == [created["id"]]

    url = f"{world.base}/requests/{created['id']}"
    assert other.get(url).status_code == 404
    assert other.post(f"{url}/updates", json={"body": "x"}).status_code == 404
    assert (
        other.post(f"{url}/attachments", params={"filename": "a.png"}, content=PNG).status_code
        == 404
    )
    assert other.get(f"{url}/attachments/{uuid.uuid4()}").status_code == 404


def test_staff_can_filter_the_request_list(scene: Scene, world: World):
    rae = scene.sign_in(RESIDENT)
    admin = scene.sign_in("admin@harbor.example")
    first = submit(scene, world, rae)
    submit(scene, world, rae, title="Light is out")
    admin.post(f"{world.base}/requests/{first['id']}/updates", json={"status": "in_review"})

    in_review = admin.get(f"{world.base}/requests", params={"status": "in_review"}).json()
    by_property = admin.get(
        f"{world.base}/requests", params={"property_id": scene.oak["id"]}
    ).json()

    assert [r["reference"] for r in in_review] == ["REQ-0001"]
    assert by_property == []
    newest_first = admin.get(f"{world.base}/requests").json()
    assert [r["reference"] for r in newest_first] == ["REQ-0002", "REQ-0001"]


def test_staff_detail_includes_the_resident_and_the_full_timeline(scene: Scene, world: World):
    rae = scene.sign_in(RESIDENT)
    manager = scene.sign_in(MANAGER)
    created = submit(scene, world, rae)
    manager.post(f"{world.base}/requests/{created['id']}/updates", json={"body": SECRET_NOTE})

    detail = manager.get(f"{world.base}/requests/{created['id']}").json()

    assert detail["resident"]["phone"] == "555-0111"
    assert detail["resident"]["has_account"] is True
    assert [(e["kind"], e["visibility"]) for e in detail["timeline"]] == [
        ("submitted", "resident"),
        ("note", "internal"),
    ]
    assert detail["timeline"][1]["author_name"] == MANAGER


def test_status_changes_are_visible_to_the_resident_and_recorded(
    scene: Scene, world: World, db_session: Session
):
    rae = scene.sign_in(RESIDENT)
    manager = scene.sign_in(MANAGER)
    created = submit(scene, world, rae)
    url = f"{world.base}/requests/{created['id']}/updates"

    response = manager.post(
        url, json={"status": "in_review", "body": "Looking into it", "visibility": "resident"}
    )

    assert response.status_code == 201
    seen = rae.get(f"{world.base}/my-requests/{created['id']}").json()
    assert seen["status"] == "in_review"
    assert [(e["kind"], e["status"], e["body"]) for e in seen["timeline"][1:]] == [
        ("status_changed", "in_review", None),
        ("message", None, "Looking into it"),
    ]
    changed = events(db_session, EventType.REQUEST_STATUS_CHANGED)
    assert changed[0].before == {"status": "submitted"}
    assert changed[0].after == {"status": "in_review"}


def test_a_status_change_stays_visible_even_when_the_note_is_internal(scene: Scene, world: World):
    rae = scene.sign_in(RESIDENT)
    manager = scene.sign_in(MANAGER)
    created = submit(scene, world, rae)

    manager.post(
        f"{world.base}/requests/{created['id']}/updates",
        json={"status": "in_progress", "body": SECRET_NOTE},
    )

    seen = rae.get(f"{world.base}/my-requests/{created['id']}")
    assert SECRET_NOTE not in seen.text
    assert seen.json()["status"] == "in_progress"


def test_invalid_status_changes_are_refused(scene: Scene, world: World):
    rae = scene.sign_in(RESIDENT)
    manager = scene.sign_in(MANAGER)
    created = submit(scene, world, rae)
    url = f"{world.base}/requests/{created['id']}/updates"

    assert manager.post(url, json={}).status_code == 422
    assert manager.post(url, json={"visibility": "internal"}).status_code == 422
    assert manager.post(url, json={"status": "bogus"}).status_code == 422
    assert manager.post(url, json={"status": "submitted"}).status_code == 409
    assert manager.post(url, json={"status": "in_review"}).status_code == 201
    assert manager.post(url, json={"status": "in_review"}).status_code == 409
    assert manager.post(url, json={"status": "closed"}).status_code == 201
    assert manager.post(url, json={"status": "in_progress"}).status_code == 409
    # Internal notes can still be added to a finished request.
    assert manager.post(url, json={"body": "Filed"}).status_code == 201


def test_staff_enter_a_request_for_a_resident(scene: Scene, world: World):
    manager = scene.sign_in(MANAGER)
    rae = scene.sign_in(RESIDENT)

    response = manager.post(
        f"{world.base}/requests",
        json={**payload(scene.unit_1a["id"]), "resident_id": scene.rae["id"]},
    )

    assert response.status_code == 201, response.text
    assert response.json()["submitted_on_behalf"] is True
    seen = rae.get(f"{world.base}/my-requests").json()
    assert [r["reference"] for r in seen] == [response.json()["reference"]]
    timeline = rae.get(f"{world.base}/my-requests/{seen[0]['id']}").json()["timeline"]
    assert timeline[0]["author"] == "Property team"


def test_staff_cannot_enter_requests_outside_their_reach(scene: Scene, world: World):
    manager = scene.sign_in(MANAGER)
    admin = scene.sign_in("admin@harbor.example")
    url = f"{world.base}/requests"

    wrong_unit = {**payload(scene.unit_2b["id"]), "resident_id": scene.rae["id"]}
    assert admin.post(url, json=wrong_unit).status_code == 422

    out_of_scope = {**payload(scene.oak_unit["id"]), "resident_id": scene.rae["id"]}
    assert manager.post(url, json=out_of_scope).status_code == 404

    nobody = {**payload(scene.unit_1a["id"]), "resident_id": str(uuid.uuid4())}
    assert manager.post(url, json=nobody).status_code == 404


def test_other_organizations_cannot_reach_requests(
    scene: Scene, world: World, client_factory: ClientFactory
):
    created = submit(scene, world, scene.sign_in(RESIDENT))
    elm_admin = sign_in_as(client_factory, ELM_ADMIN)

    harbor_url = f"{world.base}/requests/{created['id']}"
    assert elm_admin.get(harbor_url).status_code == 404
    assert elm_admin.get(f"{world.base}/requests").status_code == 404
    elm_url = f"/api/organizations/{world.elm_id}/requests/{created['id']}"
    assert elm_admin.get(elm_url).status_code == 404
    assert elm_admin.get(f"/api/organizations/{world.elm_id}/requests").json() == []


# --- Attachments ---------------------------------------------------------------------------


def upload(client: SignedInClient, url: str, data: bytes, filename: str = "photo.png", **params):
    return client.post(url, params={"filename": filename, **params}, content=data)


def stored_files(scene: Scene) -> list[Path]:
    return [p for p in scene.uploads.rglob("*") if p.is_file()] if scene.uploads.exists() else []


def test_resident_attaches_a_photo_and_downloads_it_again(scene: Scene, world: World):
    rae = scene.sign_in(RESIDENT)
    created = submit(scene, world, rae)
    url = f"{world.base}/my-requests/{created['id']}/attachments"

    response = upload(rae, url, PNG, "leak under sink.png")

    assert response.status_code == 201, response.text
    assert response.json()["content_type"] == "image/png"
    assert response.json()["size_bytes"] == len(PNG)
    assert set(response.json()) == {"id", "filename", "content_type", "size_bytes", "created_at"}
    download = rae.get(f"{url}/{response.json()['id']}")
    assert download.content == PNG
    assert download.headers["content-type"] == "image/png"
    assert download.headers["x-content-type-options"] == "nosniff"
    assert download.headers["content-disposition"].startswith("inline")
    assert "no-store" in download.headers["cache-control"]
    assert len(stored_files(scene)) == 1


def test_documents_are_downloaded_rather_than_shown(scene: Scene, world: World):
    rae = scene.sign_in(RESIDENT)
    created = submit(scene, world, rae)
    url = f"{world.base}/my-requests/{created['id']}/attachments"

    saved = upload(rae, url, PDF, "invoice.pdf").json()

    download = rae.get(f"{url}/{saved['id']}")
    assert download.headers["content-type"] == "application/pdf"
    assert download.headers["content-disposition"].startswith("attachment")


@pytest.mark.parametrize(
    ("data", "filename"),
    [
        (b"<html><script>alert(1)</script></html>", "photo.png"),
        (b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>', "x.svg"),
        (b"MZ\x90\x00 executable", "photo.jpg"),
        (b"", "empty.png"),
        (b"GIF89a....", "animation.gif"),
    ],
)
def test_files_that_are_not_allowed_images_or_pdfs_are_refused(
    scene: Scene, world: World, data: bytes, filename: str
):
    rae = scene.sign_in(RESIDENT)
    created = submit(scene, world, rae)

    response = upload(rae, f"{world.base}/my-requests/{created['id']}/attachments", data, filename)

    assert response.status_code == 422
    assert stored_files(scene) == []
    assert rae.get(f"{world.base}/my-requests/{created['id']}").json()["attachments"] == []


def test_oversized_uploads_are_refused_without_being_stored(scene: Scene, world: World):
    rae = scene.sign_in(RESIDENT)
    created = submit(scene, world, rae)
    limit = scene.settings.max_upload_bytes

    too_big = upload(
        rae, f"{world.base}/my-requests/{created['id']}/attachments", PNG + b"0" * limit
    )
    just_fits = upload(
        rae,
        f"{world.base}/my-requests/{created['id']}/attachments",
        PNG + b"0" * (limit - len(PNG)),
    )

    assert too_big.status_code == 413
    assert just_fits.status_code == 201
    assert len(stored_files(scene)) == 1


def test_a_request_holds_a_limited_number_of_attachments(scene: Scene, world: World):
    rae = scene.sign_in(RESIDENT)
    created = submit(scene, world, rae)
    url = f"{world.base}/my-requests/{created['id']}/attachments"

    results = [upload(rae, url, PNG).status_code for _ in range(11)]

    assert results == [201] * 10 + [409]


def test_file_names_cannot_reach_the_file_system(scene: Scene, world: World):
    rae = scene.sign_in(RESIDENT)
    created = submit(scene, world, rae)
    url = f"{world.base}/my-requests/{created['id']}/attachments"

    saved = upload(rae, url, JPEG, "../../etc/passwd.jpg").json()
    windows = upload(rae, url, JPEG, "C:\\Users\\me\\holiday.jpg").json()

    assert saved["filename"] == "passwd.jpg"
    assert windows["filename"] == "holiday.jpg"
    root = scene.uploads.resolve()
    assert all(path.resolve().is_relative_to(root) for path in stored_files(scene))
    assert len(stored_files(scene)) == 2


def test_residents_cannot_attach_to_or_read_other_requests_or_finished_ones(
    scene: Scene, world: World
):
    rae = scene.sign_in(RESIDENT)
    sam = scene.sign_in(SECOND_RESIDENT)
    created = submit(scene, world, rae)
    url = f"{world.base}/my-requests/{created['id']}/attachments"
    saved = upload(rae, url, PNG).json()

    assert upload(sam, url, PNG).status_code == 404
    assert sam.get(f"{url}/{saved['id']}").status_code == 404

    rae.post(f"{world.base}/my-requests/{created['id']}/cancel")
    assert upload(rae, url, PNG).status_code == 409


def test_an_attachment_cannot_be_read_through_another_request(scene: Scene, world: World):
    rae = scene.sign_in(RESIDENT)
    first = submit(scene, world, rae)
    second = submit(scene, world, rae, title="Light is out")
    saved = upload(rae, f"{world.base}/my-requests/{first['id']}/attachments", PNG).json()

    response = rae.get(f"{world.base}/my-requests/{second['id']}/attachments/{saved['id']}")

    assert response.status_code == 404


def test_staff_uploads_are_internal_unless_shared(scene: Scene, world: World):
    rae = scene.sign_in(RESIDENT)
    manager = scene.sign_in(MANAGER)
    created = submit(scene, world, rae)
    url = f"{world.base}/requests/{created['id']}/attachments"

    private = upload(manager, url, PDF, "quote.pdf").json()
    shared = upload(manager, url, PNG, "plan.png", visibility="resident").json()

    assert private["visibility"] == "internal"
    assert shared["visibility"] == "resident"
    visible = rae.get(f"{world.base}/my-requests/{created['id']}").json()["attachments"]
    assert [a["filename"] for a in visible] == ["plan.png"]
    both = manager.get(f"{world.base}/requests/{created['id']}").json()["attachments"]
    assert {a["filename"] for a in both} == {"quote.pdf", "plan.png"}
    assert manager.get(f"{url}/{private['id']}").content == PDF
