from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from bot.services.user import get_or_create_user, check_and_reset_daily
from bot.keyboards.reply import main_menu
from bot.keyboards.inline import force_join
import bot.texts as texts
from bot.config import settings

router = Router()


@router.message(F.text == "/start")
async def cmd_start(message: Message, session):
    user = await get_or_create_user(session, message.from_user.id)
    await check_and_reset_daily(session, user)

    if settings.REQUIRED_CHANNELS and message.from_user.id not in settings.ADMIN_IDS:
        bot = message.bot
        for channel_id in settings.REQUIRED_CHANNELS:
            try:
                member = await bot.get_chat_member(chat_id=channel_id, user_id=message.from_user.id)
                if member.status in ("left", "kicked"):
                    await message.answer(texts.FORCE_JOIN_TITLE, reply_markup=force_join())
                    return
            except Exception:
                continue

    await message.answer(texts.WELCOME, reply_markup=main_menu(message.from_user.id))


@router.callback_query(F.data == "verify_join")
async def verify_join(callback: CallbackQuery, session):
    user = await get_or_create_user(session, callback.from_user.id)
    bot = callback.bot

    all_joined = True
    for channel_id in settings.REQUIRED_CHANNELS:
        try:
            member = await bot.get_chat_member(chat_id=channel_id, user_id=callback.from_user.id)
            if member.status in ("left", "kicked"):
                all_joined = False
                break
        except Exception:
            continue

    if all_joined:
        await callback.message.edit_text(
            texts.WELCOME,
            reply_markup=main_menu(callback.from_user.id),
        )
    else:
        await callback.answer(texts.FORCE_JOIN_NOT_JOINED, show_alert=True)
