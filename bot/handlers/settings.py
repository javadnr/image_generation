import asyncio
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from bot.services.user import get_or_create_user, set_resolution, toggle_optimize
from bot.keyboards.inline import settings_menu, resolution_picker
import bot.texts as texts

router = Router()

WAITING_RESOLUTION: set[int] = set()

VALID_SIZES = list(range(64, 2049, 64))
RATIO_LIMIT = 16 / 9


def validate_resolution(w: int, h: int) -> bool:
    if w not in VALID_SIZES or h not in VALID_SIZES:
        return False
    ratio = max(w, h) / min(w, h)
    return ratio <= RATIO_LIMIT


@router.callback_query(F.data == "settings")
async def settings_handler(callback: CallbackQuery, session):
    user = await get_or_create_user(session, callback.from_user.id)
    optimize_status = texts.SETTINGS_OPTIMIZE_ON if user.optimize_prompt else texts.SETTINGS_OPTIMIZE_OFF
    text = (
        f"{texts.SETTINGS_TITLE}\n\n"
        f"{texts.SETTINGS_RESOLUTION.format(width=user.image_width, height=user.image_height)}\n"
        f"{texts.SETTINGS_OPTIMIZE.format(status=optimize_status)}"
    )
    await callback.message.edit_text(text, reply_markup=settings_menu(user))
    await callback.answer()


@router.callback_query(F.data == "resolution_picker")
async def resolution_picker_handler(callback: CallbackQuery, session):
    user = await get_or_create_user(session, callback.from_user.id)
    await callback.message.edit_text(
        texts.RESOLUTION_TITLE,
        reply_markup=resolution_picker(user.image_width, user.image_height),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("set_res_"))
async def set_resolution_handler(callback: CallbackQuery, session):
    parts = callback.data.split("_")
    width, height = int(parts[2]), int(parts[3])
    user = await get_or_create_user(session, callback.from_user.id)
    await set_resolution(session, user, width, height)
    await callback.message.edit_text(
        texts.RESOLUTION_SET.format(width=width, height=height),
        reply_markup=resolution_picker(width, height),
    )
    await callback.answer()


@router.callback_query(F.data == "custom_resolution")
async def custom_resolution_handler(callback: CallbackQuery, session):
    user = await get_or_create_user(session, callback.from_user.id)
    WAITING_RESOLUTION.add(user.telegram_id)
    await callback.message.edit_text(texts.RESOLUTION_CUSTOM_PROMPT)
    await callback.answer()


@router.message(F.text, ~F.text.startswith("/"), ~F.reply_to_message)
async def handle_custom_resolution(message: Message, session):
    user = await get_or_create_user(session, message.from_user.id)
    if user.telegram_id not in WAITING_RESOLUTION:
        return

    WAITING_RESOLUTION.discard(user.telegram_id)

    text = message.text.replace("×", "x").replace("*", "x").replace("X", "x").replace(" ", "")
    try:
        w_str, h_str = text.split("x")
        w, h = int(w_str), int(h_str)
    except (ValueError, IndexError):
        await message.answer(texts.RESOLUTION_INVALID)
        return

    if not validate_resolution(w, h):
        await message.answer(texts.RESOLUTION_INVALID)
        return

    await set_resolution(session, user, w, h)
    await message.answer(
        texts.RESOLUTION_SET.format(width=w, height=h),
        reply_markup=resolution_picker(w, h),
    )


@router.callback_query(F.data == "toggle_optimize")
async def toggle_optimize_handler(callback: CallbackQuery, session):
    user = await get_or_create_user(session, callback.from_user.id)
    await toggle_optimize(session, user)
    optimize_status = texts.SETTINGS_OPTIMIZE_ON if user.optimize_prompt else texts.SETTINGS_OPTIMIZE_OFF
    text = (
        f"{texts.SETTINGS_TITLE}\n\n"
        f"{texts.SETTINGS_RESOLUTION.format(width=user.image_width, height=user.image_height)}\n"
        f"{texts.SETTINGS_OPTIMIZE.format(status=optimize_status)}"
    )
    await callback.message.edit_text(text, reply_markup=settings_menu(user))
    await callback.answer()
