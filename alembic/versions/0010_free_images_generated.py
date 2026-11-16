"""Restore the 0010 revision id that live databases are stamped with.

The original revision file was lost; its only effect was adding the
`users.free_images_generated` column, which no code reads or writes
anymore. Existing databases already have it and are stamped 0010, so this
revision is intentionally a no-op: it reconnects the history instead of
failing `alembic upgrade head` on boot.

Revision ID: 0010_free_images_generated
Revises: 0009_premium_buy_enabled
"""

from typing import Union

# revision identifiers, used by Alembic.
revision: str = "0010_free_images_generated"
down_revision: Union[str, None] = "0009_premium_buy_enabled"
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
