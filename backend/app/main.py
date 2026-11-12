from fastapi import FastAPI

from app.api import health
from app.core.config import Settings, get_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    app = FastAPI(title="WorkLedger API", version="0.1.0")
    app.state.settings = settings
    app.include_router(health.router, prefix="/api")
    return app


app = create_app()
