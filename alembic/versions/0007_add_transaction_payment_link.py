"""add transaction payment_link

Revision ID: 0007_add_transaction_payment_link
Revises: 0006_source_widen
Create Date: 2026-10-27 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0007_add_transaction_payment_link"
down_revision: Union[str, None] = "0006_source_widen"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("transactions", sa.Column("payment_link", sa.String(length=512), nullable=True))


def downgrade() -> None:
    op.drop_column("transactions", "payment_link")
