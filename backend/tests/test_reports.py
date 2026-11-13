import csv
import io
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from support import PASSWORD, ClientFactory, SignedInClient, sign_in_as

from app.core.clock import utc_now
from app.models import (
    ActivityEvent,
    EventType,
    MaintenanceRequest,
    Organization,
    Property,
    Role,
    Unit,
    WorkOrder,
)
from app.services import exports
from app.services.organizations import add_membership, create_organization
from app.services.seed import ADMIN_EMAIL, MANAGER_EMAIL, seed_demo_organization
from app.services.users import create_user

OWNER = "owner@demo.example"
CONTRACTOR = "contractor@demo.example"
RESIDENT = "resident@demo.example"
OUTSIDER = "admin@elsewhere.example"
BOM = "\ufeff"


@pytest.fixture
def seeded(db_session: Session) -> Organization:
    result = seed_demo_organization(db_session, password=PASSWORD)
    db_session.commit()
    return result.organization


@pytest.fixture
def base(seeded: Organization) -> str:
    return f"/api/organizations/{seeded.id}"


@pytest.fixture
def admin(client_factory: ClientFactory, seeded: Organization) -> SignedInClient:
    return sign_in_as(client_factory, ADMIN_EMAIL)


@pytest.fixture
def manager(client_factory: ClientFactory, seeded: Organization) -> SignedInClient:
    return sign_in_as(client_factory, MANAGER_EMAIL)


@pytest.fixture
def owner(client_factory: ClientFactory, seeded: Organization) -> SignedInClient:
    return sign_in_as(client_factory, OWNER)


def report(client: SignedInClient, base: str, **params: Any) -> dict[str, Any]:
    response = client.get(f"{base}/reports", params=params)
    assert response.status_code == 200, response.text
    return response.json()


def table(response: Any) -> list[dict[str, str]]:
    assert response.status_code == 200, response.text
    assert response.text.startswith(BOM)
    return list(csv.DictReader(io.StringIO(response.text.removeprefix(BOM))))


def property_named(db: Session, name: str) -> Property:
    return db.scalars(select(Property).where(Property.name == name)).one()


def order_titled(db: Session, fragment: str) -> WorkOrder:
    db.expire_all()
    return next(
        item for item in db.scalars(select(WorkOrder)) if fragment.lower() in item.title.lower()
    )


# --- The seeded demonstration firm: every metric against known data --------------------


def test_requests_match_the_seeded_data(admin: SignedInClient, base: str) -> None:
    requests = report(admin, base)["requests"]

    # Ten were submitted: 4 submitted, 1 in review, 3 in progress, 1 resolved, 1 closed.
    assert requests["submitted_in_period"] == 10
    assert requests["open"] == 8
    assert requests["waiting_for_triage"] == 5
    assert requests["by_status"]["submitted"] == 4
    assert requests["by_status"]["in_review"] == 1


def test_work_orders_match_the_seeded_data(admin: SignedInClient, base: str) -> None:
    work_orders = report(admin, base)["work_orders"]

    assert work_orders["by_status"] == {
        "awaiting_approval": 1,
        "closed": 1,
        "completed": 1,
        "on_hold": 1,
        "ready_for_review": 1,
    }
    # Completed and closed work is finished, so three remain open.
    assert work_orders["open"] == 3
    assert work_orders["overdue"] == 1
    assert work_orders["blocked"] == 2
    assert work_orders["created_in_period"] == 5
    assert sum(work_orders["created_by_category"].values()) == 5
    assert {
        item["property_name"]: item["count"] for item in work_orders["created_by_property"]
    } == {
        "Maple Court": 2,
        "Oak Terrace Houses": 2,
        "Riverside Lofts": 1,
    }


