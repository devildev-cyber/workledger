import uuid
from collections.abc import Iterable
from datetime import datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session, joinedload

from app.core.clock import utc_now
from app.core.security import hash_token, new_token
from app.models import EventType, Invitation, Membership, Organization, Role, User
from app.services.activity import record_event
from app.services.organizations import AlreadyMemberError, NoRolesError, add_membership
from app.services.residents import link_residents_for_member
from app.services.users import get_user_by_email, normalize_email


class InvitationNotPendingError(Exception):
    pass


class InvitationEmailMismatchError(Exception):
    pass


def create_invitation(
    db: Session,
    *,
    organization: Organization,
    inviter: User,
    email: str,
    roles: Iterable[Role],
    ttl: timedelta,
    now: datetime | None = None,
) -> tuple[Invitation, str]:
    """Invite an email address. Returns the invitation and the raw token, which is never stored.

    Any earlier pending invitation to the same address in this organization is revoked, so
    only the newest link works. The caller must commit, and should send the email afterwards.
    """
    now = now or utc_now()
    email = normalize_email(email)
    role_set = frozenset(roles)
    if not role_set:
        raise NoRolesError("An invitation needs at least one role")

    existing_user = get_user_by_email(db, email)
    if existing_user is not None:
        already_member = db.scalar(
            select(Membership.id).where(
                Membership.organization_id == organization.id,
                Membership.user_id == existing_user.id,
            )
        )
        if already_member is not None:
            raise AlreadyMemberError(f"{email} is already a member of {organization.name}")

    for earlier in _pending_for_email(db, organization.id, email, now):
        _revoke(db, earlier, actor=inviter, now=now, reason="superseded")

    token = new_token()
    invitation = Invitation(
        organization=organization,
        invited_by=inviter,
        email=email,
        role_values=sorted(role.value for role in role_set),
        token_hash=hash_token(token),
        created_at=now,
        expires_at=now + ttl,
    )
    db.add(invitation)
    db.flush()

    record_event(
        db,
        event_type=EventType.INVITATION_CREATED,
        organization_id=organization.id,
        actor=inviter,
        subject_type="invitation",
        subject_id=invitation.id,
        after={"email": email, "roles": invitation.role_values},
    )
    return invitation, token


def list_invitations(
    db: Session,
    *,
    organization_id: uuid.UUID,
    invited_by_user_id: uuid.UUID | None = None,
    limit: int = 100,
) -> list[Invitation]:
    statement = (
        select(Invitation)
        .options(joinedload(Invitation.invited_by))
        .where(Invitation.organization_id == organization_id)
        .order_by(Invitation.created_at.desc(), Invitation.id)
        .limit(limit)
    )
    if invited_by_user_id is not None:
        statement = statement.where(Invitation.invited_by_user_id == invited_by_user_id)
    return list(db.scalars(statement))


def get_invitation(
    db: Session, *, organization_id: uuid.UUID, invitation_id: uuid.UUID
) -> Invitation | None:
    return db.scalar(
        select(Invitation)
        .options(joinedload(Invitation.invited_by))
        .where(Invitation.organization_id == organization_id, Invitation.id == invitation_id)
    )


def revoke_invitation(
    db: Session, invitation: Invitation, *, actor: User, now: datetime | None = None
) -> None:
    now = now or utc_now()
    if invitation.status(now) != "pending":
        raise InvitationNotPendingError(invitation.status(now))
    _revoke(db, invitation, actor=actor, now=now, reason="revoked")


def find_pending_invitation(
    db: Session, token: str, *, now: datetime | None = None
) -> Invitation | None:
    """Look up a usable invitation by token. Unknown, used, revoked, and expired give None."""
    now = now or utc_now()
    invitation = db.scalar(
        select(Invitation)
        .options(joinedload(Invitation.organization))
        .where(Invitation.token_hash == hash_token(token))
    )
    if invitation is None or invitation.status(now) != "pending":
        return None
    return invitation


def accept_invitation(
    db: Session, invitation: Invitation, *, user: User, now: datetime | None = None
) -> Membership:
    """Use up an invitation and add the user to its organization.

    The invitation is claimed with a single conditional UPDATE, so two simultaneous
    attempts cannot both succeed. If adding the membership then fails, the caller must
    roll back, which also releases the claim. The caller must commit.
    """
    now = now or utc_now()
    if user.email != invitation.email:
        raise InvitationEmailMismatchError(user.email)

    claimed = db.execute(
        update(Invitation)
        .where(
            Invitation.id == invitation.id,
            Invitation.accepted_at.is_(None),
            Invitation.revoked_at.is_(None),
            Invitation.expires_at > now,
        )
        .values(accepted_at=now)
    )
    if claimed.rowcount != 1:
        raise InvitationNotPendingError(invitation.status(now))
    db.refresh(invitation)

    membership = add_membership(
        db, organization=invitation.organization, user=user, roles=invitation.roles, actor=user
    )
    if Role.RESIDENT in invitation.roles:
        # Directory records created for this person before they joined now belong to them.
        link_residents_for_member(db, organization_id=invitation.organization_id, user=user)
    record_event(
        db,
        event_type=EventType.INVITATION_ACCEPTED,
        organization_id=invitation.organization_id,
        actor=user,
        subject_type="invitation",
        subject_id=invitation.id,
        after={"membership_id": str(membership.id)},
    )
    return membership


def _pending_for_email(
    db: Session, organization_id: uuid.UUID, email: str, now: datetime
) -> list[Invitation]:
    candidates = db.scalars(
        select(Invitation).where(
            Invitation.organization_id == organization_id,
            Invitation.email == email,
            Invitation.accepted_at.is_(None),
            Invitation.revoked_at.is_(None),
            Invitation.expires_at > now,
        )
    )
    return list(candidates)


def _revoke(
    db: Session, invitation: Invitation, *, actor: User, now: datetime, reason: str
) -> None:
    invitation.revoked_at = now
    record_event(
        db,
        event_type=EventType.INVITATION_REVOKED,
        organization_id=invitation.organization_id,
        actor=actor,
        subject_type="invitation",
        subject_id=invitation.id,
        after={"email": invitation.email, "reason": reason},
    )
