from aiogram import Router, F
from aiogram.types import Message
from bot.services.user import get_or_create_user, can_generate
from bot.services.models import default_model, images_per_quality
from bot.keyboards.reply import main_menu
from bot.keyboards.inline import plans_button
from bot.texts import badge
import bot.texts as texts

router = Router()

TIER_NAMES_FA = {"free": "آزاد", "bronze": "برنزی", "silver": "نقره‌ای", "gold": "طلایی", "diamond": "الماسی"}


@router.message(F.text == texts.MAIN_MENU_BALANCE)
async def balance(message: Message, session):
    from bot.config import settings
    user = await get_or_create_user(session, message.from_user.id)

    if user.tier == "free" and not settings.ALLOW_FREE:
        await message.answer(badge(texts.FREE_DISABLED), reply_markup=plans_button())
        return

    tier_name = TIER_NAMES_FA.get(user.tier, "آزاد")

    balance_credits = user.token_balance or 0
    model = user.image_model or default_model()
    std_count = images_per_quality(balance_credits, model).get("low", 0)
    text = texts.QUOTA_REMAINING_TOKENS.format(
        tier=tier_name,
        model=model,
        balance=f"{balance_credits:,}",
        standard_count=f"{std_count:,}",
    )

    if not await can_generate(session, user):
        text += "\n\n💎 برای ساخت تصاویر بیشتر، اشتراک تهیه کنید 👇"
        await message.answer(badge(text), reply_markup=plans_button())
    else:
        await message.answer(badge(text), reply_markup=main_menu(user))