def test_spend_counts_verified_work_only_and_is_never_added_across_currencies(
    admin: SignedInClient, base: str, db_session: Session
) -> None:
    spend = report(admin, base)["spend"]

    # The radiator ($185.00) and the smoke detectors ($45.00). The dishwasher is only estimated.
    assert spend["work_orders"] == 2
    assert spend["total"] == [{"currency": "USD", "total_cents": 23_000}]
    by_property = {item["property_name"]: item["total_cents"] for item in spend["by_property"]}
    assert by_property == {"Maple Court": 18_500, "Oak Terrace Houses": 4_500}

    order_titled(db_session, "smoke").currency = "EUR"
    db_session.commit()
    spend = report(admin, base)["spend"]
    assert spend["total"] == [
        {"currency": "EUR", "total_cents": 4_500},
        {"currency": "USD", "total_cents": 18_500},
    ]


def test_approvals_match_the_seeded_data(admin: SignedInClient, base: str) -> None:
    approvals = report(admin, base)["approvals"]

    # Three estimates; the faucet's is under Maple Court's threshold.
    assert approvals["estimates_recorded"] == 3
    assert approvals["needed_approval"] == 2
    assert (approvals["pending"], approvals["approved"], approvals["rejected"]) == (1, 1, 0)
    assert approvals["replaced"] == 0
    assert approvals["pending_amounts"] == [{"currency": "USD", "total_cents": 145_000}]
    assert approvals["approved_amounts"] == [{"currency": "USD", "total_cents": 132_000}]
    assert approvals["average_decision_hours"] is not None


def test_contractor_workload_matches_the_seeded_data(admin: SignedInClient, base: str) -> None:
    [contractor] = report(admin, base)["contractors"]

    # The faucet is accepted, the water heater is waiting for an answer and overdue, and the
    # radiator was finished and verified.
    assert contractor["active_jobs"] == 2
    assert contractor["awaiting_response"] == 1
    assert contractor["overdue"] == 1
    assert contractor["completed"] == 1
    assert (contractor["sent_back"], contractor["declined"]) == (0, 0)


def test_sending_work_back_is_counted_against_the_contractor(
    manager: SignedInClient, base: str, db_session: Session
) -> None:
    faucet = order_titled(db_session, "faucet")
    sent = manager.post(
        f"{base}/work-orders/{faucet.id}/send-back", json={"reason": "Still drips at the base"}
    )
    assert sent.status_code == 200, sent.text

    [contractor] = report(manager, base)["contractors"]

    assert contractor["sent_back"] == 1


def test_a_declined_job_is_counted_against_the_contractor(
    client_factory: ClientFactory,
    admin: SignedInClient,
    manager: SignedInClient,
    base: str,
    db_session: Session,
) -> None:
    contractor = sign_in_as(client_factory, CONTRACTOR)
    water = order_titled(db_session, "hot water")
    declined = contractor.post(
        f"{base}/my-jobs/{water.id}/decline", json={"reason": "Booked for the next month"}
    )
    assert declined.status_code == 204, declined.text

    [row] = report(admin, base)["contractors"]
    assert row["declined"] == 1
    # The declined job is no longer theirs, so only the faucet remains.
    assert (row["active_jobs"], row["awaiting_response"], row["overdue"]) == (1, 0, 0)
    # Oak Terrace is out of the manager's reach, and so is the decline.
    [row] = report(manager, base)["contractors"]
    assert row["declined"] == 0


def test_no_repeat_issue_is_reported_when_nothing_repeats(admin: SignedInClient, base: str) -> None:
    assert report(admin, base)["repeat_issues"] == []


def test_the_same_problem_in_the_same_place_is_a_repeat_issue(
    admin: SignedInClient, manager: SignedInClient, base: str, db_session: Session
) -> None:
    faucet = order_titled(db_session, "faucet")
    for _ in range(2):
        response = manager.post(
            f"{base}/work-orders",
            json={
                "property_id": str(faucet.property_id),
                "unit_id": str(faucet.unit_id),
                "title": "Tap drips again",
                "scope": "Drips overnight.",
                "category": faucet.category,
                "priority": "routine",
            },
        )
        assert response.status_code == 201, response.text
    # Plumbing in the common areas of the same property is a different place.
    response = manager.post(
        f"{base}/work-orders",
        json={
            "property_id": str(faucet.property_id),
            "title": "Lobby tap",
            "scope": "Check it.",
            "category": faucet.category,
            "priority": "routine",
        },
    )
    assert response.status_code == 201, response.text

    [issue] = report(admin, base)["repeat_issues"]

    assert (issue["property_name"], issue["category"], issue["count"]) == (
        "Maple Court",
        faucet.category,
        3,
    )
    assert issue["unit_label"] == "2B"
    assert len(issue["references"]) == 3
    assert all(item.startswith("WO-") for item in issue["references"])


