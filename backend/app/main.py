from fastapi import Depends, FastAPI

from app.api import (
    approvals,
    auth,
    directory,
    dispatch,
    health,
    invitations,
    jobs,
    members,
    notifications,
    organizations,
    password_reset,
    reports,
    requests,
    work_orders,
)
from app.api.deps import deliver_notifications
from app.core.config import Settings, get_settings
from app.core.http import HttpSafetyMiddleware, configure_logging
from app.core.mail import EmailSender, build_email_sender
from app.core.storage import FileStore, LocalFileStore


def create_app(
    settings: Settings | None = None,
    email_sender: EmailSender | None = None,
    file_store: FileStore | None = None,
) -> FastAPI:
    settings = settings or get_settings()

    production = settings.environment == "production"
    if production:
        configure_logging()
    app = FastAPI(
        title="WorkLedger API",
        version="0.1.0",
        dependencies=[Depends(deliver_notifications)],
        # The interactive reference lists every route; it is for development.
        docs_url=None if production else "/docs",
        redoc_url=None if production else "/redoc",
        openapi_url=None if production else "/openapi.json",
    )
    app.add_middleware(HttpSafetyMiddleware, settings=settings)
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
    app.include_router(approvals.router, prefix="/api")
    app.include_router(notifications.router, prefix="/api")
    app.include_router(reports.router, prefix="/api")
    app.include_router(members.router, prefix="/api")
    app.include_router(invitations.organization_router, prefix="/api")
    app.include_router(invitations.public_router, prefix="/api")
    return app


app = create_app()
