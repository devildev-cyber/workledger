from fastapi import FastAPI

from app.api import (
    auth,
    directory,
    dispatch,
    health,
    invitations,
    jobs,
    members,
    organizations,
    password_reset,
    requests,
    work_orders,
)
from app.core.config import Settings, get_settings
from app.core.mail import EmailSender, build_email_sender
from app.core.storage import FileStore, LocalFileStore


def create_app(
    settings: Settings | None = None,
    email_sender: EmailSender | None = None,
    file_store: FileStore | None = None,
) -> FastAPI:
    settings = settings or get_settings()

    app = FastAPI(title="WorkLedger API", version="0.1.0")
    app.state.settings = settings
    app.state.email_sender = email_sender or build_email_sender(settings)
    app.state.file_store = file_store or LocalFileStore(settings.upload_dir)
    app.include_router(health.router, prefix="/api")
    app.include_router(auth.router, prefix="/api")
    app.include_router(password_reset.router, prefix="/api")
    app.include_router(organizations.router, prefix="/api")
    app.include_router(directory.router, prefix="/api")
    app.include_router(requests.router, prefix="/api")
    app.include_router(work_orders.router, prefix="/api")
    app.include_router(dispatch.router, prefix="/api")
    app.include_router(jobs.router, prefix="/api")
    app.include_router(members.router, prefix="/api")
    app.include_router(invitations.organization_router, prefix="/api")
    app.include_router(invitations.public_router, prefix="/api")
    return app


app = create_app()