def test_cancelled_work_is_not_a_repeat(
    admin: SignedInClient, manager: SignedInClient, base: str, db_session: Session
) -> None:
    faucet = order_titled(db_session, "faucet")
    created = manager.post(
        f"{base}/work-orders",
        json={
            "property_id": str(faucet.property_id),
            "unit_id": str(faucet.unit_id),
            "title": "Tap, entered twice by mistake",
            "scope": "Duplicate entry.",
            "category": faucet.category,
            "priority": "routine",
        },
    ).json()
    cancelled = manager.post(
        f"{base}/work-orders/{created['id']}/status",
        json={"status": "cancelled", "note": "Entered twice"},
    )
    assert cancelled.status_code == 200, cancelled.text

    assert report(admin, base)["repeat_issues"] == []


def test_resolution_time_runs_from_the_residents_report_to_verification(
    admin: SignedInClient, base: str, db_session: Session
) -> None:
    radiator = order_titled(db_session, "radiator")
    smoke = order_titled(db_session, "smoke")
    now = utc_now()
    for work_order, wait_hours in ((radiator, 10), (smoke, 30)):
        submitted = now - timedelta(hours=wait_hours)
        work_order.verified_at = now
        # The work order was made later than the request: the resident's wait is what counts.
        work_order.created_at = now - timedelta(hours=1)
        for item in db_session.scalars(
            select(MaintenanceRequest).where(MaintenanceRequest.work_order_id == work_order.id)
        ):
            item.created_at = submitted
    radiator.priority = "urgent"
    smoke.priority = "routine"
    db_session.commit()

    resolution = report(admin, base)["resolution"]

    assert resolution["completed"] == 2
    assert resolution["average_hours"] == 20.0
    assert resolution["slowest_hours"] == 30.0
    assert {item["priority"]: item["average_hours"] for item in resolution["by_priority"]} == {
        "routine": 30.0,
        "urgent": 10.0,
    }


def test_a_work_order_without_a_request_is_timed_from_its_creation(
    admin: SignedInClient, base: str, db_session: Session
) -> None:
    smoke = order_titled(db_session, "smoke")
    radiator = order_titled(db_session, "radiator")
    now = utc_now()
    for item in db_session.scalars(select(MaintenanceRequest)):
        if item.work_order_id in (smoke.id, radiator.id):
            item.work_order_id = None
    smoke.created_at = now - timedelta(hours=6)
    smoke.verified_at = now
    radiator.verified_at = None
    db_session.commit()

    resolution = report(admin, base)["resolution"]

    assert resolution["completed"] == 1
    assert resolution["average_hours"] == 6.0


def test_the_period_decides_what_happened_but_not_what_is_open_now(
    admin: SignedInClient, base: str, db_session: Session
) -> None:
    radiator = order_titled(db_session, "radiator")
    radiator.verified_at = datetime(2024, 3, 10, 12, tzinfo=UTC)
    db_session.commit()

    last_year = report(admin, base, **{"from": "2024-03-01", "to": "2024-03-31"})
    now = report(admin, base)

    # Spend and resolution use the period, so March 2024 holds only the radiator.
    assert last_year["spend"]["total"] == [{"currency": "USD", "total_cents": 18_500}]
    assert last_year["resolution"]["completed"] == 1
    assert now["spend"]["total"] == [{"currency": "USD", "total_cents": 4_500}]
    # Nothing was created in March 2024, but the same work is open today either way.
    assert last_year["work_orders"]["created_in_period"] == 0
    assert last_year["requests"]["submitted_in_period"] == 0
    assert last_year["work_orders"]["open"] == now["work_orders"]["open"] == 3
    assert last_year["requests"]["open"] == now["requests"]["open"] == 8


