"""The product at its upper target size: about 300 units and three years of history.

These are guards, not benchmarks. The limits are far above what the numbers were when they were
written (every request below took well under half a second), so a slow machine does not fail
them, but a change that makes something scan or build everything twice does.
"""

import time
from collections.abc import Iterator
from typing import Any

import pytest
from sqlalchemy.orm import Session
from support import PASSWORD, ClientFactory, SignedInClient, sign_in_as
from volume import Volume, build_volume

SLOWEST_SECONDS = 3.0
LARGEST_RESPONSE_BYTES = 1_000_000


@pytest.fixture
def volume(db_session: Session) -> Iterator[Volume]:
    yield build_volume(db_session, password=PASSWORD)


def timed(client: SignedInClient, path: str) -> tuple[Any, float]:
    started = time.perf_counter()
    response = client.get(path)
    return response, time.perf_counter() - started


def test_the_generated_firm_has_the_intended_size(volume: Volume) -> None:
    assert volume.units == 300
    assert volume.requests == 3_600
    assert 2_000 < volume.work_orders < 3_000


def test_staff_screens_stay_fast_with_years_of_history(
    client_factory: ClientFactory, volume: Volume
) -> None:
    base = f"/api/organizations/{volume.organization_id}"
    admin = sign_in_as(client_factory, volume.admin_email)
    manager = sign_in_as(client_factory, volume.manager_email)
    paths = [
        (admin, "/requests"),
        (admin, "/requests?needs_triage=true"),
        (admin, "/work-orders"),
        (admin, "/work-orders?attention=overdue"),
        (admin, "/work-orders?attention=blocked"),
        (manager, "/work-orders"),
        (manager, "/requests"),
        (admin, "/properties"),
        (admin, "/residents"),
        (admin, "/notifications"),
        (admin, "/notifications?unread_only=true"),
        (admin, "/activity"),
    ]

    for client, path in paths:
        response, seconds = timed(client, base + path)
        assert response.status_code == 200, path
        assert seconds < SLOWEST_SECONDS, f"{path} took {seconds:.1f} s"
        assert len(response.content) < LARGEST_RESPONSE_BYTES, path


def test_reports_and_exports_stay_fast_over_the_whole_history(
    client_factory: ClientFactory, volume: Volume
) -> None:
    base = f"/api/organizations/{volume.organization_id}"
    admin = sign_in_as(client_factory, volume.admin_email)
    whole = "from=2023-01-01&to=2026-12-31"

    for path in (
        "/reports",
        f"/reports?{whole}",
        f"/reports/export/work-orders.csv?{whole}",
        f"/reports/export/requests.csv?{whole}",
        f"/reports/export/estimates.csv?{whole}",
    ):
        response, seconds = timed(admin, base + path)
        assert response.status_code == 200, path
        assert seconds < SLOWEST_SECONDS, f"{path} took {seconds:.1f} s"
        assert len(response.content) < LARGEST_RESPONSE_BYTES, path


def test_the_report_is_complete_and_the_repeat_list_is_capped(
    client_factory: ClientFactory, volume: Volume
) -> None:
    base = f"/api/organizations/{volume.organization_id}"
    admin = sign_in_as(client_factory, volume.admin_email)

    report = admin.get(f"{base}/reports", params={"from": "2023-01-01", "to": "2026-12-31"}).json()

    assert report["requests"]["submitted_in_period"] == volume.requests
    assert report["work_orders"]["created_in_period"] == volume.work_orders
    assert len(report["work_orders"]["created_by_property"]) == 10
    assert len(report["contractors"]) == 8
    assert 0 < len(report["repeat_issues"]) <= 50
    counts = [item["count"] for item in report["repeat_issues"]]
    assert counts == sorted(counts, reverse=True)


def test_other_roles_stay_fast_too(client_factory: ClientFactory, volume: Volume) -> None:
    base = f"/api/organizations/{volume.organization_id}"
    for email, path in (
        (volume.owner_email, "/my-approvals"),
        (volume.owner_email, "/my-approvals/summary"),
        (volume.contractor_email, "/my-jobs"),
        (volume.resident_email, "/my-requests"),
    ):
        client = sign_in_as(client_factory, email)

        response, seconds = timed(client, base + path)

        assert response.status_code == 200, path
        assert seconds < SLOWEST_SECONDS, f"{path} took {seconds:.1f} s"
