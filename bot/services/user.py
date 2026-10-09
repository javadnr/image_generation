from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession
from bot.db.models import User, GeneratedImage
from bot.config import settings
from bot.services.analytics import exclude_admins
from bot.utils.timezone import tehran_day_utc_window, today_in_tehran


def get_tier_limit(tier: str) -> int:
    return {
        "free": settings.FREE_LIMIT,
        "bronze": settings.BRONZE_LIMIT,
        "silver": settings.SILVER_LIMIT,
        "gold": settings.GOLD_LIMIT,
    }.get(tier, settings.FREE_LIMIT)


def get_tier_max_limit(tier: str) -> int | None:
    if tier == "free":
        return None
    return {
        "bronze": settings.BRONZE_MAX_LIMIT,
        "silver": settings.SILVER_MAX_LIMIT,
        "gold": settings.GOLD_MAX_LIMIT,
    }.get(tier)


async def get_or_create_user(session: AsyncSession, telegram_id: int) -> User:
    result = await session.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()
    if user is None:
        user = User(telegram_id=telegram_id)
        session.add(user)
        await session.commit()
        await session.refresh(user)
    return user


async def check_and_reset_daily(session: AsyncSession, user: User) -> User:
    if user.tier == "free":
        # Free credit is one-time, never resets.
        return user
    today = today_in_tehran()
    if user.last_reset_date != today:
        user.daily_used = 0
        user.last_reset_date = today
        await session.commit()
        await session.refresh(user)
    return user


async def check_max_limit(session: AsyncSession, user: User) -> bool:
    """Check if premium user hit max limit. Returns True if downgraded."""
    if user.tier == "free":
        return False
    max_limit = get_tier_max_limit(user.tier)
    if max_limit is not None and user.total_used >= max_limit:
        user.tier = "free"
        user.total_used = 0
        user.daily_used = 0
        await session.commit()
        await session.refresh(user)
        return True
    return False


async def can_generate(session: AsyncSession, user: User) -> bool:
    user = await check_and_reset_daily(session, user)
    limit = get_tier_limit(user.tier)
    return user.daily_used < limit


async def consume_quota(session: AsyncSession, user: User) -> None:
    user.daily_used += 1
    if user.tier != "free":
        user.total_used += 1
    await session.commit()


async def get_remaining(session: AsyncSession, user: User) -> int:
    user = await check_and_reset_daily(session, user)
    limit = get_tier_limit(user.tier)
    return max(0, limit - user.daily_used)


async def get_total_remaining(session: AsyncSession, user: User) -> int | None:
    max_limit = get_tier_max_limit(user.tier)
    if max_limit is None:
        return None
    return max(0, max_limit - user.total_used)


async def set_tier(session: AsyncSession, telegram_id: int, tier: str) -> User | None:
    result = await session.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()
    if user:
        user.tier = tier
        await session.commit()
        await session.refresh(user)
    return user


async def set_generating(session: AsyncSession, user: User, value: bool) -> None:
    user.is_generating = value
    await session.commit()


async def get_all_users_count(session: AsyncSession) -> int:
    result = await session.execute(select(func.count(User.id)))
    return result.scalar()


async def get_active_today_count(session: AsyncSession) -> int:
    today = today_in_tehran()
    stmt = select(func.count(User.id)).where(
        User.last_reset_date == today,
        User.daily_used > 0,
    )
    result = await session.execute(exclude_admins(stmt))
    return result.scalar()


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
    start, end = tehran_day_utc_window(today_in_tehran())
    stmt = (
        select(func.count(GeneratedImage.id))
        .join(User)
        .where(
            User.tier == tier,
            GeneratedImage.created_at >= start,
            GeneratedImage.created_at < end,
        )
    )
    result = await session.execute(exclude_admins(stmt))
    return result.scalar()


async def reset_all_daily(session: AsyncSession) -> None:
    await session.execute(
        update(User)
        .where(User.tier != "free")
        .values(daily_used=0, last_reset_date=today_in_tehran())
    )
    await session.commit()



