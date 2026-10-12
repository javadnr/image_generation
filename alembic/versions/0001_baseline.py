"""Baseline: converge any database to the current models.

Covers fresh databases (creates everything) and stale ones (adds only
what is missing). Every operation is existence-checked, so this revision
is safe to apply on top of databases migrated with the old manual SQL
files, and safe to re-run.

Also performs the one-time data backfills that used to live in the manual
migrations/ SQL files (plan token grants, free credit grant, mini->flare
model move). Like all Alembic revisions, each runs exactly once per
database (tracked in alembic_version).

Revision ID: 0001_baseline
Revises: None
Create Date: 2026-01-01
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0001_baseline"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _users_columns():
    return [
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("tier", sa.String(length=20)),
        sa.Column("daily_used", sa.Integer()),
        sa.Column("total_used", sa.Integer()),
        sa.Column("token_balance", sa.Integer()),
        sa.Column("last_reset_date", sa.Date()),
        sa.Column("is_generating", sa.Boolean()),
        sa.Column("image_width", sa.Integer()),
        sa.Column("image_height", sa.Integer()),
        sa.Column("image_quality", sa.String(length=10)),
        sa.Column("image_model", sa.String(length=50)),
        sa.Column("optimize_prompt", sa.Boolean()),
        sa.Column("premium_expire_date", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime()),
    ]


def upgrade() -> None:
    # ---- tables (skipped when already present) ----
    op.create_table("users", *_users_columns(), if_not_exists=True)
    op.create_table(
        "bot_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("bot_enabled", sa.Boolean()),
        if_not_exists=True,
    )
    op.create_table(
        "generated_images",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("message_id", sa.BigInteger()),
        sa.Column("file_path", sa.String(length=500)),
        sa.Column("prompt", sa.Text()),
        sa.Column("created_at", sa.DateTime()),
        if_not_exists=True,
    )
    op.create_table(
        "transactions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("plan", sa.String(length=20), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20)),
        sa.Column("payment_authority", sa.String(length=255), nullable=True),
        sa.Column("payment_ref_id", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime()),
        sa.Column("paid_at", sa.DateTime(), nullable=True),
        if_not_exists=True,
    )
    op.create_table(
        "user_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("event_type", sa.String(length=40), nullable=False),
        sa.Column("event_meta", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime()),
        if_not_exists=True,
    )

    # ---- columns (skipped when already present) ----
    for table_name, columns in (
        ("users", _users_columns()),
        ("bot_settings", [
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("bot_enabled", sa.Boolean()),
        ]),
        ("generated_images", [
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("message_id", sa.BigInteger()),
            sa.Column("file_path", sa.String(length=500)),
            sa.Column("prompt", sa.Text()),
            sa.Column("created_at", sa.DateTime()),
        ]),
        ("transactions", [
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("plan", sa.String(length=20), nullable=False),
            sa.Column("amount", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(length=20)),
            sa.Column("payment_authority", sa.String(length=255), nullable=True),
            sa.Column("payment_ref_id", sa.String(length=255), nullable=True),
            sa.Column("created_at", sa.DateTime()),
            sa.Column("paid_at", sa.DateTime(), nullable=True),
        ]),
        ("user_events", [
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("event_type", sa.String(length=40), nullable=False),
            sa.Column("event_meta", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime()),
        ]),
    ):
        for column in columns:
            if column.primary_key:
                continue  # PKs come with the table; never added afterwards
            op.add_column(table_name, column, if_not_exists=True)

    # ---- indexes (skipped when already present) ----
    op.create_index(
        "ix_user_events_type_created", "user_events",
        ["event_type", "created_at"], if_not_exists=True,
    )
    op.create_index(
        "ix_user_events_user", "user_events",
        ["user_id"], if_not_exists=True,
    )
    op.create_index(
        "uq_pending_tx_per_user_plan", "transactions",
        ["user_id", "plan"], unique=True,
        postgresql_where=sa.text("status = 'pending'"),
        if_not_exists=True,
    )

    # ---- one-time data backfills (run exactly once per database) ----
    # Allowance UPDATEs only touch NULL/zero balances on purpose: if this
    # revision ever runs on a database that already has live balances
    # (e.g. first Alembic boot on an old production DB), existing positive
    # balances must be preserved, never reset to full.
    op.execute(
        "UPDATE users SET token_balance = 10000 "
        "WHERE tier = 'bronze' AND (token_balance IS NULL OR token_balance = 0)"
    )
    op.execute(
        "UPDATE users SET token_balance = 25000 "
        "WHERE tier = 'silver' AND (token_balance IS NULL OR token_balance = 0)"
    )
    op.execute(
        "UPDATE users SET token_balance = 60000 "
        "WHERE tier = 'gold' AND (token_balance IS NULL OR token_balance = 0)"
    )
    op.execute(
        "UPDATE users SET token_balance = 1000 "
        "WHERE tier = 'free' AND (token_balance IS NULL OR token_balance = 0)"
    )
    op.execute(
        "UPDATE users SET image_model = 'gpt-image-2.5-flare' "
        "WHERE image_model = 'gpt-image-1-mini'"
    )


def downgrade() -> None:
    # Baseline is not reversible without data loss.
    pass
