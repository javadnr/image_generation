from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton
from bot.services.user import get_or_create_user, set_resolution, toggle_optimize
from bot.keyboards.inline import settings_menu, resolution_picker
from bot.keyboards.reply import main_menu
from bot.texts import badge
import bot.texts as texts

router = Router()

VALID_SIZES = list(range(64, 2049, 64))
RATIO_LIMIT = 16 / 9

CANCEL_KB = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text=texts.RESOLUTION_CANCEL)]], resize_keyboard=True)


class ResolutionState(StatesGroup):
    waiting = State()


def validate_resolution(w: int, h: int) -> bool:
    if w not in VALID_SIZES or h not in VALID_SIZES:
        return False
    ratio = max(w, h) / min(w, h)
    return ratio <= RATIO_LIMIT


@router.callback_query(F.data == "settings")
async def settings_handler(callback: CallbackQuery, session):
    user = await get_or_create_user(session, callback.from_user.id)
    optimize_status = texts.SETTINGS_OPTIMIZE_ON if user.optimize_prompt else texts.SETTINGS_OPTIMIZE_OFF
    text = badge(
        f"{texts.SETTINGS_TITLE}\n\n"
        f"{texts.SETTINGS_RESOLUTION.format(width=user.image_width, height=user.image_height)}\n"
        f"{texts.SETTINGS_OPTIMIZE.format(status=optimize_status)}"
    )
    await callback.message.edit_text(text, reply_markup=settings_menu(user))
    await callback.answer()


@router.message(F.text == texts.MAIN_MENU_SETTINGS)
async def settings_main_menu(message: Message, session, state: FSMContext):
    if await state.get_state() == ResolutionState.waiting:
        return
    user = await get_or_create_user(session, message.from_user.id)
    optimize_status = texts.SETTINGS_OPTIMIZE_ON if user.optimize_prompt else texts.SETTINGS_OPTIMIZE_OFF
    text = badge(
        f"{texts.SETTINGS_TITLE}\n\n"
        f"{texts.SETTINGS_RESOLUTION.format(width=user.image_width, height=user.image_height)}\n"
        f"{texts.SETTINGS_OPTIMIZE.format(status=optimize_status)}"
    )
    await message.answer(text, reply_markup=settings_menu(user))


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
        badge(texts.RESOLUTION_SET.format(width=width, height=height)),
        reply_markup=resolution_picker(width, height),
    )
    await callback.answer()


@router.callback_query(F.data == "custom_resolution")
async def custom_resolution_handler(callback: CallbackQuery, session, state: FSMContext):
    user = await get_or_create_user(session, callback.from_user.id)
    await state.set_state(ResolutionState.waiting)
    await callback.message.delete()
    await callback.message.answer(badge(texts.RESOLUTION_CUSTOM_PROMPT), reply_markup=CANCEL_KB)
    await callback.answer()


@router.message(F.text == texts.RESOLUTION_CANCEL, ResolutionState.waiting)
async def cancel_resolution(message: Message, session, state: FSMContext):
    await state.clear()
    user = await get_or_create_user(session, message.from_user.id)
    await message.answer(badge("❌ لغو شد."), reply_markup=main_menu(user))


@router.message(F.text, ~F.text.startswith("/"), ~F.reply_to_message, ResolutionState.waiting)
async def handle_custom_resolution(message: Message, session, state: FSMContext):
    user = await get_or_create_user(session, message.from_user.id)

    text = message.text.replace("×", "x").replace("*", "x").replace("X", "x").replace(" ", "")
    try:
        w_str, h_str = text.split("x")
        w, h = int(w_str), int(h_str)
    except (ValueError, IndexError):
        await message.answer(badge(texts.RESOLUTION_INVALID), reply_markup=CANCEL_KB)
        return

    if not validate_resolution(w, h):
        await message.answer(badge(texts.RESOLUTION_INVALID), reply_markup=CANCEL_KB)
        return

    await state.clear()
    await set_resolution(session, user, w, h)
    await message.answer(
        badge(texts.RESOLUTION_SET.format(width=w, height=h)),
        reply_markup=main_menu(user),
    )


@router.callback_query(F.data == "toggle_optimize")
async def toggle_optimize_handler(callback: CallbackQuery, session):
    user = await get_or_create_user(session, callback.from_user.id)
    await toggle_optimize(session, user)
    optimize_status = texts.SETTINGS_OPTIMIZE_ON if user.optimize_prompt else texts.SETTINGS_OPTIMIZE_OFF
    text = badge(
        f"{texts.SETTINGS_TITLE}\n\n"
        f"{texts.SETTINGS_RESOLUTION.format(width=user.image_width, height=user.image_height)}\n"
        f"{texts.SETTINGS_OPTIMIZE.format(status=optimize_status)}"
    )
    await callback.message.edit_text(text, reply_markup=settings_menu(user))
    await callback.answer()
