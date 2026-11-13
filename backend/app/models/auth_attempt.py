import uuid
from datetime import datetime

from sqlalchemy import Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.clock import utc_now
from app.db.base import Base
from app.db.types import UTCDateTime


class AuthAttempt(Base):
    """A failed sign-in, or a request for a password reset, counted to slow down guessing.

    Neither the email address nor the network address is stored: both are keyed hashes, so
    the table can be counted but not read back into personal data.
    """

    __tablename__ = "auth_attempts"
    __table_args__ = (
        Index("ix_auth_attempts_kind_account_key_created_at", "kind", "account_key", "created_at"),
        Index("ix_auth_attempts_kind_address_key_created_at", "kind", "address_key", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    # "sign_in" (failures only) or "reset" (every request).
    kind: Mapped[str] = mapped_column(String(16))
    account_key: Mapped[str] = mapped_column(String(64))
    address_key: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utc_now, index=True)