def test_both_ends_of_the_period_are_included(
    admin: SignedInClient, base: str, db_session: Session
) -> None:
    radiator = order_titled(db_session, "radiator")
    radiator.verified_at = datetime(2024, 3, 31, 23, 59, 59, tzinfo=UTC)
    db_session.commit()

    last_day = report(admin, base, **{"from": "2024-03-31", "to": "2024-03-31"})
    next_day = report(admin, base, **{"from": "2024-04-01", "to": "2024-04-01"})

    assert last_day["resolution"]["completed"] == 1
    assert next_day["resolution"]["completed"] == 0


def test_the_default_period_is_the_last_ninety_days(admin: SignedInClient, base: str) -> None:
    result = report(admin, base)

    end = utc_now().date()
    assert result["period_end"] == end.isoformat()
    assert result["period_start"] == (end - timedelta(days=89)).isoformat()


@pytest.mark.parametrize(
    "params",
    [
        {"from": "2025-02-01", "to": "2025-01-01"},
        {"from": "2000-01-01", "to": "2025-01-01"},
        {"from": "last week"},
        {"property_id": "not-an-id"},
    ],
)
def test_an_impossible_period_is_refused(
    admin: SignedInClient, base: str, params: dict[str, str]
) -> None:
    assert admin.get(f"{base}/reports", params=params).status_code == 422
    assert admin.get(f"{base}/reports/export/work-orders.csv", params=params).status_code == 422


def test_a_report_can_be_narrowed_to_one_property(
    admin: SignedInClient, base: str, db_session: Session
) -> None:
    oak = property_named(db_session, "Oak Terrace Houses")

    result = report(admin, base, property_id=str(oak.id))

    assert result["work_orders"]["created_in_period"] == 2
    assert result["work_orders"]["overdue"] == 1
    assert result["spend"]["total"] == [{"currency": "USD", "total_cents": 4_500}]
    assert result["approvals"]["needed_approval"] == 1
    assert [item["property_name"] for item in result["work_orders"]["created_by_property"]] == [
        "Oak Terrace Houses"
    ]


# --- Who may read a report, and of what --------------------------------------------------


def test_a_manager_reports_only_on_the_properties_they_look_after(
    manager: SignedInClient, base: str
) -> None:
    result = report(manager, base)

    # Oak Terrace is out of reach: no overdue water heater, no smoke detector spend.
    assert result["work_orders"]["created_in_period"] == 3
    assert result["work_orders"]["by_status"] == {
        "completed": 1,
        "on_hold": 1,
        "ready_for_review": 1,
    }
    assert result["work_orders"]["overdue"] == 0
    assert result["work_orders"]["blocked"] == 1
    assert result["spend"]["total"] == [{"currency": "USD", "total_cents": 18_500}]
    assert result["approvals"]["needed_approval"] == 1
    assert result["approvals"]["pending"] == 0
    assert all(
        item["property_name"] != "Oak Terrace Houses"
        for section in (
            result["work_orders"]["created_by_property"],
            result["spend"]["by_property"],
            result["approvals"]["by_property"],
        )
        for item in section
    )
    [contractor] = result["contractors"]
    assert (contractor["active_jobs"], contractor["awaiting_response"]) == (1, 0)
    assert result["requests"]["submitted_in_period"] < 10


def test_a_manager_cannot_ask_about_a_property_they_do_not_look_after(
    manager: SignedInClient, base: str, db_session: Session
) -> None:
    oak = property_named(db_session, "Oak Terrace Houses")

    for path in ("", "/export/work-orders.csv", "/export/requests.csv", "/export/estimates.csv"):
        response = manager.get(f"{base}/reports{path}", params={"property_id": str(oak.id)})
        assert response.status_code == 404, path


def test_a_property_that_does_not_exist_is_not_found(admin: SignedInClient, base: str) -> None:
    missing = "00000000-0000-4000-8000-000000000000"

    assert admin.get(f"{base}/reports", params={"property_id": missing}).status_code == 404


@pytest.mark.parametrize("email", [RESIDENT, CONTRACTOR, OWNER])
def test_only_staff_may_read_reports_or_export_them(
    client_factory: ClientFactory, base: str, email: str
) -> None:
    client = sign_in_as(client_factory, email)

    for path in (
        "",
        "/export/work-orders.csv",
        "/export/requests.csv",
        "/export/estimates.csv",
    ):
        assert client.get(f"{base}/reports{path}").status_code == 403, path


