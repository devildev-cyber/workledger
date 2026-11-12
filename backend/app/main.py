from fastapi import FastAPI

from app.api import auth, health, invitations, organizations, password_reset
from app.core.config import Settings, get_settings
from app.core.mail import EmailSender, build_email_sender


def create_app(
    settings: Settings | None = None, email_sender: EmailSender | None = None
) -> FastAPI:
    settings = settings or get_settings()

    app = FastAPI(title="WorkLedger API", version="0.1.0")
    app.state.settings = settings
    app.state.email_sender = email_sender or build_email_sender(settings)
    app.include_router(health.router, prefix="/api")
    app.include_router(auth.router, prefix="/api")
    app.include_router(password_reset.router, prefix="/api")
    app.include_router(organizations.router, prefix="/api")
    app.include_router(invitations.organization_router, prefix="/api")
    app.include_router(invitations.public_router, prefix="/api")
    return app


app = create_app()
