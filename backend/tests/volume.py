"""Builds a firm at the upper target size, with years of history, for performance checks.

About 300 units over 10 properties, three years of requests (roughly four per unit per year),
most of them turned into work orders that went through their whole life, with histories,
estimates, notifications and activity. Rows are added directly, in bulk, because going through
the services thousands of times would take minutes and test nothing new.
"""

import random
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.models import (
    ActivityEvent,
    Estimate,
    EventType,
    MaintenanceRequest,
    Membership,
    Notification,
    NotificationKind,
    Organization,
    Property,
    PropertyAssignment,
    PropertyOwnership,
    RequestStatus,
    RequestUpdate,
    Resident,
    Role,
    Tenancy,
    Unit,
    User,
    WorkOrder,
    WorkOrderAssignment,
    WorkOrderEntry,
    WorkOrderStatus,
)
from app.models.notifications import LinkKind
from app.models.requests import RequestCategory, UpdateKind, Urgency, Visibility
from app.models.work_orders import AssignmentResponse, EntryKind
from app.services.organizations import add_membership, create_organization
from app.services.users import create_user

PROPERTIES = 10
UNITS_PER_PROPERTY = 30
YEARS = 3
REQUESTS_PER_UNIT_PER_YEAR = 4


@dataclass
class Volume:
    organization_id: uuid.UUID
    admin_email: str
    manager_email: str
    owner_email: str
    contractor_email: str
    resident_email: str
    requests: int
    work_orders: int
    units: int


def _add(session: Session, rows: list[object]) -> None:
    session.add_all(rows)
    session.flush()
    rows.clear()


def build_volume(session: Session, *, password: str, seed: int = 7) -> Volume:
    rng = random.Random(seed)
    now = datetime.now(UTC)
    organization = create_organization(session, name="Volume Test Firm", actor=None)

    people: dict[str, tuple[User, Membership]] = {}
    for key, role in (
        ("admin", Role.ADMINISTRATOR),
        ("manager", Role.MANAGER),
        ("owner", Role.PROPERTY_OWNER),
        ("contractor", Role.CONTRACTOR),
        ("resident", Role.RESIDENT),
    ):
        user = create_user(
            session, email=f"{key}@volume.example", full_name=key.title(), password=password
        )
        membership = add_membership(
            session, organization=organization, user=user, roles=[role], actor=None
        )
        people[key] = (user, membership)
    admin = people["admin"][0]
    contractors = [people["contractor"][1]]
    for index in range(7):
        user = create_user(
            session,
            email=f"crew{index}@volume.example",
            full_name=f"Crew {index}",
            password=password,
        )
        contractors.append(
            add_membership(
                session, organization=organization, user=user, roles=[Role.CONTRACTOR], actor=None
            )
        )

    properties: list[Property] = []
    units: list[Unit] = []
    for number in range(PROPERTIES):
        property_ = Property(
            organization_id=organization.id,
            name=f"Property {number:02d}",
            currency="USD",
            approval_threshold_cents=50_000,
        )
        session.add(property_)
        session.flush()
        properties.append(property_)
        session.add(
            PropertyOwnership(
                organization_id=organization.id,
                property_id=property_.id,
                membership_id=people["owner"][1].id,
            )
        )
        if number < PROPERTIES // 2:
            session.add(
                PropertyAssignment(
                    organization_id=organization.id,
                    property_id=property_.id,
                    membership_id=people["manager"][1].id,
                )
            )
        for label in range(UNITS_PER_PROPERTY):
            units.append(
                Unit(
                    organization_id=organization.id,
                    property_id=property_.id,
                    label=f"{label + 1:03d}",
                )
            )
    _add(session, list(units))
    residents: dict[uuid.UUID, Resident] = {}
    pending: list[object] = []
    for unit in units:
        resident = Resident(
            organization_id=organization.id,
            full_name=f"Resident {unit.label} of {unit.property_id.hex[:4]}",
            email=f"{unit.id.hex[:10]}@volume.example",
            phone="555-0100",
        )
        residents[unit.id] = resident
        pending.append(resident)
    _add(session, pending)
    for unit in units:
        pending.append(
            Tenancy(
                organization_id=organization.id,
                unit_id=unit.id,
                resident_id=residents[unit.id].id,
                move_in_date=(now - timedelta(days=YEARS * 365 + 30)).date(),
            )
        )
    _add(session, pending)

    categories = list(RequestCategory)
    urgencies = list(Urgency)
    request_number = 0
    order_number = 0
    request_count = 0
    order_count = 0
    for unit in units:
        for _ in range(REQUESTS_PER_UNIT_PER_YEAR * YEARS):
            request_number += 1
            created = now - timedelta(days=rng.randint(1, YEARS * 365), hours=rng.randint(0, 23))
            age_days = (now - created).days
            category = rng.choice(categories)
            urgency = rng.choice(urgencies)
            converted = rng.random() < 0.7
            request = MaintenanceRequest(
                organization_id=organization.id,
                number=request_number,
                property_id=unit.property_id,
                unit_id=unit.id,
                resident_id=residents[unit.id].id,
                submitted_by_user_id=admin.id,
                category=category,
                urgency=urgency,
                status=RequestStatus.CLOSED if age_days > 30 else RequestStatus.SUBMITTED,
                title=f"{category} problem {request_number}",
                description="A description of the problem. " * 4,
                created_at=created,
            )
            pending.append(request)
            request_count += 1
            if not converted:
                continue

            order_number += 1
            order_count += 1
            old = age_days > 30
            status = (
                rng.choice([WorkOrderStatus.CLOSED, WorkOrderStatus.COMPLETED])
                if old
                else rng.choice(
                    [
                        WorkOrderStatus.OPEN,
                        WorkOrderStatus.ASSIGNED,
                        WorkOrderStatus.IN_PROGRESS,
                        WorkOrderStatus.ON_HOLD,
                        WorkOrderStatus.READY_FOR_REVIEW,
                    ]
                )
            )
            verified = created + timedelta(days=rng.randint(1, 20)) if old else None
            order = WorkOrder(
                id=uuid.uuid4(),
                organization_id=organization.id,
                number=order_number,
                property_id=unit.property_id,
                unit_id=unit.id,
                title=request.title,
                scope="Scope of the work. " * 5,
                category=category,
                priority=urgency,
                status=status,
                due_date=(created + timedelta(days=14)).date(),
                created_by_user_id=admin.id,
                resolution="Done." if verified else None,
                final_cost_cents=rng.randint(5_000, 90_000) if verified else None,
                currency="USD" if verified else None,
                verified_by_user_id=admin.id if verified else None,
                verified_at=verified,
                created_at=created,
            )
            pending.append(order)
            request.work_order_id = order.id
            if len(pending) >= 2_000:
                _link_and_add(session, pending, organization, contractors, admin, rng, now)
    _link_and_add(session, pending, organization, contractors, admin, rng, now)

    notifications: list[object] = []
    for index in range(4_000):
        notifications.append(
            Notification(
                organization_id=organization.id,
                recipient_user_id=admin.id,
                kind=NotificationKind.REQUEST_SUBMITTED,
                link_kind=LinkKind.STAFF_REQUEST,
                subject_id=uuid.uuid4(),
                title=f"New request REQ-{index:04d}: something is wrong",
                read_at=now if index % 5 else None,
                created_at=now - timedelta(minutes=index * 30),
            )
        )
    _add(session, notifications)
    session.commit()
    return Volume(
        organization_id=organization.id,
        admin_email="admin@volume.example",
        manager_email="manager@volume.example",
        owner_email="owner@volume.example",
        contractor_email="contractor@volume.example",
        resident_email="resident@volume.example",
        requests=request_count,
        work_orders=order_count,
        units=len(units),
    )


