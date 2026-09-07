from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from bot.services.user import get_or_create_user
from bot.services.report import send_premium_report, TIER_PRICES
from bot.keyboards.inline import premium_menu
from bot.db.engine import async_session
from bot.config import settings
import bot.texts as texts

router = Router()


@router.message(F.text == texts.MAIN_MENU_PREMIUM)
async def premium(message: Message, session):
    user = await get_or_create_user(session, message.from_user.id)
    tier_name = {"free": "ندارد", "bronze": "🥉 برنزی", "silver": "🥈 نقره‌ای", "gold": "🥇 طلایی"}.get(user.tier, "آزاد")
    text = (
        f"{texts.PREMIUM_TITLE}\n\n"
        f"{texts.PREMIUM_CURRENT.format(tier=tier_name)}\n\n"
        f"{texts.PREMIUM_BRONZE.format(price=settings.BRONZE_PRICE):,}\n\n"
        f"{texts.PREMIUM_SILVER.format(price=settings.SILVER_PRICE):,}\n\n"
        f"{texts.PREMIUM_GOLD.format(price=settings.GOLD_PRICE):,}"
    )
    await message.answer(text, reply_markup=premium_menu(user))


@router.callback_query(F.data.startswith("buy_"))
async def buy_tier(callback: CallbackQuery, session):
    tier = callback.data.replace("buy_", "")
    if tier not in ("bronze", "silver", "gold"):
        await callback.answer(texts.ADMIN_INVALID_TIER, show_alert=True)
        return

    user = await get_or_create_user(session, callback.from_user.id)
    user.tier = tier
    await session.commit()

    price = TIER_PRICES.get(tier, 0)
    tier_name = {"bronze": "🥉 برنزی", "silver": "🥈 نقره‌ای", "gold": "🥇 طلایی"}.get(tier)

    await callback.message.edit_text(
        f"✅ اشتراک {tier_name} فعال شد!\n\n"
        f"💰 قیمت: {price:,} تومان",
    )

    await send_premium_report(callback.bot, callback.from_user.id, tier)
    await callback.answer()


@router.callback_query(F.data == "back_premium")
async def back_to_premium(callback: CallbackQuery, session):
    user = await get_or_create_user(session, callback.from_user.id)
    tier_name = {"free": "ندارد", "bronze": "🥉 برنزی", "silver": "🥈 نقره‌ای", "gold": "🥇 طلایی"}.get(user.tier, "آزاد")
    text = (
        f"{texts.PREMIUM_TITLE}\n\n"
        f"{texts.PREMIUM_CURRENT.format(tier=tier_name)}\n\n"
        f"{texts.PREMIUM_BRONZE.format(price=settings.BRONZE_PRICE):,}\n\n"
        f"{texts.PREMIUM_SILVER.format(price=settings.SILVER_PRICE):,}\n\n"
        f"{texts.PREMIUM_GOLD.format(price=settings.GOLD_PRICE):,}"
    )
    await callback.message.edit_text(text, reply_markup=premium_menu(user))
    await callback.answer()
