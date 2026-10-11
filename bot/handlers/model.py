from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from bot.services.user import get_or_create_user, set_model
from bot.services.models import model_ids, is_free_model, default_model
from bot.keyboards.inline import model_keyboard
from bot.texts import badge
import bot.texts as texts

router = Router()


def _current_model(user) -> str:
    return user.image_model or default_model()


@router.message(F.text == texts.MAIN_MENU_MODEL)
async def model_menu(message: Message, session):
    user = await get_or_create_user(session, message.from_user.id)
    await message.answer(
        badge(f"{texts.MODEL_TITLE}\n\n{texts.MODEL_HELP}"),
        reply_markup=model_keyboard(user.tier, _current_model(user)),
    )


@router.callback_query(F.data.startswith("model:"))
async def model_set(callback: CallbackQuery, session):
    value = callback.data.split(":", 1)[1]
    if value not in model_ids():
        await callback.answer("⚠️ گزینه نامعتبر.", show_alert=True)
        return

    user = await get_or_create_user(session, callback.from_user.id)
    if user.tier == "free" and not is_free_model(value):
        await callback.answer(texts.MODEL_LOCKED, show_alert=True)
        return

    await set_model(session, user, value)
    try:
        await callback.message.edit_reply_markup(
            reply_markup=model_keyboard(user.tier, value)
        )
    except Exception:
        pass
    await callback.answer(
        texts.MODEL_SET.format(label=value)
    )
