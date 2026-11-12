from sqlalchemy.orm import Session

from app.models import Organization, Role, User
from app.services.organizations import add_membership, create_organization
from app.services.users import create_user


def create_organization_with_administrator(
    session: Session,
    *,
    organization_name: str,
    email: str,
    full_name: str,
    password: str,
) -> tuple[Organization, User]:
    """Create an organization and its first administrator.

    Raises EmailAlreadyRegisteredError if the email already has an account, so an
    existing user is never modified. The caller decides when to commit.
    """
    user = create_user(session, email=email, full_name=full_name, password=password)
    # No signed-in user exists yet, so these events are attributed to the operator tool.
    organization = create_organization(session, name=organization_name, actor=None)
    add_membership(
        session, organization=organization, user=user, roles=[Role.ADMINISTRATOR], actor=None
    )
    return organization, user
