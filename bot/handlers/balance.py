from aiogram import Router, F
from aiogram.types import Message
from bot.services.user import get_or_create_user, can_generate
from bot.services.models import default_model, images_per_quality, edits_available
from bot.services.user import get_edit_cost
from bot.keyboards.reply import main_menu
from bot.keyboards.inline import plans_button
from bot.texts import badge
import bot.texts as texts

router = Router()

TIER_NAMES_FA = {"free": "آزاد", "bronze": "برنزی", "silver": "نقره‌ای", "gold": "طلایی", "diamond": "الماسی"}


@router.message(F.text == texts.MAIN_MENU_BALANCE)
async def balance(message: Message, session):
    user = await get_or_create_user(session, message.from_user.id)
    tier_name = TIER_NAMES_FA.get(user.tier, "آزاد")

    balance_credits = user.token_balance or 0
    model = user.image_model or default_model()
    lines = [
        f"• {texts.QUALITY_LABELS[q]}: {count:,} تصویر"
        for q, count in images_per_quality(balance_credits, model).items()
    ]
    lines.append(
        f"• ویرایش عکس: {edits_available(balance_credits, get_edit_cost()):,} تصویر"
    )
    text = texts.QUOTA_REMAINING_TOKENS.format(
        tier=tier_name,
        model=model,
        balance=f"{balance_credits:,}",
        breakdown="\n".join(lines),
    )

    if not await can_generate(session, user):
        text += "\n\n💎 برای ساخت تصاویر بیشتر، اشتراک تهیه کنید 👇"
        await message.answer(badge(text), reply_markup=plans_button())
    else:
        await message.answer(badge(text), reply_markup=main_menu(user))
