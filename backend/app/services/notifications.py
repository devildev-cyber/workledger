"""Notifications for the people an event needs (decision 0023).

Each event function names its audience explicitly and writes text for that audience. Three
rules hold for all of them:

- The person who did the thing is never told about it.
- A recipient must still hold the role the notification is for, in that organization. Removing
  a role or a membership ends the notifications with it.
- The text holds only a reference and a title the recipient could already read. No amounts,
  notes, reasons, or names of other people, so email copies cannot leak internal records.

Services flush but never commit. Email copies are sent after the commit by `deliver`, so
nobody is emailed about a change that was rolled back.
"""

import logging
import uuid
from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.clock import utc_now
from app.core.mail import EmailMessage, EmailSender
from app.models import (
    LinkKind,
    Membership,
    MembershipRole,
    Notification,
    NotificationKind,
    PropertyAssignment,
    PropertyOwnership,
    Resident,
    Role,
    User,
    WorkOrderAssignment,
    WorkOrderStatus,
)

logger = logging.getLogger(__name__)

PENDING_KEY = "pending_notification_ids"
LIST_LIMIT = 50

S = WorkOrderStatus

# The moves of someone else's job that its contractor is told about. Assigning, removing and
# verifying have their own notifications.
CONTRACTOR_STATUS_NOTICES = frozenset(
    {S.ON_HOLD, S.CANCELLED, S.IN_PROGRESS, S.CLOSED, S.AWAITING_APPROVAL}
)
# The moves a contractor makes that the property team should act on or know about.
TEAM_STATUS_NOTICES = frozenset({S.ON_HOLD, S.READY_FOR_REVIEW})

STATUS_WORDS: dict[WorkOrderStatus, str] = {
    S.OPEN: "open",
    S.ASSIGNED: "assigned",
    S.IN_PROGRESS: "in progress",
    S.ON_HOLD: "on hold",
    S.AWAITING_APPROVAL: "waiting for the owner's approval",
    S.READY_FOR_REVIEW: "ready for review",
    S.COMPLETED: "completed",
    S.CLOSED: "closed",
    S.CANCELLED: "cancelled",
}


# --- Who is told ------------------------------------------------------------------------


def _holding(
    db: Session, organization_id: uuid.UUID, user_ids: Iterable[uuid.UUID], role: Role
) -> list[uuid.UUID]:
    """Of these people, the ones who are members here with this role, in a stable order."""
    wanted = set(user_ids)
    if not wanted:
        return []
    found = db.scalars(
        select(Membership.user_id)
        .join(MembershipRole, MembershipRole.membership_id == Membership.id)
        .where(
            Membership.organization_id == organization_id,
            Membership.user_id.in_(wanted),
            MembershipRole.role == role,
        )
    )
    return sorted(set(found))


def team_user_ids(
    db: Session, *, organization_id: uuid.UUID, property_id: uuid.UUID
) -> list[uuid.UUID]:
    """The managers of a property. A property nobody manages falls back to the administrators,
    so nothing sits unseen."""
    managers = db.scalars(
        select(Membership.user_id)
        .join(PropertyAssignment, PropertyAssignment.membership_id == Membership.id)
        .join(MembershipRole, MembershipRole.membership_id == Membership.id)
        .where(
            PropertyAssignment.property_id == property_id,
            Membership.organization_id == organization_id,
            MembershipRole.role == Role.MANAGER,
        )
    )
    found = sorted(set(managers))
    if found:
        return found
    administrators = db.scalars(
        select(Membership.user_id)
        .join(MembershipRole, MembershipRole.membership_id == Membership.id)
        .where(
            Membership.organization_id == organization_id,
            MembershipRole.role == Role.ADMINISTRATOR,
        )
    )
    return sorted(set(administrators))


def owner_user_ids(
    db: Session, *, organization_id: uuid.UUID, property_id: uuid.UUID
) -> list[uuid.UUID]:
    owners = db.scalars(
        select(Membership.user_id)
        .join(PropertyOwnership, PropertyOwnership.membership_id == Membership.id)
        .where(
            PropertyOwnership.property_id == property_id,
            Membership.organization_id == organization_id,
        )
    )
    return _holding(db, organization_id, owners, Role.PROPERTY_OWNER)


