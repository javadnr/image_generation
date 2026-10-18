"""Widen users.source to 64 chars (full Telegram start-payload length).

Revision ID: 0006_source_widen
Revises: 0005_user_source
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0006_source_widen"
down_revision: Union[str, None] = "0005_user_source"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "users", "source",
        existing_type=sa.String(length=20),
        type_=sa.String(length=64),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "users", "source",
        existing_type=sa.String(length=64),
        type_=sa.String(length=20),
        existing_nullable=True,
    )
