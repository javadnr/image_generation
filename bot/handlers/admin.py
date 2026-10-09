import asyncio
import logging

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from bot.config import settings
from bot.services.user import (
    get_all_users_count, get_active_today_count, get_joined_today_count,
    get_tier_users_count, get_tier_images_today, reset_all_daily, set_tier,
)
from bot.services import analytics as az
from bot.services.payment import activate_plan, deactivate_plan, PLAN_LIMITS, PLAN_MAX_LIMITS
from bot.keyboards.inline import admin_status
from bot.keyboards.reply import main_menu
from bot.db.engine import async_session
from sqlalchemy import select, update
from bot.db.models import BotSettings, User
from bot.texts import badge
import bot.texts as texts

logger = logging.getLogger(__name__)

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

    started_today = await az.get_images_started_today(session)
    success_today = await az.get_images_success_today(session)
    failed_today = await az.get_images_failed_today(session)
    click_total, click_unique = await az.get_premium_clicks_today(session)
    pricing_viewers = await az.get_pricing_viewers_today(session)
    pricing_new = await az.get_new_pricing_viewers_today(session)
    plan_sel = await az.get_plan_selection_today(session)
    pay_started, pay_success = await az.get_payments_today(session)

    status_text = "فعال" if bot_enabled else "غیرفعال"

    text = badge(
        texts.ADMIN_STATS.format(
            status=status_text,
            total_users=total_users,
            active_today=active_today,
            joined_today=joined_today,
            started_today=started_today,
            success_today=success_today,
            failed_today=failed_today,
            click_total=click_total,
            click_unique=click_unique,
            pricing_viewers=pricing_viewers,
            pricing_new=pricing_new,
            plan_bronze=plan_sel.get("bronze", 0),
            plan_silver=plan_sel.get("silver", 0),
            plan_gold=plan_sel.get("gold", 0),
            pay_started=pay_started,
            pay_success=pay_success,
            free_images=free_images,
            bronze_images=bronze_images,
            silver_images=silver_images,
            gold_images=gold_images,
            bronze_users=bronze_users,
            silver_users=silver_users,
            gold_users=gold_users,
        )
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
        badge(f"📊 وضعیت ربات\n\n🟢 وضعیت: {new_status}"),
        reply_markup=admin_status(settings_row.bot_enabled),
    )
    await callback.answer(toggle_text)


@router.callback_query(F.data == "reset_daily")
async def reset_daily_handler(callback: CallbackQuery, session):
    if callback.from_user.id not in settings.ADMIN_IDS:
        await callback.answer("⛔ دسترسی ندارید.", show_alert=True)
        return

    await reset_all_daily(session, include_free=True)
    await callback.answer(texts.ADMIN_RESET_DONE)


@router.message(F.text.startswith("/set_premium"))
async def set_premium_cmd(message: Message, session):
    if message.from_user.id not in settings.ADMIN_IDS:
        return

    parts = message.text.split()
    if len(parts) != 3:
        await message.answer(badge(texts.ADMIN_USAGE))
        return

    try:
        user_id = int(parts[1])
    except ValueError:
        await message.answer(badge(texts.ADMIN_USAGE))
        return

    tier = parts[2].lower()
    if tier not in ("free", "bronze", "silver", "gold"):
        await message.answer(badge(texts.ADMIN_INVALID_TIER))
        return

    user = await set_tier(session, user_id, tier)
    if user:
        await message.answer(badge(texts.ADMIN_ACTIVATED.format(tier=tier, user_id=user_id)))
        from bot.services.report import send_premium_report
        if tier != "free":
            await send_premium_report(
                message.bot, user_id, tier, expire_dt=user.premium_expire_date
            )
    else:
        await message.answer(badge(f"⚠️ کاربر با ID {user_id} یافت نشد."))