def test_reports_need_a_signed_in_user(client_factory: ClientFactory, base: str) -> None:
    client = client_factory(None)

    assert client.get(f"{base}/reports").status_code == 401
    assert client.get(f"{base}/reports/export/work-orders.csv").status_code == 401


def test_another_firms_administrator_sees_nothing(
    client_factory: ClientFactory, base: str, db_session: Session
) -> None:
    other = create_organization(db_session, name="Elsewhere", actor=None)
    user = create_user(db_session, email=OUTSIDER, full_name="Outsider", password=PASSWORD)
    add_membership(
        db_session, organization=other, user=user, roles=[Role.ADMINISTRATOR], actor=None
    )
    db_session.commit()
    outsider = sign_in_as(client_factory, OUTSIDER)

    assert outsider.get(f"{base}/reports").status_code in (403, 404)
    assert outsider.get(f"{base}/reports/export/work-orders.csv").status_code in (403, 404)
    own = report(outsider, f"/api/organizations/{other.id}")
    assert own["work_orders"]["created_in_period"] == 0
    assert own["requests"]["open"] == 0
    assert own["contractors"] == []
    assert own["spend"]["total"] == []


# --- The owner's summary -----------------------------------------------------------------


def test_an_owner_sees_the_approvals_at_their_own_properties(
    owner: SignedInClient, base: str
) -> None:
    response = owner.get(f"{base}/my-approvals/summary")

    assert response.status_code == 200, response.text
    approvals = response.json()["approvals"]
    # Riverside Lofts and Oak Terrace: the dishwasher is approved and the water heater waits.
    assert approvals["needed_approval"] == 2
    assert (approvals["pending"], approvals["approved"]) == (1, 1)
    assert {item["property_name"] for item in approvals["by_property"]} == {
        "Oak Terrace Houses",
        "Riverside Lofts",
    }
    # Spending, contractors and the rest of the staff report are not part of an owner's summary.
    assert set(response.json()) == {"period_start", "period_end", "approvals"}


def test_an_owner_sees_only_the_properties_they_own(
    owner: SignedInClient, admin: SignedInClient, base: str, db_session: Session
) -> None:
    oak = property_named(db_session, "Oak Terrace Houses")
    removed = admin.put(f"{base}/properties/{oak.id}/owners", json={"membership_ids": []})
    assert removed.status_code == 200, removed.text

    approvals = owner.get(f"{base}/my-approvals/summary").json()["approvals"]

    assert approvals["needed_approval"] == 1
    assert {item["property_name"] for item in approvals["by_property"]} == {"Riverside Lofts"}


@pytest.mark.parametrize("path", ["/summary", "/export.csv"])
def test_the_owner_routes_are_for_owners_only(
    admin: SignedInClient, manager: SignedInClient, base: str, path: str
) -> None:
    assert admin.get(f"{base}/my-approvals{path}").status_code == 403
    assert manager.get(f"{base}/my-approvals{path}").status_code == 403


def test_the_owner_routes_do_not_swallow_an_approval_id(owner: SignedInClient, base: str) -> None:
    listing = owner.get(f"{base}/my-approvals")

    assert listing.status_code == 200
    assert isinstance(listing.json(), list)


# --- Exports -----------------------------------------------------------------------------


def test_work_orders_are_exported_as_a_spreadsheet_file(admin: SignedInClient, base: str) -> None:
    response = admin.get(f"{base}/reports/export/work-orders.csv")

    rows = table(response)
    assert response.headers["content-type"].startswith("text/csv")
    assert response.headers["content-disposition"].startswith("attachment;")
    assert response.headers["content-disposition"].endswith('.csv"')
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert len(rows) == 5
    by_reference = {row["Reference"]: row for row in rows}
    assert all(reference.startswith("WO-") for reference in by_reference)
    radiator = next(row for row in rows if "radiator" in row["Title"].lower())
    assert radiator["Final cost"] == "185.00"
    assert radiator["Currency"] == "USD"
    assert radiator["Property"] == "Maple Court"
    assert radiator["Contractor"] != ""
    assert radiator["Status"] == "completed"
    assert radiator["Hours to resolve"] != ""
    overdue = [row for row in rows if row["Overdue"] == "Yes"]
    assert [row["Status"] for row in overdue] == ["awaiting_approval"]


