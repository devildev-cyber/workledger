"""Synthetic demonstration data: a small, realistic property management firm.

Everything here is invented. Email addresses use the reserved example domain and phone
numbers use the 555-01xx range set aside for fiction, so no real person can be reached.
"""

from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import utc_now
from app.models import Organization, Property, Resident, Role, Unit, User
from app.services import assignments, directory, residents
from app.services.organizations import add_membership, create_organization
from app.services.users import create_user

ORGANIZATION_NAME = "Harbor Demo Properties"
DOMAIN = "demo.example"

ADMIN_EMAIL = f"admin@{DOMAIN}"
MANAGER_EMAIL = f"manager@{DOMAIN}"
RESIDENT_EMAIL = f"resident@{DOMAIN}"
CONTRACTOR_EMAIL = f"contractor@{DOMAIN}"
OWNER_EMAIL = f"owner@{DOMAIN}"

STAFF = [
    (ADMIN_EMAIL, "Alex Rivera", Role.ADMINISTRATOR),
    (MANAGER_EMAIL, "Morgan Ellis", Role.MANAGER),
    (RESIDENT_EMAIL, "Riley Chen", Role.RESIDENT),
    (CONTRACTOR_EMAIL, "Casey Brooks", Role.CONTRACTOR),
    (OWNER_EMAIL, "Olivia Grant", Role.PROPERTY_OWNER),
]

# (name, street, city, region, postal code, approval threshold in cents, buildings, units)
# Units are given per building; the empty building name means "no building".
PROPERTIES = [
    (
        "Maple Court",
        "120 Maple Street",
        "Portland",
        "OR",
        "97201",
        50000,
        {
            "Building A": ["1A", "1B", "2A", "2B", "3A", "3B"],
            "Building B": ["1A", "1B", "2A", "2B"],
        },
    ),
    (
        "Riverside Lofts",
        "45 Riverside Drive",
        "Portland",
        "OR",
        "97209",
        100000,
        {"": ["101", "102", "103", "201", "202", "203", "301", "302"]},
    ),
    (
        "Oak Terrace Houses",
        "8 Oak Terrace",
        "Beaverton",
        "OR",
        "97005",
        25000,
        {"": ["No. 1", "No. 2", "No. 3", "No. 4", "No. 5", "No. 6"]},
    ),
]

# (name, local part of the email, access instructions)
PEOPLE = [
    ("Riley Chen", "resident", "Buzz 2B. Dog in the unit, call before entering."),
    ("Jordan Patel", "jordan.patel", "Key with the front desk."),
    ("Taylor Nguyen", "taylor.nguyen", "Ring twice, works nights, avoid mornings."),
    ("Sam Okafor", "sam.okafor", None),
    ("Priya Raman", "priya.raman", "Gate code 4821."),
    ("Marcus Webb", "marcus.webb", "Prefers texts. Cat in the unit."),
    ("Elena Rossi", "elena.rossi", None),
    ("Dev Kapoor", "dev.kapoor", "Lockbox on the rail, code 1937."),
    ("Hannah Berg", "hannah.berg", None),
    ("Luis Moreno", "luis.moreno", "Call 24 hours before any visit."),
    ("Amara Diallo", "amara.diallo", None),
    ("Tomas Novak", "tomas.novak", "Side entrance only."),
    ("Grace Lindqvist", "grace.lindqvist", None),
    ("Omar Haddad", "omar.haddad", "Alarm panel by the door, code 5520."),
    ("Wendy Fischer", "wendy.fischer", None),
    ("Kenji Watanabe", "kenji.watanabe", "Home most afternoons."),
    ("Isabel Duarte", "isabel.duarte", None),
    ("Nate Sullivan", "nate.sullivan", "Knock loudly, hard of hearing."),
]

# Which person lives where: (person index, property, building, unit, days since moving in).
# Anything not listed stays vacant. History and a scheduled move-in are added separately.
PLACEMENTS = [
    (0, "Maple Court", "Building A", "2B", 420),
    (1, "Maple Court", "Building A", "1A", 800),
    (2, "Maple Court", "Building A", "1B", 210),
    (3, "Maple Court", "Building B", "1A", 95),
    (4, "Maple Court", "Building A", "2A", 640),
    (5, "Riverside Lofts", "", "101", 365),
    (6, "Riverside Lofts", "", "102", 30),
    (7, "Riverside Lofts", "", "201", 515),
    (8, "Riverside Lofts", "", "202", 150),
    (9, "Riverside Lofts", "", "301", 720),
    (10, "Oak Terrace Houses", "", "No. 1", 900),
    (11, "Oak Terrace Houses", "", "No. 2", 275),
    (12, "Oak Terrace Houses", "", "No. 3", 60),
    (13, "Oak Terrace Houses", "", "No. 5", 480),
]