def assignee_user_id(db: Session, work_order_id: uuid.UUID) -> uuid.UUID | None:
    """The contractor now responsible for a work order, if there is one."""
    return db.scalar(
        select(Membership.user_id)
        .join(
            WorkOrderAssignment,
            WorkOrderAssignment.contractor_membership_id == Membership.id,
        )
        .where(
            WorkOrderAssignment.work_order_id == work_order_id,
            WorkOrderAssignment.ended_at.is_(None),
        )
    )


def _user_of_membership(db: Session, membership_id: uuid.UUID) -> uuid.UUID | None:
    return db.scalar(select(Membership.user_id).where(Membership.id == membership_id))


def resident_user_id(db: Session, *, resident_id: uuid.UUID) -> uuid.UUID | None:
    return db.scalar(select(Resident.user_id).where(Resident.id == resident_id))


# --- Writing ----------------------------------------------------------------------------


def notify(
    db: Session,
    *,
    organization_id: uuid.UUID,
    recipients: Iterable[uuid.UUID | None],
    role: Role | tuple[Role, ...],
    actor: User | None,
    kind: NotificationKind,
    link_kind: LinkKind,
    subject_id: uuid.UUID,
    title: str,
) -> list[Notification]:
    """Tell each recipient who currently holds `role` here, except whoever acted."""
    roles = role if isinstance(role, tuple) else (role,)
    wanted = {user_id for user_id in recipients if user_id is not None}
    if actor is not None:
        wanted.discard(actor.id)
    allowed: set[uuid.UUID] = set()
    for item in roles:
        allowed.update(_holding(db, organization_id, wanted, item))

    created: list[Notification] = []
    for user_id in sorted(allowed):
        notification = Notification(
            id=uuid.uuid4(),
            organization_id=organization_id,
            recipient_user_id=user_id,
            kind=kind,
            link_kind=link_kind,
            subject_id=subject_id,
            title=title[:300],
        )
        db.add(notification)
        created.append(notification)
    if created:
        db.flush()
        pending: list[uuid.UUID] = db.info.setdefault(PENDING_KEY, [])
        pending.extend(item.id for item in created)
    return created


# --- Events: requests -------------------------------------------------------------------


def request_submitted(
    db: Session,
    *,
    organization_id: uuid.UUID,
    property_id: uuid.UUID,
    request_id: uuid.UUID,
    reference: str,
    title: str,
    resident_id: uuid.UUID,
    on_behalf: bool,
    actor: User,
) -> None:
    """The property team needs to triage it. A resident whose request was logged for them by
    staff is told it exists."""
    notify(
        db,
        organization_id=organization_id,
        recipients=team_user_ids(db, organization_id=organization_id, property_id=property_id),
        role=(Role.MANAGER, Role.ADMINISTRATOR),
        actor=actor,
        kind=NotificationKind.REQUEST_SUBMITTED,
        link_kind=LinkKind.STAFF_REQUEST,
        subject_id=request_id,
        title=f"New request {reference}: {title}",
    )
    if on_behalf:
        notify(
            db,
            organization_id=organization_id,
            recipients=[resident_user_id(db, resident_id=resident_id)],
            role=Role.RESIDENT,
            actor=actor,
            kind=NotificationKind.REQUEST_UPDATED,
            link_kind=LinkKind.MY_REQUEST,
            subject_id=request_id,
            title=f"A request was logged for you: {reference}, {title}",
        )


def request_message_from_resident(
    db: Session,
    *,
    organization_id: uuid.UUID,
    property_id: uuid.UUID,
    request_id: uuid.UUID,
    reference: str,
    actor: User,
) -> None:
    notify(
        db,
        organization_id=organization_id,
        recipients=team_user_ids(db, organization_id=organization_id, property_id=property_id),
        role=(Role.MANAGER, Role.ADMINISTRATOR),
        actor=actor,
        kind=NotificationKind.REQUEST_MESSAGE,
        link_kind=LinkKind.STAFF_REQUEST,
        subject_id=request_id,
        title=f"The resident replied on {reference}",
    )


