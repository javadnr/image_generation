from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from bot.services.user import get_or_create_user, set_quality, VALID_QUALITIES
from bot.services.models import default_model, images_per_quality
from bot.keyboards.inline import quality_keyboard
from bot.texts import badge
import bot.texts as texts

router = Router()


def _current_quality(user) -> str:
    return user.image_quality or "low"


def _estimates_text(user) -> str:
    """Per-quality approximate image counts for the user's current balance."""
    model = user.image_model or default_model()
    per_quality = images_per_quality(user.token_balance or 0, model)
    if not per_quality:
        return ""
    lines = "\n".join(
        f"• {texts.QUALITY_LABELS[q]}: حدود {count:,} تصویر"
        for q, count in per_quality.items()
    )
    return f"\n\n📊 با موجودی فعلی تقریباً می‌تونی بسازی:\n{lines}"


@router.message(F.text == texts.MAIN_MENU_QUALITY)
async def quality_menu(message: Message, session):
    user = await get_or_create_user(session, message.from_user.id)
    await message.answer(
        badge(f"{texts.QUALITY_TITLE}{_estimates_text(user)}"),
        reply_markup=quality_keyboard(user.tier, _current_quality(user)),
    )


@router.callback_query(F.data.startswith("quality:"))
async def quality_set(callback: CallbackQuery, session):
    value = callback.data.split(":", 1)[1]
    if value not in VALID_QUALITIES:
        await callback.answer("⚠️ گزینه نامعتبر.", show_alert=True)
        return

    user = await get_or_create_user(session, callback.from_user.id)
    if user.tier == "free" and value != "low":
        await callback.answer(texts.QUALITY_LOCKED, show_alert=True)
        return

    await set_quality(session, user, value)
    try:
        await callback.message.edit_text(
            badge(f"{texts.QUALITY_TITLE}{_estimates_text(user)}"),
            reply_markup=quality_keyboard(user.tier, value),
        )
    except Exception:
        pass
    await callback.answer(
        texts.QUALITY_SET.format(label=texts.QUALITY_LABELS[value])
    )
