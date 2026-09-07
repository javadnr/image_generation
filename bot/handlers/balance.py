from aiogram import Router, F
from aiogram.types import Message
from bot.services.user import get_or_create_user, check_and_reset_daily, get_remaining
from bot.keyboards.reply import main_menu
import bot.texts as texts
from bot.services.user import TIER_LIMITS

router = Router()


@router.message(F.text == texts.MAIN_MENU_BALANCE)
async def balance(message: Message, session):
    user = await get_or_create_user(session, message.from_user.id)
    user = await check_and_reset_daily(session, user)
    remaining = await get_remaining(session, user)
    total = TIER_LIMITS.get(user.tier, 2)
    tier_name = {"free": "آزاد", "bronze": "برنزی", "silver": "نقره‌ای", "gold": "طلایی"}.get(user.tier, "آزاد")
    await message.answer(
        f"📊 موجودی شما\n\n"
        f"📦 پلن: {tier_name}\n"
        f"🖼 باقی‌مانده: {remaining} از {total} تصویر در روز",
        reply_markup=main_menu(message.from_user.id),
    )