def request_changed_for_resident(
    db: Session,
    *,
    organization_id: uuid.UUID,
    request_id: uuid.UUID,
    reference: str,
    resident_id: uuid.UUID,
    actor: User,
    status_label: str | None,
) -> None:
    """The resident is told when their request moves, or when staff write to them. The words
    of a message stay on the request; the notification only says there is one."""
    title = (
        f"Your request {reference} is now {status_label}"
        if status_label
        else f"New message on your request {reference}"
    )
    notify(
        db,
        organization_id=organization_id,
        recipients=[resident_user_id(db, resident_id=resident_id)],
        role=Role.RESIDENT,
        actor=actor,
        kind=NotificationKind.REQUEST_UPDATED,
        link_kind=LinkKind.MY_REQUEST,
        subject_id=request_id,
        title=title,
    )


# --- Events: work orders ----------------------------------------------------------------


def work_order_assigned(
    db: Session,
    *,
    organization_id: uuid.UUID,
    work_order_id: uuid.UUID,
    reference: str,
    title: str,
    contractor_membership_id: uuid.UUID,
    actor: User,
) -> None:
    notify(
        db,
        organization_id=organization_id,
        recipients=[_user_of_membership(db, contractor_membership_id)],
        role=Role.CONTRACTOR,
        actor=actor,
        kind=NotificationKind.WORK_ORDER_ASSIGNED,
        link_kind=LinkKind.JOB,
        subject_id=work_order_id,
        title=f"{reference} was assigned to you: {title}",
    )


def work_order_unassigned(
    db: Session,
    *,
    organization_id: uuid.UUID,
    work_order_id: uuid.UUID,
    reference: str,
    contractor_membership_id: uuid.UUID,
    actor: User,
) -> None:
    # A contractor who no longer has the job cannot open it, so this opens their list.
    notify(
        db,
        organization_id=organization_id,
        recipients=[_user_of_membership(db, contractor_membership_id)],
        role=Role.CONTRACTOR,
        actor=actor,
        kind=NotificationKind.WORK_ORDER_UNASSIGNED,
        link_kind=LinkKind.MY_JOBS,
        subject_id=work_order_id,
        title=f"You are no longer assigned to {reference}",
    )


def assignment_responded(
    db: Session,
    *,
    organization_id: uuid.UUID,
    property_id: uuid.UUID,
    work_order_id: uuid.UUID,
    reference: str,
    accepted: bool,
    actor: User,
) -> None:
    notify(
        db,
        organization_id=organization_id,
        recipients=team_user_ids(db, organization_id=organization_id, property_id=property_id),
        role=(Role.MANAGER, Role.ADMINISTRATOR),
        actor=actor,
        kind=NotificationKind.ASSIGNMENT_ACCEPTED
        if accepted
        else NotificationKind.ASSIGNMENT_DECLINED,
        link_kind=LinkKind.STAFF_WORK_ORDER,
        subject_id=work_order_id,
        title=(
            f"The contractor accepted {reference}"
            if accepted
            else f"The contractor declined {reference}. It needs a new contractor"
        ),
    )


def work_order_status_changed(
    db: Session,
    *,
    organization_id: uuid.UUID,
    property_id: uuid.UUID,
    work_order_id: uuid.UUID,
    reference: str,
    title: str,
    new_status: WorkOrderStatus,
    contractor_user_id: uuid.UUID | None,
    actor: User,
) -> None:
    """A manager or owner moving the job tells its contractor. The contractor moving it
    (starting, pausing, finishing) tells the property team."""
    if actor.id == contractor_user_id:
        if new_status not in TEAM_STATUS_NOTICES:
            return
        ready = new_status == S.READY_FOR_REVIEW
        notify(
            db,
            organization_id=organization_id,
            recipients=team_user_ids(db, organization_id=organization_id, property_id=property_id),
            role=(Role.MANAGER, Role.ADMINISTRATOR),
            actor=actor,
            kind=(
                NotificationKind.WORK_ORDER_READY_FOR_REVIEW
                if ready
                else NotificationKind.WORK_ORDER_STATUS_CHANGED
            ),
            link_kind=LinkKind.STAFF_WORK_ORDER,
            subject_id=work_order_id,
            title=(
                f"{reference} is ready for your review"
                if ready
                else f"{reference} was put on hold by the contractor"
            ),
        )
        return
    if new_status in CONTRACTOR_STATUS_NOTICES:
        notify(
            db,
            organization_id=organization_id,
            recipients=[contractor_user_id],
            role=Role.CONTRACTOR,
            actor=actor,
            kind=NotificationKind.WORK_ORDER_STATUS_CHANGED,
            # A cancelled job leaves the contractor's list, so there is nothing to open.
            link_kind=LinkKind.MY_JOBS if new_status == S.CANCELLED else LinkKind.JOB,
            subject_id=work_order_id,
            title=f"{reference} is now {STATUS_WORDS[new_status]}: {title}",
        )


