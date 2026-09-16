import os
import logging
import tempfile
from aiogram import Router, F
from aiogram.types import Message, BufferedInputFile
from bot.config import settings
from bot.services.user import get_or_create_user, check_and_reset_daily, can_generate, consume_quota, set_generating, get_image_by_message, save_image, check_max_limit
from bot.services.queue import acquire_queue, release_queue
from bot.services.image import edit_image
from bot.keyboards.reply import main_menu
from bot.texts import badge
import bot.texts as texts

router = Router()

IMAGES_DIR = "images"


@router.message(F.text, F.reply_to_message)
async def handle_edit(message: Message, session):
    user = await get_or_create_user(session, message.from_user.id)
    user = await check_and_reset_daily(session, user)

    if await check_max_limit(session, user):
        await message.answer(badge(texts.QUOTA_EXCEEDED_MAX))
        return

    reply_msg = message.reply_to_message
    if not reply_msg.photo:
        return

    if reply_msg.from_user.id != message.bot.id:
        await message.answer(badge(texts.EDIT_NOT_OWN))
        return

    img = await get_image_by_message(session, user, reply_msg.message_id)
    if not img:
        await message.answer(badge(texts.EDIT_NOT_SAVED))
        return

    if not os.path.exists(img.file_path):
        await message.answer(badge(texts.EDIT_FILE_MISSING))
        return

    if not await can_generate(session, user):
        await message.answer(badge(texts.QUOTA_EXCEEDED))
        return

    if user.is_generating:
        await message.answer(badge("⏳ لطفاً صبر کنید. تصویر قبلی در حال ساخت است."))
        return

    if not await acquire_queue(user.tier, user.telegram_id):
        await message.answer(badge("⏳ صف پر است. لطفاً صبر کنید..."))
        return

    try:
        await set_generating(session, user, True)
        gen_msg = await message.answer(badge("درحال ساخت...."))

        width = user.image_width if user.tier != "free" else 1024
        height = user.image_height if user.tier != "free" else 1024

        image_bytes = await edit_image(img.file_path, message.text, user.tier, width, height)

        await gen_msg.delete()

        user_dir = os.path.join(IMAGES_DIR, str(user.telegram_id))
        os.makedirs(user_dir, exist_ok=True)

        file_path = os.path.join(user_dir, f"edit_{message.message_id}.png")
        with open(file_path, "wb") as f:
            f.write(image_bytes)

        if settings.API_SERVER == "bale":
            from bot.utils.bale_upload import send_photo_bytes_raw
            result = await send_photo_bytes_raw(
                token=settings.BOT_TOKEN,
                chat_id=message.chat.id,
                image_bytes=image_bytes,
                caption=f"✅ {message.text[:100]}",
            )
            sent_msg_id = result.get("result", {}).get("message_id", 0)
        else:
            photo = BufferedInputFile(image_bytes, filename="image.png")
            sent_msg = await message.answer_photo(
                photo=photo,
                caption=f"✅ {message.text[:100]}",
            )
            sent_msg_id = sent_msg.message_id

        await consume_quota(session, user)
        await save_image(session, user, sent_msg_id, file_path, message.text)

    except Exception as e:
        logging.error("Image edit failed: %s", e, exc_info=True)
        error_text = str(e)
        if "rate" in error_text.lower():
            error_msg = texts.ERROR_WAIT
        elif "moderation" in error_text.lower():
            error_msg = texts.ERROR_MODERATION
        else:
            error_msg = texts.ERROR_GENERIC
        try:
            await gen_msg.edit_text(badge(error_msg))
        except Exception:
            await message.answer(badge(error_msg))
    finally:
        await set_generating(session, user, False)
        release_queue(user.tier, user.telegram_id)


@router.message(F.photo, F.caption)
async def handle_photo_edit(message: Message, session, bot):
    user = await get_or_create_user(session, message.from_user.id)
    user = await check_and_reset_daily(session, user)

    if await check_max_limit(session, user):
        await message.answer(badge(texts.QUOTA_EXCEEDED_MAX))
        return

    prompt = message.caption
    if not prompt or not prompt.strip():
        return

    if not await can_generate(session, user):
        await message.answer(badge(texts.QUOTA_EXCEEDED))
        return

    if user.is_generating:
        await message.answer(badge("⏳ لطفاً صبر کنید. تصویر قبلی در حال ساخت است."))
        return

    if not await acquire_queue(user.tier, user.telegram_id):
        await message.answer(badge("⏳ صف پر است. لطفاً صبر کنید..."))
        return

    try:
        await set_generating(session, user, True)
        gen_msg = await message.answer(badge("درحال ویرایش تصویر...."))

        photo = message.photo[-1]
        file = await bot.get_file(photo.file_id)
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
        await bot.download_file(file.file_path, tmp.name)

        width = user.image_width if user.tier != "free" else 1024
        height = user.image_height if user.tier != "free" else 1024

        image_bytes = await edit_image(tmp.name, prompt, user.tier, width, height)

        os.unlink(tmp.name)
        await gen_msg.delete()

        user_dir = os.path.join(IMAGES_DIR, str(user.telegram_id))
        os.makedirs(user_dir, exist_ok=True)

        file_path = os.path.join(user_dir, f"edit_{message.message_id}.png")
        with open(file_path, "wb") as f:
            f.write(image_bytes)

        if settings.API_SERVER == "bale":
            from bot.utils.bale_upload import send_photo_bytes_raw
            result = await send_photo_bytes_raw(
                token=settings.BOT_TOKEN,
                chat_id=message.chat.id,
                image_bytes=image_bytes,
                caption=f"✅ {prompt[:100]}",
            )
            sent_msg_id = result.get("result", {}).get("message_id", 0)
        else:
            photo = BufferedInputFile(image_bytes, filename="image.png")
            sent_msg = await message.answer_photo(
                photo=photo,
                caption=f"✅ {prompt[:100]}",
            )
            sent_msg_id = sent_msg.message_id

        await consume_quota(session, user)
        await save_image(session, user, sent_msg_id, file_path, prompt)

    except Exception as e:
        logging.error("Photo edit failed: %s", e, exc_info=True)
        error_text = str(e)
        if "rate" in error_text.lower():
            error_msg = texts.ERROR_WAIT
        elif "moderation" in error_text.lower():
            error_msg = texts.ERROR_MODERATION
        else:
            error_msg = texts.ERROR_GENERIC
        try:
            await gen_msg.edit_text(badge(error_msg))
        except Exception:
            await message.answer(badge(error_msg))
    finally:
        await set_generating(session, user, False)
        release_queue(user.tier, user.telegram_id)