def test_requests_and_estimates_are_exported_too(admin: SignedInClient, base: str) -> None:
    requests = table(admin.get(f"{base}/reports/export/requests.csv"))
    estimates = table(admin.get(f"{base}/reports/export/estimates.csv"))

    assert len(requests) == 10
    assert all(row["Reference"].startswith("REQ-") for row in requests)
    assert sum(1 for row in requests if row["Work order"]) == 5
    assert len(estimates) == 3
    approved = next(row for row in estimates if row["Status"] == "approved")
    assert approved["Amount"] == "1320.00"
    assert approved["Needed approval"] == "Yes"
    assert approved["Decided by"] != ""
    assert next(row for row in estimates if row["Amount"] == "140.00")["Needed approval"] == "No"


def test_exports_leave_out_what_people_wrote_and_who_they_are(
    admin: SignedInClient, base: str
) -> None:
    exported = "".join(
        admin.get(f"{base}/reports/export/{name}.csv").text
        for name in ("work-orders", "requests", "estimates")
    )

    # Residents' names, contact details and access instructions.
    for private in ("Riley Chen", "demo.example", "555-01", "Gate code", "Buzz 2B", "Lockbox"):
        assert private not in exported
    # Descriptions, scope, resolutions, notes and quotes' text.
    for private in (
        "Valve replaced and the radiator bled",
        "Supply and fit a new dishwasher",
        "Ring the bell and wait",
        "Replaced the cartridge and ran the tap",
        "Approved. The old unit",
    ):
        assert private not in exported
    header = table(admin.get(f"{base}/reports/export/work-orders.csv"))[0].keys()
    assert not {"Scope", "Resolution", "Description", "Notes", "Resident"} & set(header)


def test_a_manager_exports_only_their_properties(manager: SignedInClient, base: str) -> None:
    work_orders = table(manager.get(f"{base}/reports/export/work-orders.csv"))
    requests = table(manager.get(f"{base}/reports/export/requests.csv"))
    estimates = table(manager.get(f"{base}/reports/export/estimates.csv"))

    assert len(work_orders) == 3
    assert {row["Property"] for row in work_orders + requests + estimates} <= {
        "Maple Court",
        "Riverside Lofts",
    }
    assert len(estimates) == 2
    assert 0 < len(requests) < 10


def test_the_export_follows_the_period(admin: SignedInClient, base: str) -> None:
    response = admin.get(
        f"{base}/reports/export/work-orders.csv", params={"from": "2001-01-01", "to": "2001-01-31"}
    )

    assert table(response) == []
    assert response.text.startswith(BOM + "Reference,")


def test_a_cell_that_looks_like_a_formula_is_defused(
    admin: SignedInClient, base: str, db_session: Session
) -> None:
    radiator = order_titled(db_session, "radiator")
    smoke = order_titled(db_session, "smoke")
    radiator.title = '=HYPERLINK("http://evil.example","Click")'
    smoke.title = "@SUM(1+1)"
    db_session.commit()

    rows = table(admin.get(f"{base}/reports/export/work-orders.csv"))

    titles = {row["Title"] for row in rows}
    assert '\'=HYPERLINK("http://evil.example","Click")' in titles
    assert "'@SUM(1+1)" in titles
    assert not any(title.startswith(("=", "@", "+", "-")) for title in titles)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("=1+1", "'=1+1"),
        ("+1", "'+1"),
        ("-1", "'-1"),
        ("@cmd", "'@cmd"),
        ("\tTab", "'\tTab"),
        ("\rReturn", "'\rReturn"),
        ("Kitchen tap", "Kitchen tap"),
        ("1=1", "1=1"),
        (None, ""),
        (42, "42"),
    ],
)
def test_safe_cell(value: Any, expected: str) -> None:
    assert exports.safe_cell(value) == expected