def work_order_verified(
    db: Session,
    *,
    organization_id: uuid.UUID,
    work_order_id: uuid.UUID,
    reference: str,
    contractor_user_id: uuid.UUID | None,
    actor: User,
) -> None:
    notify(
        db,
        organization_id=organization_id,
        recipients=[contractor_user_id],
        role=Role.CONTRACTOR,
        actor=actor,
        kind=NotificationKind.WORK_ORDER_VERIFIED,
        link_kind=LinkKind.JOB,
        subject_id=work_order_id,
        title=f"Your work on {reference} was verified",
    )


def work_order_sent_back(
    db: Session,
    *,
    organization_id: uuid.UUID,
    work_order_id: uuid.UUID,
    reference: str,
    contractor_user_id: uuid.UUID | None,
    actor: User,
) -> None:
    notify(
        db,
        organization_id=organization_id,
        recipients=[contractor_user_id],
        role=Role.CONTRACTOR,
        actor=actor,
        kind=NotificationKind.WORK_ORDER_SENT_BACK,
        link_kind=LinkKind.JOB,
        subject_id=work_order_id,
        title=f"{reference} was sent back to you. See what still needs doing",
    )


# --- Events: estimates ------------------------------------------------------------------


def estimate_needs_decision(
    db: Session,
    *,
    organization_id: uuid.UUID,
    property_id: uuid.UUID,
    estimate_id: uuid.UUID,
    reference: str,
    title: str,
    actor: User,
) -> None:
    notify(
        db,
        organization_id=organization_id,
        recipients=owner_user_ids(db, organization_id=organization_id, property_id=property_id),
        role=Role.PROPERTY_OWNER,
        actor=actor,
        kind=NotificationKind.ESTIMATE_NEEDS_DECISION,
        link_kind=LinkKind.APPROVAL,
        subject_id=estimate_id,
        title=f"{reference} needs your decision: {title}",
    )


def estimate_decided(
    db: Session,
    *,
    organization_id: uuid.UUID,
    property_id: uuid.UUID,
    work_order_id: uuid.UUID,
    reference: str,
    approved: bool,
    submitter_user_id: uuid.UUID,
    actor: User,
) -> None:
    """Whoever recorded the estimate, and the property team, learn the outcome. The owner's
    reason is on the work order for staff; it is not repeated here."""
    recipients = {
        submitter_user_id,
        *team_user_ids(db, organization_id=organization_id, property_id=property_id),
    }
    notify(
        db,
        organization_id=organization_id,
        recipients=recipients,
        role=(Role.MANAGER, Role.ADMINISTRATOR),
        actor=actor,
        kind=NotificationKind.ESTIMATE_DECIDED,
        link_kind=LinkKind.STAFF_WORK_ORDER,
        subject_id=work_order_id,
        title=(
            f"The owner approved the estimate for {reference}"
            if approved
            else f"The owner rejected the estimate for {reference}. The work is on hold"
        ),
    )


def approved_work_completed(
    db: Session,
    *,
    organization_id: uuid.UUID,
    property_id: uuid.UUID,
    estimate_id: uuid.UUID,
    reference: str,
    title: str,
    actor: User,
) -> None:
    """Owners who approved spending are told when that work is done."""
    notify(
        db,
        organization_id=organization_id,
        recipients=owner_user_ids(db, organization_id=organization_id, property_id=property_id),
        role=Role.PROPERTY_OWNER,
        actor=actor,
        kind=NotificationKind.APPROVED_WORK_COMPLETED,
        link_kind=LinkKind.APPROVAL,
        subject_id=estimate_id,
        title=f"Approved work is complete: {reference}, {title}",
    )


