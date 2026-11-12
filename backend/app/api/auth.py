from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.api.deps import SESSION_COOKIE_NAME, AuthenticatedSession, DbSession
from app.core.config import Settings
from app.models import UserSession
from app.schemas.auth import CurrentUserOut, MembershipOut, SessionOut, SignInRequest
from app.services.auth import authenticate
from app.services.organizations import list_memberships_for_user
from app.services.sessions import create_session, end_session

router = APIRouter(prefix="/auth", tags=["auth"])


def _cookie_options(settings: Settings) -> dict[str, Any]:
    return {
        "httponly": True,
        "samesite": "lax",
        "secure": settings.environment == "production",
        "path": "/",
    }


def set_session_cookie(response: Response, settings: Settings, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE_NAME,
        token,
        max_age=int(settings.session_max_age.total_seconds()),
        **_cookie_options(settings),
    )


def session_out(db: Session, record: UserSession) -> SessionOut:
    user = record.user
    memberships = list_memberships_for_user(db, user.id)
    return SessionOut(
        user=CurrentUserOut(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            memberships=[
                MembershipOut(
                    organization_id=membership.organization_id,
                    organization_name=membership.organization.name,
                    roles=sorted(membership.roles),
                )
                for membership in memberships
            ],
        ),
        csrf_token=record.csrf_token,
    )


@router.post("/sign-in")
def sign_in(body: SignInRequest, request: Request, response: Response, db: DbSession) -> SessionOut:
    settings: Settings = request.app.state.settings

    user = authenticate(db, email=body.email, password=body.password)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")

    record, token = create_session(db, user, max_age=settings.session_max_age)
    db.commit()

    set_session_cookie(response, settings, token)
    return session_out(db, record)


@router.get("/me")
def read_current_user(record: AuthenticatedSession, db: DbSession) -> SessionOut:
    return session_out(db, record)


@router.post("/sign-out", status_code=status.HTTP_204_NO_CONTENT)
def sign_out(
    request: Request, response: Response, record: AuthenticatedSession, db: DbSession
) -> None:
    end_session(db, record)
    db.commit()

    response.delete_cookie(SESSION_COOKIE_NAME, **_cookie_options(request.app.state.settings))