@pytest.mark.parametrize(
    ("cents", "text"),
    [
        (None, ""),
        (0, "0.00"),
        (5, "0.05"),
        (18_500, "185.00"),
        (132_001, "1320.01"),
        (-250, "-2.50"),
    ],
)
def test_money_is_formatted_from_whole_cents(cents: int | None, text: str) -> None:
    assert exports.money(cents) == text


def test_an_export_that_is_too_big_is_refused(
    admin: SignedInClient, base: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(exports, "MAX_ROWS", 2)

    response = admin.get(f"{base}/reports/export/work-orders.csv")

    assert response.status_code == 422
    assert "shorter period" in response.json()["detail"]


def test_taking_data_out_leaves_a_record(
    manager: SignedInClient, base: str, db_session: Session
) -> None:
    manager.get(f"{base}/reports/export/work-orders.csv")
    manager.get(
        f"{base}/reports/export/estimates.csv", params={"from": "2001-01-01", "to": "2001-01-31"}
    )

    db_session.expire_all()
    recorded = list(
        db_session.scalars(
            select(ActivityEvent)
            .where(ActivityEvent.event_type == EventType.REPORT_EXPORTED)
            .order_by(ActivityEvent.occurred_at)
        )
    )
    assert [item.after["export"] for item in recorded] == ["work-orders", "estimates"]
    assert recorded[0].after["rows"] == 3
    assert recorded[1].after["rows"] == 0
    assert recorded[0].after["period_end"] == utc_now().date().isoformat()
    assert all(item.actor_user_id is not None for item in recorded)
    # The record says what and how much, never the data itself.
    assert "Maple" not in str(recorded[0].after)


def test_a_refused_export_leaves_no_record(
    manager: SignedInClient, base: str, db_session: Session
) -> None:
    oak = property_named(db_session, "Oak Terrace Houses")

    manager.get(f"{base}/reports/export/work-orders.csv", params={"property_id": str(oak.id)})

    assert not db_session.scalars(
        select(ActivityEvent).where(ActivityEvent.event_type == EventType.REPORT_EXPORTED)
    ).all()


def test_an_owner_exports_the_decisions_at_their_own_properties(
    owner: SignedInClient, base: str
) -> None:
    response = owner.get(f"{base}/my-approvals/export.csv")

    rows = table(response)
    assert response.headers["cache-control"] == "no-store"
    assert {row["Property"] for row in rows} == {"Riverside Lofts", "Oak Terrace Houses"}
    assert len(rows) == 2
    approved = next(row for row in rows if row["Status"] == "approved")
    assert approved["Amount"] == "1320.00"
    # The owner already sees their own reason, but not the contractor's description or notes.
    assert approved["Reason"].startswith("Approved.")
    assert "Supply and fit" not in response.text
    assert "Maple Court" not in response.text
    assert "Riley Chen" not in response.text


def test_an_owner_export_is_empty_without_properties(
    owner: SignedInClient, admin: SignedInClient, base: str, db_session: Session
) -> None:
    for name in ("Riverside Lofts", "Oak Terrace Houses"):
        found = property_named(db_session, name)
        assert (
            admin.put(
                f"{base}/properties/{found.id}/owners", json={"membership_ids": []}
            ).status_code
            == 200
        )

    response = owner.get(f"{base}/my-approvals/export.csv")

    assert table(response) == []


def test_an_owner_export_is_recorded_like_any_other(
    owner: SignedInClient, base: str, db_session: Session
) -> None:
    owner.get(f"{base}/my-approvals/export.csv")

    db_session.expire_all()
    [recorded] = db_session.scalars(
        select(ActivityEvent).where(ActivityEvent.event_type == EventType.REPORT_EXPORTED)
    ).all()
    assert recorded.after["export"] == "approvals"
    assert recorded.after["rows"] == 2


def test_units_are_named_in_exports_without_the_residents(
    admin: SignedInClient, base: str, db_session: Session
) -> None:
    rows = table(admin.get(f"{base}/reports/export/requests.csv"))
    labels = set(db_session.scalars(select(Unit.label)))

    assert {row["Unit"] for row in rows} <= labels