# --- Reading and managing your own ------------------------------------------------------


@dataclass(frozen=True)
class NotificationList:
    items: list[Notification]
    unread_count: int


def list_for(
    db: Session,
    *,
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
    unread_only: bool = False,
) -> NotificationList:
    """The person's own notifications in one organization, newest first."""
    base = (Notification.organization_id == organization_id) & (
        Notification.recipient_user_id == user_id
    )
    statement = select(Notification).where(base)
    if unread_only:
        statement = statement.where(Notification.read_at.is_(None))
    statement = statement.order_by(Notification.created_at.desc(), Notification.id).limit(
        LIST_LIMIT
    )
    unread = db.scalar(
        select(func.count()).select_from(Notification).where(base, Notification.read_at.is_(None))
    )
    return NotificationList(items=list(db.scalars(statement)), unread_count=unread or 0)


def mark_read(
    db: Session, *, organization_id: uuid.UUID, user_id: uuid.UUID, notification_id: uuid.UUID
) -> bool:
    """Mark one of the person's own notifications read. Anyone else's looks like it is missing."""
    item = db.scalar(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.organization_id == organization_id,
            Notification.recipient_user_id == user_id,
        )
    )
    if item is None:
        return False
    if item.read_at is None:
        item.read_at = utc_now()
        db.flush()
    return True


def mark_all_read(db: Session, *, organization_id: uuid.UUID, user_id: uuid.UUID) -> None:
    db.execute(
        update(Notification)
        .where(
            Notification.organization_id == organization_id,
            Notification.recipient_user_id == user_id,
            Notification.read_at.is_(None),
        )
        .values(read_at=utc_now())
    )
    db.flush()


def path_for(notification: Notification) -> str:
    """Where in the app the notification leads, for the person it was written for."""
    base = f"/organizations/{notification.organization_id}"
    match LinkKind(notification.link_kind):
        case LinkKind.STAFF_REQUEST:
            return f"{base}/requests/{notification.subject_id}"
        case LinkKind.STAFF_WORK_ORDER:
            return f"{base}/work-orders/{notification.subject_id}"
        case LinkKind.MY_REQUEST:
            return f"{base}/my-requests/{notification.subject_id}"
        case LinkKind.JOB:
            return f"{base}/my-jobs/{notification.subject_id}"
        case LinkKind.MY_JOBS:
            return f"{base}/my-jobs"
        case LinkKind.APPROVAL:
            return f"{base}/my-approvals/{notification.subject_id}"


def set_email_enabled(db: Session, membership: Membership, *, enabled: bool) -> None:
    membership.email_notifications = enabled
    db.flush()


# --- Email copies -----------------------------------------------------------------------


def deliver(db: Session, sender: EmailSender, *, frontend_url: str) -> None:
    """Send email copies of this session's new notifications. Call after the commit.

    Only people who have not turned email off are written to. A failure to send is logged
    and does not affect the request that caused it: the notification is still in the app.
    """
    ids: list[uuid.UUID] = db.info.pop(PENDING_KEY, [])
    if not ids:
        return
    rows = db.execute(
        select(Notification, User.email, Membership.email_notifications)
        .join(User, User.id == Notification.recipient_user_id)
        .join(
            Membership,
            (Membership.user_id == Notification.recipient_user_id)
            & (Membership.organization_id == Notification.organization_id),
        )
        .where(Notification.id.in_(ids), Notification.emailed_at.is_(None))
    ).all()
    base = frontend_url.rstrip("/")
    changed = False
    for notification, email, wants_email in rows:
        if not wants_email:
            continue
        link = f"{base}{path_for(notification)}"
        body = (
            f"{notification.title}\n\nOpen it in WorkLedger: {link}\n\n"
            "You can turn these emails off under Notifications in WorkLedger."
        )
        try:
            sender.send(
                EmailMessage(to=email, subject=" ".join(notification.title.split()), body=body)
            )
        except Exception:
            logger.exception("Could not send the email copy of notification %s", notification.id)
            continue
        notification.emailed_at = utc_now()
        changed = True
    if changed:
        db.commit()
