"""Add users.image_size for the aspect-ratio picker.

Revision ID: 0004_image_size
Revises: 0003_pending_prompt
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0004_image_size"
down_revision: Union[str, None] = "0003_pending_prompt"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("image_size", sa.String(length=10), nullable=True),
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_column("users", "image_size")
