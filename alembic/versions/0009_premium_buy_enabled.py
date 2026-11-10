"""Add premium_buy_enabled to bot_settings.

Revision ID: 0009_premium_buy_enabled
Revises: 0008_user_plan_snapshot
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0009_premium_buy_enabled"
down_revision: Union[str, None] = "0008_user_plan_snapshot"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "bot_settings",
        sa.Column("premium_buy_enabled", sa.Boolean(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("bot_settings", "premium_buy_enabled")
