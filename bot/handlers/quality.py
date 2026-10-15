from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from bot.services.user import get_or_create_user, set_quality, set_size, VALID_QUALITIES
from bot.services.models import (
    default_model, images_per_quality, VALID_IMAGE_SIZES,
    size_label, DEFAULT_IMAGE_SIZE,
)
from bot.keyboards.inline import quality_keyboard, size_keyboard, settings_hub_keyboard, confirm_keyboard
from bot.texts import badge
import bot.texts as texts

router = Router()


def _current_quality(user) -> str:
    return user.image_quality or "low"


def _current_size(user) -> str:
    return user.image_size or DEFAULT_IMAGE_SIZE


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


def _quality_menu_text(user) -> str:
    return (
        f"{texts.QUALITY_TITLE}{_estimates_text(user)}\n\n"
        f"کیفیت فعلی: {texts.QUALITY_LABELS.get(_current_quality(user), _current_quality(user))}"
    )


def _size_menu_text(user) -> str:
    return (
        f"{texts.SIZE_TITLE}\n\n"
        f"اندازه فعلی: {size_label(_current_size(user))}"
    )


async def send_confirm(target: Message, prompt: str):
    """Send the generate-confirmation message for the latest pending prompt."""
    await target.answer(
        badge(f"{texts.CONFIRM_ASK}\n\n«{prompt[:texts.CONFIRM_PROMPT_MAX]}»"),
        reply_markup=confirm_keyboard(),
    )


def _settings_summary_text(user) -> str:
    """Full overview: current quality, size, and per-quality estimates."""
    quality = _current_quality(user)
    return (
        f"{texts.SETTINGS_TITLE}\n\n"
        f"🎨 کیفیت انتخابی: {texts.QUALITY_LABELS.get(quality, quality)}\n"
        f"📐 اندازه انتخابی: {size_label(_current_size(user))}"
        f"{_estimates_text(user)}"
    )


@router.message(F.text == texts.MAIN_MENU_QUALITY)
async def quality_menu(message: Message, session):
    user = await get_or_create_user(session, message.from_user.id)
    await message.answer(
        badge(_settings_summary_text(user)),
        reply_markup=settings_hub_keyboard(),
    )


@router.callback_query(F.data == "settings_home")
async def settings_home(callback: CallbackQuery, session):
    user = await get_or_create_user(session, callback.from_user.id)
    await callback.message.edit_text(
        badge(_settings_summary_text(user)),
        reply_markup=settings_hub_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "settings_quality")
async def settings_quality(callback: CallbackQuery, session):
    user = await get_or_create_user(session, callback.from_user.id)
    await callback.message.edit_text(
        badge(_quality_menu_text(user)),
        reply_markup=quality_keyboard(user.tier, _current_quality(user), show_back=True),
    )
    await callback.answer()


@router.callback_query(F.data == "settings_size")
async def settings_size(callback: CallbackQuery, session):
    user = await get_or_create_user(session, callback.from_user.id)
    await callback.message.edit_text(
        badge(_size_menu_text(user)),
        reply_markup=size_keyboard(_current_size(user), show_back=True),
    )
    await callback.answer()


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
            badge(_quality_menu_text(user)),
            reply_markup=quality_keyboard(user.tier, value, show_back=True),
        )
    except Exception:
        pass
    await callback.answer(
        texts.QUALITY_SET.format(label=texts.QUALITY_LABELS[value])
    )


@router.callback_query(F.data.startswith("size:"))
async def size_set(callback: CallbackQuery, session):
    value = callback.data.split(":", 1)[1]
    if value not in VALID_IMAGE_SIZES:
        await callback.answer("⚠️ گزینه نامعتبر.", show_alert=True)
        return

    user = await get_or_create_user(session, callback.from_user.id)
    await set_size(session, user, value)
    try:
        await callback.message.edit_text(
            badge(_size_menu_text(user)),
            reply_markup=size_keyboard(value, show_back=True),
        )
    except Exception:
        pass
    await callback.answer(
        texts.SIZE_SET.format(label=size_label(value))
    )

    if user.pending_prompt and not user.is_generating:
        await send_confirm(callback.message, user.pending_prompt)
