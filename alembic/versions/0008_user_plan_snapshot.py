"""Add users.plan_snapshot for activation-time plan limitations.

Revision ID: 0008_user_plan_snapshot
Revises: 0007_add_transaction_payment_link
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0008_user_plan_snapshot"
down_revision: Union[str, None] = "0007_add_transaction_payment_link"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("plan_snapshot", sa.JSON(), nullable=True),
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_column("users", "plan_snapshot")
