import secrets
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.models import UserSession
from app.services.sessions import get_valid_session

SESSION_COOKIE_NAME = "workledger_session"
CSRF_HEADER_NAME = "X-CSRF-Token"
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

DbSession = Annotated[Session, Depends(get_session)]


def get_authenticated_session(request: Request, db: DbSession) -> UserSession:
    """Require a signed-in user, and a valid CSRF token on every non-read request."""
    settings = request.app.state.settings
    token = request.cookies.get(SESSION_COOKIE_NAME)

    record = None
    if token:
        record = get_valid_session(db, token, idle_timeout=settings.session_idle_timeout)
        db.commit()  # saves activity updates and the deletion of expired sessions
    if record is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")

    if request.method not in SAFE_METHODS:
        supplied = request.headers.get(CSRF_HEADER_NAME, "")
        if not secrets.compare_digest(supplied.encode(), record.csrf_token.encode()):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Invalid CSRF token")
    return record


AuthenticatedSession = Annotated[UserSession, Depends(get_authenticated_session)]
