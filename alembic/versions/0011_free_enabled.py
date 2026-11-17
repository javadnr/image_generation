"""Add free_enabled to bot_settings (admin toggle for free usage).

NULL means "use the ALLOW_FREE .env default".

Revision ID: 0011_free_enabled
Revises: 0010_free_images_generated
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0011_free_enabled"
down_revision: Union[str, None] = "0010_free_images_generated"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "bot_settings",
        sa.Column("free_enabled", sa.Boolean(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("bot_settings", "free_enabled")
