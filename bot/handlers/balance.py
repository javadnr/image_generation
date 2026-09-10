from aiogram import Router, F
from aiogram.types import Message
from bot.services.user import get_or_create_user, check_and_reset_daily, get_remaining, get_total_remaining, get_tier_limit
from bot.keyboards.reply import main_menu
from bot.texts import badge
import bot.texts as texts

router = Router()


@router.message(F.text == texts.MAIN_MENU_BALANCE)
async def balance(message: Message, session):
    user = await get_or_create_user(session, message.from_user.id)
    user = await check_and_reset_daily(session, user)
    daily_remaining = await get_remaining(session, user)
    daily_limit = get_tier_limit(user.tier)
    tier_name = {"free": "آزاد", "bronze": "برنزی", "silver": "نقره‌ای", "gold": "طلایی"}.get(user.tier, "آزاد")

    total_remaining = await get_total_remaining(session, user)
    if total_remaining is not None:
        from bot.services.user import get_tier_max_limit
        max_limit = get_tier_max_limit(user.tier)
        text = texts.QUOTA_REMAINING.format(
            tier=tier_name,
            daily_remaining=daily_remaining,
            daily_limit=daily_limit,
            total_remaining=total_remaining,
            max_limit=max_limit,
        )
    else:
        text = texts.QUOTA_REMAINING_FREE.format(
            daily_remaining=daily_remaining,
            daily_limit=daily_limit,
        )

    await message.answer(badge(text), reply_markup=main_menu(user))