def _link_and_add(
    session: Session,
    pending: list[object],
    organization: Organization,
    contractors: list[Membership],
    admin: User,
    rng: random.Random,
    now: datetime,
) -> None:
    """Add requests and work orders, then the history that hangs off the work orders."""
    requests = [row for row in pending if isinstance(row, MaintenanceRequest)]
    orders = [row for row in pending if isinstance(row, WorkOrder)]
    pending.clear()
    session.add_all(orders)
    session.flush()
    session.add_all(requests)
    session.flush()

    extras: list[object] = []
    for request in requests:
        extras.append(
            RequestUpdate(
                organization_id=organization.id,
                request_id=request.id,
                author_user_id=admin.id,
                kind=UpdateKind.MESSAGE,
                visibility=Visibility.RESIDENT,
                body="We are looking into it.",
                created_at=request.created_at + timedelta(hours=3),
            )
        )
    for order in orders:
        for step, kind in enumerate((EntryKind.CREATED, EntryKind.STATUS_CHANGED, EntryKind.NOTE)):
            extras.append(
                WorkOrderEntry(
                    organization_id=organization.id,
                    work_order_id=order.id,
                    author_user_id=admin.id,
                    kind=kind,
                    visibility=Visibility.INTERNAL,
                    body=f"Entry {step}",
                    status_after=order.status if kind == EntryKind.STATUS_CHANGED else None,
                    contractor_visible=step == 2,
                    created_at=order.created_at + timedelta(hours=step + 1),
                )
            )
        if order.status != WorkOrderStatus.OPEN:
            extras.append(
                WorkOrderAssignment(
                    organization_id=organization.id,
                    work_order_id=order.id,
                    contractor_membership_id=rng.choice(contractors).id,
                    assigned_by_user_id=admin.id,
                    assigned_at=order.created_at + timedelta(hours=2),
                    response=AssignmentResponse.ACCEPTED,
                    responded_at=order.created_at + timedelta(hours=5),
                )
            )
        if rng.random() < 0.15:
            amount = rng.randint(20_000, 300_000)
            extras.append(
                Estimate(
                    organization_id=organization.id,
                    work_order_id=order.id,
                    version=1,
                    amount_cents=amount,
                    currency="USD",
                    description="Estimate for the work.",
                    submitted_by_user_id=admin.id,
                    approval_required=amount > 50_000,
                    threshold_cents=50_000,
                    status="approved" if amount > 50_000 else "not_required",
                    decided_by_user_id=admin.id if amount > 50_000 else None,
                    decided_at=order.created_at + timedelta(days=1) if amount > 50_000 else None,
                    created_at=order.created_at + timedelta(hours=8),
                )
            )
        extras.append(
            ActivityEvent(
                organization_id=organization.id,
                actor_user_id=admin.id,
                event_type=EventType.WORK_ORDER_CREATED,
                subject_type="work_order",
                subject_id=order.id,
                after={"title": order.title},
                occurred_at=order.created_at,
            )
        )
    session.add_all(extras)
    session.flush()
