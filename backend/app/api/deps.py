import secrets
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.mail import EmailSender
from app.core.storage import FileStore
from app.db.session import get_session
from app.models import UserSession
from app.services.sessions import get_valid_session

SESSION_COOKIE_NAME = "workledger_session"
CSRF_HEADER_NAME = "X-CSRF-Token"
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

DbSession = Annotated[Session, Depends(get_session)]


def get_email_sender(request: Request) -> EmailSender:
    return request.app.state.email_sender


EmailSenderDep = Annotated[EmailSender, Depends(get_email_sender)]


def get_file_store(request: Request) -> FileStore:
    return request.app.state.file_store


FileStoreDep = Annotated[FileStore, Depends(get_file_store)]


def _load_session(request: Request, db: Session) -> UserSession | None:
    settings = request.app.state.settings
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        return None

    record = get_valid_session(db, token, idle_timeout=settings.session_idle_timeout)
    db.commit()  # saves activity updates and the deletion of expired sessions
    return record


def _require_csrf_for_changes(request: Request, record: UserSession) -> None:
    if request.method in SAFE_METHODS:
        return
    supplied = request.headers.get(CSRF_HEADER_NAME, "")
    if not secrets.compare_digest(supplied.encode(), record.csrf_token.encode()):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Invalid CSRF token")


def get_authenticated_session(request: Request, db: DbSession) -> UserSession:
    """Require a signed-in user, and a valid CSRF token on every non-read request."""
    record = _load_session(request, db)
    if record is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    _require_csrf_for_changes(request, record)
    return record


def get_optional_session(request: Request, db: DbSession) -> UserSession | None:
    """For endpoints that work signed out or signed in. A session that is present is
    still held to the CSRF rule."""
    record = _load_session(request, db)
    if record is not None:
        _require_csrf_for_changes(request, record)
    return record


AuthenticatedSession = Annotated[UserSession, Depends(get_authenticated_session)]
OptionalSession = Annotated[UserSession | None, Depends(get_optional_session)]
