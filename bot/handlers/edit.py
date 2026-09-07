import os
from aiogram import Router, F
from aiogram.types import Message
from bot.services.user import get_or_create_user, check_and_reset_daily, can_generate, consume_quota, set_generating, get_image_by_message, save_image
from bot.services.queue import acquire_queue, release_queue
from bot.services.image import edit_image
from bot.keyboards.reply import main_menu
import bot.texts as texts

router = Router()

IMAGES_DIR = "images"


@router.message(F.text, F.reply_to_message)
async def handle_edit(message: Message, session):
    user = await get_or_create_user(session, message.from_user.id)
    user = await check_and_reset_daily(session, user)

    reply_msg = message.reply_to_message
    if not reply_msg.photo:
        return

    if reply_msg.from_user.id != message.bot.id:
        await message.answer(texts.EDIT_NOT_OWN)
        return

    img = await get_image_by_message(session, user, reply_msg.message_id)
    if not img:
        await message.answer(texts.EDIT_NOT_SAVED)
        return

    if not os.path.exists(img.file_path):
        await message.answer(texts.EDIT_FILE_MISSING)
        return

    if not await can_generate(session, user):
        await message.answer(texts.QUOTA_EXCEEDED)
        return

    if user.is_generating:
        await message.answer("⏳ لطفاً صبر کنید. تصویر قبلی در حال ساخت است.")
        return

    if not await acquire_queue(user.tier, user.telegram_id):
        await message.answer("⏳ صف پر است. لطفاً صبر کنید...")
        return

    try:
        await set_generating(session, user, True)
        await message.answer(texts.GENERATING)

        width = user.image_width if user.tier != "free" else 1024
        height = user.image_height if user.tier != "free" else 1024

        image_bytes = await edit_image(img.file_path, message.text, user.tier, width, height)

        user_dir = os.path.join(IMAGES_DIR, str(user.telegram_id))
        os.makedirs(user_dir, exist_ok=True)

        sent_msg = await message.answer_photo(
            photo=image_bytes,
            caption=f"✅ {message.text[:100]}",
        )

        file_path = os.path.join(user_dir, f"{sent_msg.message_id}.png")
        with open(file_path, "wb") as f:
            f.write(image_bytes)

        await consume_quota(session, user)
        await save_image(session, user, sent_msg.message_id, file_path, message.text)

    except Exception as e:
        error_text = str(e)
        if "rate" in error_text.lower():
            await message.answer(texts.ERROR_WAIT)
        elif "moderation" in error_text.lower():
            await message.answer(texts.ERROR_MODERATION)
        else:
            await message.answer(texts.ERROR_GENERIC)
    finally:
        await set_generating(session, user, False)
        release_queue(user.tier, user.telegram_id)
