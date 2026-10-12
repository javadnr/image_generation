"""Add users.pending_prompt for the generate-confirmation flow.

Revision ID: 0003_pending_prompt
Revises: 0002_discounts
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0003_pending_prompt"
down_revision: Union[str, None] = "0002_discounts"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("pending_prompt", sa.Text(), nullable=True),
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_column("users", "pending_prompt")
