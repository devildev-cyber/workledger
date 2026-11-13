from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, status

from app.api.deps import DbSession, EmailSenderDep
from app.core.config import Settings
from app.core.mail import EmailMessage
from app.core.network import client_address
from app.models import User
from app.schemas.auth import MessageOut, PasswordResetConfirm, PasswordResetRequest
from app.services import throttle
from app.services.password_reset import (
    InvalidResetTokenError,
    create_reset_token,
    reset_password,
)
from app.services.users import InvalidPasswordError, get_user_by_email

router = APIRouter(prefix="/auth/password-reset", tags=["auth"])

REQUEST_ACCEPTED = "If an account exists for that email address, a reset link has been sent."
INVALID_RESET_LINK = "This reset link is not valid. It may have expired or already been used."


def _reset_email(settings: Settings, user: User, token: str) -> EmailMessage:
    # The token sits after '#', which browsers never send to servers, keeping it out of logs.
    link = f"{settings.frontend_url.rstrip('/')}/password-reset#token={token}"
    minutes = settings.password_reset_valid_minutes
    return EmailMessage(
        to=user.email,
        subject="Reset your WorkLedger password",
        body=(
            f"Hello {user.full_name},\n\n"
            f"Someone asked to reset the password for this account. To choose a new one, open:\n"
            f"{link}\n\n"
            f"The link works once and expires in {minutes} minutes. "
            "If you did not ask for this, ignore this email; your password has not changed.\n"
        ),
    )


def _changed_email(user: User) -> EmailMessage:
    return EmailMessage(
        to=user.email,
        subject="Your WorkLedger password was changed",
        body=(
            f"Hello {user.full_name},\n\n"
            "The password for your WorkLedger account was just changed, and you were signed "
            "out everywhere. If this was not you, reset your password again right away and "
            "tell your administrator.\n"
        ),
    )


@router.post("/request", status_code=status.HTTP_202_ACCEPTED)
def request_password_reset(
    body: PasswordResetRequest,
    request: Request,
    background: BackgroundTasks,
    db: DbSession,
    sender: EmailSenderDep,
) -> MessageOut:
    """Always answers the same way, so it cannot be used to find out who has an account.

    The email is sent after the response, so the response time does not reveal it either.
    """
    settings: Settings = request.app.state.settings

    # Every request is counted, whether or not the account exists. Past the limit the answer
    # is unchanged, but no email is sent, so nobody can be flooded and nothing is revealed.
    caller = throttle.caller_for(
        settings, email=body.email, address=client_address(request, settings)
    )
    limited = throttle.reset_wait(db, settings, caller) > 0
    throttle.record(db, caller, kind=throttle.RESET)
    db.commit()
    if limited:
        return MessageOut(detail=REQUEST_ACCEPTED)

    user = get_user_by_email(db, body.email)
    if user is not None and user.is_active:
        token = create_reset_token(db, user, ttl=settings.password_reset_ttl)
        db.commit()
        background.add_task(sender.send, _reset_email(settings, user, token))
    return MessageOut(detail=REQUEST_ACCEPTED)


@router.post("/confirm", status_code=status.HTTP_204_NO_CONTENT)
def confirm_password_reset(
    body: PasswordResetConfirm,
    background: BackgroundTasks,
    db: DbSession,
    sender: EmailSenderDep,
) -> None:
    try:
        user = reset_password(db, token=body.token, new_password=body.password)
    except InvalidPasswordError as error:
        raise HTTPException(422, str(error)) from None
    except InvalidResetTokenError:
        db.rollback()
        raise HTTPException(status.HTTP_404_NOT_FOUND, INVALID_RESET_LINK) from None
    db.commit()

    background.add_task(sender.send, _changed_email(user))
