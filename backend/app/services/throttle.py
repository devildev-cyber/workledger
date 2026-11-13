"""Slowing down password guessing and reset-email flooding (decision 0025).

Failures are counted per account and per network address inside a sliding window. Counting
by account stops a patient guesser who rotates addresses; counting by address stops one who
tries many accounts. An account that does not exist is counted exactly like one that does, so
the response never reveals which emails have accounts.

The cost of counting by account is that someone can lock a known email out for one window by
failing on purpose. That is accepted: the window is short, the lock is not a flag on the
account, and the owner can still reset the password by email.
"""

import hashlib
import hmac
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.clock import utc_now
from app.core.config import Settings
from app.models import AuthAttempt

SIGN_IN = "sign_in"
RESET = "reset"
RESET_WINDOW = timedelta(hours=1)


@dataclass(frozen=True)
class Caller:
    """Who is asking, as keyed hashes. Built once per request."""

    account_key: str
    address_key: str | None


def _key(settings: Settings, label: str, value: str) -> str:
    secret = settings.secret_key.get_secret_value().encode()
    return hmac.new(secret, f"{label}:{value}".encode(), hashlib.sha256).hexdigest()


def caller_for(settings: Settings, *, email: str, address: str | None) -> Caller:
    return Caller(
        account_key=_key(settings, "account", email.strip().lower()),
        address_key=_key(settings, "address", address) if address else None,
    )


def _count_and_oldest(
    db: Session, *, kind: str, caller: Caller, since: datetime
) -> tuple[tuple[int, datetime | None], tuple[int, datetime | None]]:
    def measure(column, value: str | None) -> tuple[int, datetime | None]:  # type: ignore[no-untyped-def]
        if value is None:
            return 0, None
        count, oldest = db.execute(
            select(func.count(), func.min(AuthAttempt.created_at)).where(
                AuthAttempt.kind == kind, column == value, AuthAttempt.created_at > since
            )
        ).one()
        return count, oldest

    return (
        measure(AuthAttempt.account_key, caller.account_key),
        measure(AuthAttempt.address_key, caller.address_key),
    )


def seconds_until_allowed(
    db: Session,
    settings: Settings,
    caller: Caller,
    *,
    kind: str,
    account_limit: int,
    address_limit: int,
    window: timedelta,
    now: datetime | None = None,
) -> int:
    """0 when the caller may go ahead, otherwise how long until the oldest failure expires."""
    now = now or utc_now()
    (account_count, account_oldest), (address_count, address_oldest) = _count_and_oldest(
        db, kind=kind, caller=caller, since=now - window
    )
    waits = []
    if account_count >= account_limit and account_oldest is not None:
        waits.append(account_oldest + window - now)
    if address_count >= address_limit and address_oldest is not None:
        waits.append(address_oldest + window - now)
    if not waits:
        return 0
    return max(int(max(waits).total_seconds()) + 1, 1)


def sign_in_wait(db: Session, settings: Settings, caller: Caller) -> int:
    return seconds_until_allowed(
        db,
        settings,
        caller,
        kind=SIGN_IN,
        account_limit=settings.sign_in_max_failures,
        address_limit=settings.sign_in_max_failures_per_address,
        window=settings.sign_in_window,
    )


def reset_wait(db: Session, settings: Settings, caller: Caller) -> int:
    return seconds_until_allowed(
        db,
        settings,
        caller,
        kind=RESET,
        account_limit=settings.reset_requests_per_hour,
        address_limit=settings.reset_requests_per_address_per_hour,
        window=RESET_WINDOW,
    )


def record(db: Session, caller: Caller, *, kind: str) -> None:
    db.add(AuthAttempt(kind=kind, account_key=caller.account_key, address_key=caller.address_key))
    db.flush()


def forget_sign_in_failures(db: Session, caller: Caller) -> None:
    """A correct password ends the account's run of failures."""
    db.execute(
        delete(AuthAttempt).where(
            AuthAttempt.kind == SIGN_IN, AuthAttempt.account_key == caller.account_key
        )
    )


def purge(db: Session, *, older_than: datetime) -> int:
    """Delete counts that can no longer matter. Returns how many were removed."""
    result = db.execute(delete(AuthAttempt).where(AuthAttempt.created_at < older_than))
    return result.rowcount or 0
