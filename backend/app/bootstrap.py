"""Create the first organization and administrator for a new installation.

Usage, from backend/:

    python -m app.bootstrap --organization "Harbor Property Management" \\
        --email admin@example.com --name "Alex Rivera"

The password is requested at a hidden prompt so it never appears in shell history.
"""

import argparse
import getpass
import sys
from collections.abc import Callable, Sequence

from sqlalchemy.orm import Session

from app.db.session import get_engine
from app.services.bootstrap import create_organization_with_administrator
from app.services.users import EmailAlreadyRegisteredError, InvalidPasswordError


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.bootstrap",
        description="Create an organization and its first administrator.",
    )
    parser.add_argument("--organization", required=True, help="Organization name")
    parser.add_argument("--email", required=True, help="Administrator email address")
    parser.add_argument("--name", required=True, help="Administrator full name")
    return parser


def _default_session() -> Session:
    return Session(get_engine())


def main(
    argv: Sequence[str] | None = None,
    *,
    session_factory: Callable[[], Session] = _default_session,
    read_password: Callable[[str], str] = getpass.getpass,
) -> int:
    args = _build_parser().parse_args(argv)

    if "@" not in args.email:
        print("Error: the email address is not valid.", file=sys.stderr)
        return 1

    password = read_password("Password: ")
    if password != read_password("Repeat password: "):
        print("Error: the passwords do not match.", file=sys.stderr)
        return 1

    with session_factory() as session:
        try:
            organization, user = create_organization_with_administrator(
                session,
                organization_name=args.organization,
                email=args.email,
                full_name=args.name,
                password=password,
            )
        except EmailAlreadyRegisteredError:
            print(
                f"Error: {args.email} already has an account; nothing was changed.", file=sys.stderr
            )
            return 1
        except InvalidPasswordError as error:
            print(f"Error: {error}.", file=sys.stderr)
            return 1

        session.commit()
        print(f"Created organization '{organization.name}' with administrator {user.email}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