UnitKey = tuple[str, str, str]  # property name, building name ("" for none), unit label


class AlreadySeededError(Exception):
    pass


@dataclass(frozen=True)
class SeedResult:
    organization: Organization
    properties: int
    units: int
    residents: int
    password: str


def _already_seeded(db: Session) -> bool:
    by_name = db.scalar(select(Organization.id).where(Organization.name == ORGANIZATION_NAME))
    by_email = db.scalar(select(User.id).where(User.email == ADMIN_EMAIL))
    return by_name is not None or by_email is not None


def seed_demo_organization(db: Session, *, password: str) -> SeedResult:
    """Create the demonstration firm. The caller commits.

    Refuses to run twice, so real data is never mixed with or overwritten by demo data.
    """
    if _already_seeded(db):
        raise AlreadySeededError(ORGANIZATION_NAME)

    organization = create_organization(db, name=ORGANIZATION_NAME, actor=None)
    users: dict[str, User] = {}
    for email, name, role in STAFF:
        users[email] = create_user(db, email=email, full_name=name, password=password)
        add_membership(db, organization=organization, user=users[email], roles=[role], actor=None)
    admin = users[ADMIN_EMAIL]

    created: dict[str, Property] = {}
    units: dict[UnitKey, Unit] = {}
    for name, street, city, region, postal_code, threshold, buildings in PROPERTIES:
        property_ = directory.create_property(
            db,
            organization_id=organization.id,
            actor=admin,
            values={
                "name": name,
                "street": street,
                "city": city,
                "region": region,
                "postal_code": postal_code,
                "currency": "USD",
                "approval_threshold_cents": threshold,
            },
        )
        created[name] = property_
        for building_name, labels in buildings.items():
            building = (
                directory.create_building(db, property_, actor=admin, name=building_name)
                if building_name
                else None
            )
            for label in labels:
                units[(name, building_name, label)] = directory.create_unit(
                    db,
                    property_,
                    actor=admin,
                    label=label,
                    building_id=building.id if building else None,
                )

    # The demo manager looks after two of the three properties, so property scoping is visible.
    manager_membership = next(m for m in assignments.manager_memberships(db, organization.id))
    for name in ("Maple Court", "Riverside Lofts"):
        assignments.set_property_managers(
            db, created[name], membership_ids=[manager_membership.id], actor=admin
        )

    people: list[Resident] = []
    for full_name, local_part, access in PEOPLE:
        index = len(people)
        people.append(
            residents.create_resident(
                db,
                organization_id=organization.id,
                actor=admin,
                full_name=full_name,
                email=f"{local_part}@{DOMAIN}",
                phone=f"555-01{index:02d}",
                access_instructions=access,
            )
        )

    today = utc_now().date()
    for person_index, property_name, building_name, label, days in PLACEMENTS:
        residents.start_tenancy(
            db,
            unit=units[(property_name, building_name, label)],
            resident=people[person_index],
            move_in_date=today - timedelta(days=days),
            actor=admin,
        )

    _add_history(db, admin, units, people, today)

    return SeedResult(
        organization=organization,
        properties=len(created),
        units=len(units),
        residents=len(people),
        password=password,
    )


def _add_history(
    db: Session,
    admin: User,
    units: dict[UnitKey, Unit],
    people: list[Resident],
    today: date,
) -> None:
    """One person who has moved out of a unit, and one who moves in soon."""
    earlier = units[("Maple Court", "Building A", "3A")]
    tenancy = residents.start_tenancy(
        db,
        unit=earlier,
        resident=people[14],
        move_in_date=today - timedelta(days=700),
        actor=admin,
    )
    residents.end_tenancy(db, tenancy, move_out_date=today - timedelta(days=45), actor=admin)

    upcoming = units[("Riverside Lofts", "", "203")]
    residents.start_tenancy(
        db,
        unit=upcoming,
        resident=people[15],
        move_in_date=today + timedelta(days=12),
        actor=admin,
    )
