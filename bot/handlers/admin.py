from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from bot.config import settings
from bot.services.user import (
    get_all_users_count, get_active_today_count, get_joined_today_count,
    get_tier_users_count, get_tier_images_today, reset_all_daily, set_tier,
)
from bot.services import analytics as az
from bot.keyboards.inline import admin_status
from bot.db.engine import async_session
from sqlalchemy import select, update
from bot.db.models import BotSettings
from bot.texts import badge
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

    activated_today, joined = await az.get_new_users_with_success_today(session)
    started_today = await az.get_images_started_today(session)
    success_today = await az.get_images_success_today(session)
    failed_today = await az.get_images_failed_today(session)
    limit_users = await az.get_free_limit_users_today(session)
    limit_new = await az.get_new_free_limit_users_today(session)
    click_total, click_unique = await az.get_premium_clicks_today(session)
    pricing_viewers = await az.get_pricing_viewers_today(session)
    pricing_new = await az.get_new_pricing_viewers_today(session)
    plan_sel = await az.get_plan_selection_today(session)
    pay_started, pay_success = await az.get_payments_today(session)
    conv = await az.get_conversions(session)
    retention = await az.get_retention_overview(session)

    def pct(x: float) -> str:
        return f"{x * 100:.1f}"

    activation_rate = pct(az.safe_rate(activated_today, joined if joined else joined_today))

    status_text = "فعال" if bot_enabled else "غیرفعال"

    text = badge(
        texts.ADMIN_STATS.format(
            status=status_text,
            total_users=total_users,
            active_today=active_today,
            joined_today=joined_today,
            activated_today=activated_today,
            activation_rate=activation_rate,
            started_today=started_today,
            success_today=success_today,
            failed_today=failed_today,
            limit_users=limit_users,
            limit_new=limit_new,
            click_total=click_total,
            click_unique=click_unique,
            pricing_viewers=pricing_viewers,
            pricing_new=pricing_new,
            plan_bronze=plan_sel.get("bronze", 0),
            plan_silver=plan_sel.get("silver", 0),
            plan_gold=plan_sel.get("gold", 0),
            pay_started=pay_started,
            pay_success=pay_success,
            conv_user=pct(conv["user_buyer"]),
            conv_limit=pct(conv["limit_buyer"]),
            conv_pricing=pct(conv["pricing_buyer"]),
            d1=pct(retention.get(1, 0.0)),
            d3=pct(retention.get(3, 0.0)),
            d7=pct(retention.get(7, 0.0)),
            d14=pct(retention.get(14, 0.0)),
            d30=pct(retention.get(30, 0.0)),
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

    await reset_all_daily(session)
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
