"""Initial baseline

Revision ID: 7c1e2f4a9b30
Revises:
Create Date: 2026-11-12 16:00:00.000000

"""

from collections.abc import Sequence

revision: str = "7c1e2f4a9b30"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
