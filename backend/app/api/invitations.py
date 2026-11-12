import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status

from app.api.access import OrganizationContext, require_roles
from app.api.auth import session_out, set_session_cookie
from app.api.deps import DbSession, EmailSenderDep, OptionalSession
from app.core.clock import utc_now
from app.core.config import Settings
from app.core.mail import EmailMessage
from app.core.permissions import invitable_roles
from app.models import Invitation, Role
from app.schemas.auth import SessionOut
from app.schemas.invitations import (
    AcceptInvitationRequest,
    CreateInvitationRequest,
    InvitationOut,
    InvitationPreviewOut,
    InvitationTokenRequest,
)
from app.services.invitations import (
    InvitationEmailMismatchError,
    InvitationNotPendingError,
    accept_invitation,
    create_invitation,
    find_pending_invitation,
    get_invitation,
    list_invitations,
    revoke_invitation,
)
from app.services.organizations import AlreadyMemberError
from app.services.sessions import create_session
from app.services.users import (
    EmailAlreadyRegisteredError,
    InvalidPasswordError,
    create_user,
    get_user_by_email,
)

# Administrators and managers manage invitations; which roles they may invite is checked below.
InviterContext = Annotated[
    OrganizationContext, Depends(require_roles(Role.ADMINISTRATOR, Role.MANAGER))
]

organization_router = APIRouter(
    prefix="/organizations/{organization_id}/invitations", tags=["invitations"]
)
public_router = APIRouter(prefix="/invitations", tags=["invitations"])

INVALID_INVITATION = "This invitation is not valid. It may have expired or already been used."


def _to_out(invitation: Invitation) -> InvitationOut:
    return InvitationOut(
        id=invitation.id,
        email=invitation.email,
        roles=sorted(invitation.roles),
        status=invitation.status(utc_now()),
        invited_by_name=invitation.invited_by.full_name,
        created_at=invitation.created_at,
        expires_at=invitation.expires_at,
    )


def _invitation_email(settings: Settings, invitation: Invitation, token: str) -> EmailMessage:
    # The token sits after '#', which browsers never send to servers, keeping it out of logs.
    link = f"{settings.frontend_url.rstrip('/')}/invitations/accept#token={token}"
    roles = ", ".join(role.value.replace("_", " ") for role in sorted(invitation.roles))
    expires = invitation.expires_at.strftime("%B %d, %Y")
    return EmailMessage(
        to=invitation.email,
        subject=f"You are invited to join {invitation.organization.name} on WorkLedger",
        body=(
            f"{invitation.invited_by.full_name} invited you to join "
            f"{invitation.organization.name} as: {roles}.\n\n"
            f"Accept the invitation: {link}\n\n"
            f"This link works once and expires on {expires}. "
            "If you were not expecting it, you can ignore this email.\n"
        ),
    )


@organization_router.post("", status_code=status.HTTP_201_CREATED)
def create_organization_invitation(
    body: CreateInvitationRequest,
    request: Request,
    context: InviterContext,
    db: DbSession,
    sender: EmailSenderDep,
) -> InvitationOut:
    if not set(body.roles) <= invitable_roles(context.roles):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You cannot invite people with these roles")

    settings: Settings = request.app.state.settings
    try:
        invitation, token = create_invitation(
            db,
            organization=context.organization,
            inviter=context.user,
            email=body.email,
            roles=body.roles,
            ttl=settings.invitation_ttl,
        )
    except AlreadyMemberError:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "This person is already a member of the organization"
        ) from None
    db.commit()

    # Sent after the commit, so nobody is emailed about an invitation that was rolled back.
    sender.send(_invitation_email(settings, invitation, token))
    return _to_out(invitation)


@organization_router.get("")
def list_organization_invitations(
    context: InviterContext,
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> list[InvitationOut]:
    # Managers see only the invitations they sent; administrators see all of them.
    own_only = Role.ADMINISTRATOR not in context.roles
    invitations = list_invitations(
        db,
        organization_id=context.organization.id,
        invited_by_user_id=context.user.id if own_only else None,
        limit=limit,
    )
    return [_to_out(invitation) for invitation in invitations]


@organization_router.delete("/{invitation_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_organization_invitation(
    invitation_id: uuid.UUID, context: InviterContext, db: DbSession
) -> None:
    invitation = get_invitation(
        db, organization_id=context.organization.id, invitation_id=invitation_id
    )
    is_admin = Role.ADMINISTRATOR in context.roles
    if invitation is None or not (is_admin or invitation.invited_by_user_id == context.user.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invitation not found")

    try:
        revoke_invitation(db, invitation, actor=context.user)
    except InvitationNotPendingError:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Only pending invitations can be revoked"
        ) from None
    db.commit()


@public_router.post("/preview")
def preview_invitation(body: InvitationTokenRequest, db: DbSession) -> InvitationPreviewOut:
    invitation = find_pending_invitation(db, body.token)
    if invitation is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, INVALID_INVITATION)
    return InvitationPreviewOut(
        organization_name=invitation.organization.name,
        email=invitation.email,
        roles=sorted(invitation.roles),
        has_account=get_user_by_email(db, invitation.email) is not None,
    )


@public_router.post("/accept")
def accept_organization_invitation(
    body: AcceptInvitationRequest,
    request: Request,
    response: Response,
    db: DbSession,
    current: OptionalSession,
) -> SessionOut:
    settings: Settings = request.app.state.settings
    invitation = find_pending_invitation(db, body.token)
    if invitation is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, INVALID_INVITATION)

    existing_user = get_user_by_email(db, invitation.email)
    new_session_token: str | None = None

    if existing_user is not None:
        # Joining another organization is an explicit act by the account's owner.
        if current is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sign in to accept this invitation")
        if current.user_id != existing_user.id:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, "This invitation is for a different account"
            )
        user, record = existing_user, current
    else:
        if not body.full_name or not body.full_name.strip() or not body.password:
            raise HTTPException(
                422,
                "A name and password are required to create your account",
            )
        try:
            user = create_user(
                db, email=invitation.email, full_name=body.full_name, password=body.password
            )
        except InvalidPasswordError as error:
            raise HTTPException(422, str(error)) from None
        except EmailAlreadyRegisteredError:
            raise HTTPException(
                status.HTTP_409_CONFLICT, "An account with this email was just created; sign in"
            ) from None
        record, new_session_token = create_session(db, user, max_age=settings.session_max_age)

    try:
        accept_invitation(db, invitation, user=user)
    except AlreadyMemberError:
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, "You are already a member of this organization"
        ) from None
    except (InvitationNotPendingError, InvitationEmailMismatchError):
        db.rollback()
        raise HTTPException(status.HTTP_404_NOT_FOUND, INVALID_INVITATION) from None
    db.commit()

    if new_session_token is not None:
        set_session_cookie(response, settings, new_session_token)
    return session_out(db, record)
