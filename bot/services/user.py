import logging

from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession
from bot.db.models import User, UserEvent
from bot.config import settings
from bot.services.analytics import exclude_admins, IMAGE_GENERATION_SUCCESS
from bot.utils.timezone import tehran_day_utc_window, today_in_tehran

logger = logging.getLogger(__name__)


def get_tier_limit(tier: str) -> int:
    # Only the free tier uses image-count limits now; premium is token-based.
    return settings.FREE_LIMIT if tier == "free" else 0


async def get_or_create_user(session: AsyncSession, telegram_id: int) -> User:
    result = await session.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()
    if user is None:
        user = User(telegram_id=telegram_id)
        session.add(user)
        await session.commit()
        await session.refresh(user)
    return user


async def can_generate(session: AsyncSession, user: User) -> bool:
    if user.tier == "free":
        return user.daily_used < get_tier_limit("free")
    estimate = estimate_tokens_for(user)
    if estimate is None:
        logger.warning(
            "No token estimate for model=%s quality=%s; allowing generation",
            user.image_model, user.image_quality,
        )
        return True
    return (user.token_balance or 0) >= estimate


def estimate_tokens_for(user: User) -> int | None:
    from bot.services.models import estimate_tokens, default_model
    return estimate_tokens(
        user.image_model or default_model(),
        user.image_quality or "low",
    )


async def deduct_tokens(session: AsyncSession, user: User, amount: int | None) -> int:
    """Deduct actual output tokens. Floors at zero. Returns remaining balance."""
    if amount is None:
        logger.warning("No usage reported for user=%d; deducting 0", user.telegram_id)
        amount = 0
    user.token_balance = max(0, (user.token_balance or 0) - amount)
    await session.commit()
    return user.token_balance


async def consume_quota(session: AsyncSession, user: User) -> None:
    user.daily_used += 1
    await session.commit()


async def get_remaining(session: AsyncSession, user: User) -> int:
    limit = get_tier_limit(user.tier)
    return max(0, limit - user.daily_used)


def get_edit_cost() -> int:
    return settings.IMAGE_EDIT_COST_TOKENS


def has_edit_balance(user: User) -> bool:
    """Premium-only gate helper: enough balance for one fixed-cost edit."""
    if user.tier == "free":
        return False
    return (user.token_balance or 0) >= get_edit_cost()


async def set_tier(session: AsyncSession, telegram_id: int, tier: str) -> User | None:
    from bot.services.models import plan_allowance
    result = await session.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()
    if user:
        user.tier = tier
        user.token_balance = plan_allowance(tier)
        await session.commit()
        await session.refresh(user)
    return user


async def set_generating(session: AsyncSession, user: User, value: bool) -> None:
    user.is_generating = value
    await session.commit()


VALID_QUALITIES = ("low", "medium", "high")



async def set_quality(session: AsyncSession, user: User, quality: str) -> None:
    if quality not in VALID_QUALITIES:
        raise ValueError(f"Invalid quality: {quality}")
    user.image_quality = quality
    await session.commit()


async def set_model(session: AsyncSession, user: User, model: str) -> None:
    from bot.services.models import model_ids
    if model not in model_ids():
        raise ValueError(f"Invalid model: {model}")
    user.image_model = model
    await session.commit()


async def get_all_users_count(session: AsyncSession) -> int:
    result = await session.execute(select(func.count(User.id)))
    return result.scalar()


async def get_active_today_count(session: AsyncSession) -> int:
    start, end = tehran_day_utc_window(today_in_tehran())
    stmt = (
        select(func.count(func.distinct(UserEvent.user_id)))
        .join(User, UserEvent.user_id == User.id)
        .where(
            UserEvent.event_type == IMAGE_GENERATION_SUCCESS,
            UserEvent.created_at >= start,
            UserEvent.created_at < end,
        )
    )
    result = await session.execute(exclude_admins(stmt))
    return result.scalar() or 0


async def get_joined_today_count(session: AsyncSession) -> int:
    start, end = tehran_day_utc_window(today_in_tehran())
    stmt = select(func.count(User.id)).where(
        User.created_at >= start, User.created_at < end
    )
    result = await session.execute(exclude_admins(stmt))
    return result.scalar()


async def get_tier_users_count(session: AsyncSession, tier: str) -> int:
    result = await session.execute(
        select(func.count(User.id)).where(User.tier == tier)
    )
    return result.scalar()


async def get_tier_images_today(session: AsyncSession, tier: str) -> int:
    """Count today's successful generations for a tier.

    Source is IMAGE_GENERATION_SUCCESS events (images are no longer saved
    to disk/DB). Tier is read from event metadata recorded at success time.
    """
    start, end = tehran_day_utc_window(today_in_tehran())
    stmt = (
        select(UserEvent.event_meta)
        .join(User, UserEvent.user_id == User.id)
        .where(
            UserEvent.event_type == IMAGE_GENERATION_SUCCESS,
            UserEvent.created_at >= start,
            UserEvent.created_at < end,
        )
    )
    result = await session.execute(exclude_admins(stmt))
    return sum(1 for (meta,) in result.all() if (meta or {}).get("tier") == tier)


async def reset_all_daily(session: AsyncSession, include_free: bool = False) -> None:
    stmt = update(User).values(daily_used=0, last_reset_date=today_in_tehran())
    if not include_free:
        stmt = stmt.where(User.tier != "free")
    await session.execute(stmt)
    await session.commit()



