"""Record work order outcome

Revision ID: c6a1fc04604f
Revises: 1b4b809cb1d9
Create Date: 2026-11-12 22:20:49.707301

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c6a1fc04604f"
down_revision: str | Sequence[str] | None = "1b4b809cb1d9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("work_orders", schema=None) as batch_op:
        batch_op.add_column(sa.Column("resolution", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("final_cost_cents", sa.BigInteger(), nullable=True))
        batch_op.add_column(sa.Column("currency", sa.String(length=3), nullable=True))
        batch_op.add_column(sa.Column("verified_by_user_id", sa.Uuid(), nullable=True))
        batch_op.add_column(sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.create_foreign_key(
            batch_op.f("fk_work_orders_verified_by_user_id_users"),
            "users",
            ["verified_by_user_id"],
            ["id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("work_orders", schema=None) as batch_op:
        batch_op.drop_constraint(
            batch_op.f("fk_work_orders_verified_by_user_id_users"), type_="foreignkey"
        )
        batch_op.drop_column("verified_at")
        batch_op.drop_column("verified_by_user_id")
        batch_op.drop_column("currency")
        batch_op.drop_column("final_cost_cents")
        batch_op.drop_column("resolution")
