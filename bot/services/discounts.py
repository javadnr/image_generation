"""Time-limited plan discounts (/off admin command).

A discount targets one plan or all plans ("all" scope), carries an integer
percent, and expires at a fixed time. Expired rows are ignored (never
deleted automatically, so history is preserved).
"""
import logging
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import Discount, User

logger = logging.getLogger(__name__)

VALID_SCOPES = ("bronze", "silver", "gold", "all")


def parse_off_command(text: str):
    """Parse '/off <plan|all> <percent> <days>'.

    Returns (scope, percent, days) or None when the format is invalid.
    Percent 0 clears the discount for that scope.
    """
    parts = (text or "").split()
    if len(parts) != 4 or parts[0] != "/off":
        return None
    scope = parts[1].lower()
    if scope not in VALID_SCOPES:
        return None
    try:
        percent = int(parts[2])
        days = int(parts[3])
    except ValueError:
        return None
    if not 0 <= percent <= 100:
        return None
    if percent > 0 and days <= 0:
        return None
    return scope, percent, days


async def set_discount(session: AsyncSession, scope: str, percent: int, days: int) -> None:
    result = await session.execute(select(Discount).where(Discount.scope == scope))
    for row in result.scalars().all():
        await session.delete(row)
    if percent > 0:
        session.add(Discount(
            scope=scope,
            percent=percent,
            expires_at=datetime.now() + timedelta(days=days),
        ))
    await session.commit()
    logger.info("Discount set: scope=%s percent=%d days=%d", scope, percent, days)


async def get_active_discounts(session: AsyncSession) -> dict:
    """Return {scope: (percent, expires_at)} for non-expired discounts."""
    now = datetime.now()
    result = await session.execute(
        select(Discount).where(Discount.expires_at > now)
    )
    return {row.scope: (row.percent, row.expires_at) for row in result.scalars().all()}


async def free_user_ids(session: AsyncSession) -> list:
    """Telegram IDs of users without a plan (discount announcement targets)."""
    result = await session.execute(
        select(User.telegram_id).where(User.tier == "free")
    )
    return list(result.scalars().all())


def discount_info(plan: str, discounts: dict | None) -> tuple:
    """(percent, expires_at|None) for a plan: plan-specific wins, else 'all'."""
    if not discounts:
        return 0, None
    if plan in discounts:
        return discounts[plan]
    if "all" in discounts:
        return discounts["all"]
    return 0, None


def discount_for(plan: str, discounts: dict | None) -> int:
    """Effective percent for a plan: plan-specific wins, else 'all', else 0."""
    return discount_info(plan, discounts)[0]


def discounted_price(base: int | None, percent: int) -> int | None:
    """Apply percent off with exact integer math (50% of 50000 stays 25000).

    Only the undiscounted base price follows the ceil10k rule; a discounted
    price is kept as-is so the percent off is exact.
    """
    if base is None:
        return None
    if not percent:
        return base
    return base * (100 - percent) // 100
