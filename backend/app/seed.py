"""Create demonstration data for a new local installation.

Usage, from backend/:

    python -m app.seed

Creates a made-up firm with properties, units, residents, and one account for each role.
Everything is invented, and nothing real is contacted. The command refuses to run if the
demo organization already exists. The password for every demo account is printed once.
"""

import secrets
import sys
from collections.abc import Callable, Sequence

from sqlalchemy.orm import Session

from app.db.session import get_engine
from app.services.seed import (
    ADMIN_EMAIL,
    CONTRACTOR_EMAIL,
    MANAGER_EMAIL,
    ORGANIZATION_NAME,
    OWNER_EMAIL,
    RESIDENT_EMAIL,
    AlreadySeededError,
    seed_demo_organization,
)


def _default_session() -> Session:
    return Session(get_engine())


def main(
    argv: Sequence[str] | None = None,
    *,
    session_factory: Callable[[], Session] = _default_session,
    password: str | None = None,
) -> int:
    del argv  # The command takes no options.
    password = password or secrets.token_urlsafe(12)

    with session_factory() as session:
        try:
            result = seed_demo_organization(session, password=password)
        except AlreadySeededError:
            print(
                f"{ORGANIZATION_NAME} already exists, so nothing was changed.\n"
                "To start over, delete the local database and run the migrations again.",
                file=sys.stderr,
            )
            return 1
        session.commit()

    print(
        f"Created {ORGANIZATION_NAME}: {result.properties} properties, {result.units} units, "
        f"{result.residents} residents, {result.requests} requests.\n\n"
        f"Sign in with any of these accounts, all using the password {result.password}\n"
        f"  administrator   {ADMIN_EMAIL}\n"
        f"  manager         {MANAGER_EMAIL}   (manages Maple Court and Riverside Lofts)\n"
        f"  resident        {RESIDENT_EMAIL}\n"
        f"  contractor      {CONTRACTOR_EMAIL}\n"
        f"  property owner  {OWNER_EMAIL}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
