import logging

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import text

from app.api.deps import DbSession

logger = logging.getLogger(__name__)
router = APIRouter(tags=["health"])


@router.get("/health")
def read_health() -> dict[str, str]:
    """The process is running. It does not touch the database, so it can be polled freely."""
    return {"status": "ok"}


@router.get("/health/ready")
def read_readiness(db: DbSession) -> dict[str, str]:
    """The process can reach its database. A deployment waits for this before sending traffic."""
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        # Why goes in the log; the answer to an anonymous caller stays vague.
        logger.exception("Database readiness check failed")
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Not ready") from None
    return {"status": "ready"}