@router.message(F.text.startswith("/activate"))
async def activate_cmd(message: Message, session):
    if message.from_user.id not in settings.ADMIN_IDS:
        return

    parts = message.text.split()
    if len(parts) != 3:
        await message.answer(badge(texts.ADMIN_ACTIVATE_USAGE))
        return

    tier = parts[1].lower()
    if tier not in ("bronze", "silver", "gold"):
        await message.answer(badge(texts.ADMIN_INVALID_TIER))
        return

    try:
        user_id = int(parts[2])
    except ValueError:
        await message.answer(badge(texts.ADMIN_ACTIVATE_USAGE))
        return

    result = await session.execute(select(User).where(User.telegram_id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        await message.answer(badge(f"⚠️ کاربر با ID {user_id} یافت نشد."))
        return

    await activate_plan(session, user, tier)
    await message.answer(badge(texts.ADMIN_ACTIVATED.format(tier=tier, user_id=user_id)))

    from bot.services.report import send_premium_report
    await send_premium_report(
        message.bot, user_id, tier, expire_dt=user.premium_expire_date
    )

    expire = user.premium_expire_date.strftime("%Y/%m/%d") if user.premium_expire_date else "—"
    try:
        await message.bot.send_message(
            user_id,
            badge(
                f"✅ اشتراک {texts.TIER_NAMES_FA[tier]} برای شما فعال شد!\n\n"
                f"📊 سقف روزانه: {PLAN_LIMITS[tier]} تصویر\n"
                f"📊 سقف کل: {PLAN_MAX_LIMITS[tier]} تصویر\n"
                f"📅 پایان اشتراک: {expire}"
            ),
            reply_markup=main_menu(user),
        )
    except Exception:
        logger.exception("Failed to notify user %d about activation", user_id)
        await message.answer(badge("⚠️ فعال‌سازی انجام شد اما اطلاع‌رسانی به کاربر ممکن نشد (ربات بلاک شده؟)."))


@router.message(F.text.startswith("/deactivate"))
async def deactivate_cmd(message: Message, session):
    if message.from_user.id not in settings.ADMIN_IDS:
        return

    parts = message.text.split()
    if len(parts) != 2:
        await message.answer(badge(texts.ADMIN_DEACTIVATE_USAGE))
        return

    try:
        user_id = int(parts[1])
    except ValueError:
        await message.answer(badge(texts.ADMIN_DEACTIVATE_USAGE))
        return

    result = await session.execute(select(User).where(User.telegram_id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        await message.answer(badge(f"⚠️ کاربر با ID {user_id} یافت نشد."))
        return

    await deactivate_plan(session, user)
    await message.answer(badge(texts.ADMIN_DEACTIVATED.format(user_id=user_id)))

    try:
        await message.bot.send_message(
            user_id,
            badge(texts.USER_DEACTIVATED),
            reply_markup=main_menu(user),
        )
    except Exception:
        logger.exception("Failed to notify user %d about deactivation", user_id)
        await message.answer(badge("⚠️ غیرفعال‌سازی انجام شد اما اطلاع‌رسانی به کاربر ممکن نشد (ربات بلاک شده؟)."))


@router.message(F.text.startswith("/broadcast"))
async def broadcast_cmd(message: Message, session):
    if message.from_user.id not in settings.ADMIN_IDS:
        return

    reply = message.reply_to_message
    text = message.text[len("/broadcast"):].strip()

    if reply is None and not text:
        await message.answer(badge(texts.ADMIN_BROADCAST_USAGE))
        return

    result = await session.execute(select(User.telegram_id))
    user_ids = list(result.scalars().all())
    if not user_ids:
        await message.answer(badge("⚠️ کاربری برای ارسال وجود ندارد."))
        return

    await message.answer(badge(texts.ADMIN_BROADCAST_STARTED))

    bot = message.bot
    admin_chat_id = message.chat.id

    async def _run():
        ok = fail = 0
        for uid in user_ids:
            try:
                if reply is not None:
                    await bot.copy_message(uid, message.chat.id, reply.message_id)
                else:
                    await bot.send_message(uid, badge(text))
                ok += 1
            except Exception:
                logger.exception("Broadcast failed for user %d", uid)
                fail += 1
            await asyncio.sleep(0.05)
        try:
            await bot.send_message(
                admin_chat_id,
                badge(texts.ADMIN_BROADCAST_DONE.format(ok=ok, fail=fail)),
            )
        except Exception:
            logger.exception("Failed to send broadcast summary")

    asyncio.create_task(_run())


@router.message(F.text.startswith("/stats"))
async def stats_cmd(message: Message, session):
    if message.from_user.id not in settings.ADMIN_IDS:
        return

    total = await get_all_users_count(session)
    active = await get_active_today_count(session)
    joined = await get_joined_today_count(session)
    await message.answer(
        badge(
            f"📊 آمار کلی\n\n"
            f"👥 کل: {total}\n"
            f"🟢 فعال امروز: {active}\n"
            f"🆕 جدید امروز: {joined}"
        )
    )
