from aiogram import Router, F
from aiogram.types import Message
from bot.services.user import (
    get_or_create_user, check_and_reset_daily, get_remaining, get_tier_limit,
    estimate_tokens_for,
)
from bot.services.models import default_model, images_per_quality
from bot.keyboards.reply import main_menu
from bot.keyboards.inline import plans_button
from bot.texts import badge
import bot.texts as texts

router = Router()

TIER_NAMES_FA = {"free": "آزاد", "bronze": "برنزی", "silver": "نقره‌ای", "gold": "طلایی"}


@router.message(F.text == texts.MAIN_MENU_BALANCE)
async def balance(message: Message, session):
    user = await get_or_create_user(session, message.from_user.id)
    user = await check_and_reset_daily(session, user)
    tier_name = TIER_NAMES_FA.get(user.tier, "آزاد")

    if user.tier == "free":
        daily_remaining = await get_remaining(session, user)
        daily_limit = get_tier_limit("free")
        text = texts.QUOTA_REMAINING_FREE.format(
            daily_remaining=daily_remaining,
            daily_limit=daily_limit,
        )
        out_of_credit = daily_remaining == 0
    else:
        balance_tokens = user.token_balance or 0
        model = user.image_model or default_model()
        quality = user.image_quality or "low"
        estimate = estimate_tokens_for(user)
        per_quality = images_per_quality(balance_tokens, model)
        breakdown = "\n".join(
            f"• {texts.QUALITY_LABELS[q]}: {count:,} تصویر"
            for q, count in per_quality.items()
        ) or "—"
        text = texts.QUOTA_REMAINING_TOKENS.format(
            tier=tier_name,
            balance=f"{balance_tokens:,}",
            model=model,
            breakdown=breakdown,
        )
        out_of_credit = balance_tokens <= 0 or (
            estimate is not None and balance_tokens < estimate
        )

    if out_of_credit:
        text += "\n\n💎 برای ساخت تصاویر بیشتر، اشتراک تهیه کنید 👇"
        await message.answer(badge(text), reply_markup=plans_button())
    else:
        await message.answer(badge(text), reply_markup=main_menu(user))
