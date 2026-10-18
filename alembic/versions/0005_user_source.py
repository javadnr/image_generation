"""Add users.source for ad-platform attribution (?start=platform).

Revision ID: 0005_user_source
Revises: 0004_image_size
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0005_user_source"
down_revision: Union[str, None] = "0004_image_size"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("source", sa.String(length=20), nullable=True),
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_column("users", "source")
