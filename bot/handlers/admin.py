from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from bot.config import settings
from bot.services.user import (
    get_all_users_count, get_active_today_count, get_joined_today_count,
    get_tier_users_count, get_tier_images_today, reset_all_daily, set_tier,
)
from bot.keyboards.inline import admin_status
from bot.db.engine import async_session
from sqlalchemy import select, update
from bot.db.models import BotSettings
import bot.texts as texts

router = Router()


@router.message(F.text == texts.MAIN_MENU_ADMIN)
async def bot_status(message: Message, session):
    if message.from_user.id not in settings.ADMIN_IDS:
        return

    result = await session.execute(select(BotSettings).where(BotSettings.id == 1))
    settings_row = result.scalar_one_or_none()
    bot_enabled = settings_row.bot_enabled if settings_row else True

    total_users = await get_all_users_count(session)
    active_today = await get_active_today_count(session)
    joined_today = await get_joined_today_count(session)

    free_images = await get_tier_images_today(session, "free")
    bronze_images = await get_tier_images_today(session, "bronze")
    silver_images = await get_tier_images_today(session, "silver")
    gold_images = await get_tier_images_today(session, "gold")

    bronze_users = await get_tier_users_count(session, "bronze")
    silver_users = await get_tier_users_count(session, "silver")
    gold_users = await get_tier_users_count(session, "gold")

    status_text = "فعال" if bot_enabled else "غیرفعال"

    text = texts.ADMIN_STATS.format(
        status=status_text,
        total_users=total_users,
        active_today=active_today,
        joined_today=joined_today,
        free_images=free_images,
        bronze_images=bronze_images,
        silver_images=silver_images,
        gold_images=gold_images,
        bronze_users=bronze_users,
        silver_users=silver_users,
        gold_users=gold_users,
    )

    await message.answer(text, reply_markup=admin_status(bot_enabled))


@router.callback_query(F.data == "toggle_bot")
async def toggle_bot(callback: CallbackQuery, session):
    if callback.from_user.id not in settings.ADMIN_IDS:
        await callback.answer("⛔ دسترسی ندارید.", show_alert=True)
        return

    result = await session.execute(select(BotSettings).where(BotSettings.id == 1))
    settings_row = result.scalar_one_or_none()

    if settings_row:
        settings_row.bot_enabled = not settings_row.bot_enabled
    else:
        settings_row = BotSettings(id=1, bot_enabled=False)
        session.add(settings_row)

    await session.commit()

    new_status = "فعال" if settings_row.bot_enabled else "غیرفعال"
    toggle_text = texts.ADMIN_TOGGLE_ON if settings_row.bot_enabled else texts.ADMIN_TOGGLE_OFF

    await callback.message.edit_text(
        f"📊 وضعیت ربات\n\n🟢 وضعیت: {new_status}",
        reply_markup=admin_status(settings_row.bot_enabled),
    )
    await callback.answer(toggle_text)


@router.callback_query(F.data == "reset_daily")
async def reset_daily_handler(callback: CallbackQuery, session):
    if callback.from_user.id not in settings.ADMIN_IDS:
        await callback.answer("⛔ دسترسی ندارید.", show_alert=True)
        return

    await reset_all_daily(session)
    await callback.answer(texts.ADMIN_RESET_DONE)


@router.message(F.text.startswith("/set_premium"))
async def set_premium_cmd(message: Message, session):
    if message.from_user.id not in settings.ADMIN_IDS:
        return

    parts = message.text.split()
    if len(parts) != 3:
        await message.answer(texts.ADMIN_USAGE)
        return

    try:
        user_id = int(parts[1])
    except ValueError:
        await message.answer(texts.ADMIN_USAGE)
        return

    tier = parts[2].lower()
    if tier not in ("free", "bronze", "silver", "gold"):
        await message.answer(texts.ADMIN_INVALID_TIER)
        return

    user = await set_tier(session, user_id, tier)
    if user:
        await message.answer(texts.ADMIN_ACTIVATED.format(tier=tier, user_id=user_id))
        from bot.services.report import send_premium_report
        if tier != "free":
            await send_premium_report(message.bot, user_id, tier)
    else:
        await message.answer(f"⚠️ کاربر با ID {user_id} یافت نشد.")


@router.message(F.text.startswith("/stats"))
async def stats_cmd(message: Message, session):
    if message.from_user.id not in settings.ADMIN_IDS:
        return

    total = await get_all_users_count(session)
    active = await get_active_today_count(session)
    joined = await get_joined_today_count(session)
    await message.answer(
        f"📊 آمار کلی\n\n"
        f"👥 کل: {total}\n"
        f"🟢 فعال امروز: {active}\n"
        f"🆕 جدید امروز: {joined}"
    )
