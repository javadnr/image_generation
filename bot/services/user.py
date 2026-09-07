from datetime import date
from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession
from bot.db.models import User, GeneratedImage

TIER_LIMITS = {
    "free": 2,
    "bronze": 10,
    "silver": 25,
    "gold": 50,
}


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
    today = date.today()
    if user.last_reset_date != today:
        user.daily_used = 0
        user.last_reset_date = today
        await session.commit()
        await session.refresh(user)
    return user


async def can_generate(session: AsyncSession, user: User) -> bool:
    user = await check_and_reset_daily(session, user)
    limit = TIER_LIMITS.get(user.tier, 2)
    return user.daily_used < limit


async def consume_quota(session: AsyncSession, user: User) -> None:
    user.daily_used += 1
    await session.commit()


async def get_remaining(session: AsyncSession, user: User) -> int:
    user = await check_and_reset_daily(session, user)
    limit = TIER_LIMITS.get(user.tier, 2)
    return max(0, limit - user.daily_used)


async def set_tier(session: AsyncSession, telegram_id: int, tier: str) -> User | None:
    result = await session.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()
    if user:
        user.tier = tier
        await session.commit()
        await session.refresh(user)
    return user


async def set_resolution(session: AsyncSession, user: User, width: int, height: int) -> None:
    user.image_width = width
    user.image_height = height
    await session.commit()


async def toggle_optimize(session: AsyncSession, user: User) -> None:
    user.optimize_prompt = not user.optimize_prompt
    await session.commit()


async def set_generating(session: AsyncSession, user: User, value: bool) -> None:
    user.is_generating = value
    await session.commit()


async def save_image(session: AsyncSession, user: User, message_id: int, file_path: str, prompt: str) -> None:
    img = GeneratedImage(
        user_id=user.id,
        message_id=message_id,
        file_path=file_path,
        prompt=prompt,
    )
    session.add(img)
    await session.commit()

    result = await session.execute(
        select(GeneratedImage)
        .where(GeneratedImage.user_id == user.id)
        .order_by(GeneratedImage.created_at.desc())
    )
    images = result.scalars().all()
    if len(images) > 5:
        for old_img in images[5:]:
            import os
            if os.path.exists(old_img.file_path):
                os.remove(old_img.file_path)
            await session.delete(old_img)
        await session.commit()


async def get_image_by_message(session: AsyncSession, user: User, message_id: int) -> GeneratedImage | None:
    result = await session.execute(
        select(GeneratedImage).where(
            GeneratedImage.user_id == user.id,
            GeneratedImage.message_id == message_id,
        )
    )
    return result.scalar_one_or_none()


async def get_all_users_count(session: AsyncSession) -> int:
    result = await session.execute(select(func.count(User.id)))
    return result.scalar()


async def get_active_today_count(session: AsyncSession) -> int:
    today = date.today()
    result = await session.execute(
        select(func.count(User.id)).where(
            User.last_reset_date == today,
            User.daily_used > 0,
        )
    )
    return result.scalar()


async def get_joined_today_count(session: AsyncSession) -> int:
    today = date.today()
    result = await session.execute(
        select(func.count(User.id)).where(func.date(User.created_at) == today)
    )
    return result.scalar()


async def get_tier_users_count(session: AsyncSession, tier: str) -> int:
    result = await session.execute(
        select(func.count(User.id)).where(User.tier == tier)
    )
    return result.scalar()


async def get_tier_images_today(session: AsyncSession, tier: str) -> int:
    today = date.today()
    result = await session.execute(
        select(func.count(GeneratedImage.id))
        .join(User)
        .where(User.tier == tier, func.date(GeneratedImage.created_at) == today)
    )
    return result.scalar()


async def reset_all_daily(session: AsyncSession) -> None:
    await session.execute(
        update(User).values(daily_used=0, last_reset_date=date.today())
    )
    await session.commit()
