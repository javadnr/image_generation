import os
import logging
from aiogram import Router, F
from aiogram.types import Message, BufferedInputFile
from bot.config import settings
from bot.services.user import get_or_create_user, check_and_reset_daily, can_generate, consume_quota, set_generating, save_image, get_tier_limit, get_remaining, check_max_limit
from bot.services.queue import acquire_queue, release_queue
from bot.services.image import generate_image
from bot.keyboards.reply import main_menu
from bot.texts import badge
import bot.texts as texts

router = Router()

IMAGES_DIR = "images"

MENU_BUTTONS = {
    texts.MAIN_MENU_GENERATE,
    texts.MAIN_MENU_BALANCE,
    texts.MAIN_MENU_PREMIUM,
    texts.MAIN_MENU_SETTINGS,
    texts.MAIN_MENU_ADMIN,
}


@router.message(F.text == texts.MAIN_MENU_GENERATE)
async def generate_prompt(message: Message, session):
    await message.answer(badge(
        "🎨 ساخت تصویر\n\n"
        "ایده یا چیزی که می‌خوای ببینی رو به زبان طبیعی برام بنویس تا برات به تصویر تبدیلش کنم ✨\n\n"
        "مثلاً:\n"
        "«یک شهر آینده‌نگر در شب، باران، نورهای نئون، سبک سینمایی و واقع‌گرایانه»\n\n"
        "💡 هرچه توضیحت دقیق‌تر باشه، نتیجه به چیزی که می‌خوای نزدیک‌تر می‌شه.\n\n"
        "🖼️ ویرایش تصویر:\n"
        "اگر می‌خوای یک تصویر ساخته‌شده قبلی رو ویرایش کنی، روی همون تصویر Reply بزن و تغییر موردنظرت رو بنویس.\n\n"
        "مثلاً:\n"
        "«لباس شخصیت رو قرمز کن و پس‌زمینه رو به یک جنگل تبدیل کن.»\n\n"
        "📷 همچنین می‌تونی یک عکس همراه با کپشن بفرستی تا عکست رو ویرایش کنم."
    ))


@router.message(F.text, ~F.text.startswith("/"), ~F.reply_to_message)
async def handle_generate(message: Message, session):
    if message.text in MENU_BUTTONS:
        return

    user = await get_or_create_user(session, message.from_user.id)
    user = await check_and_reset_daily(session, user)

    if await check_max_limit(session, user):
        await message.answer(badge(texts.QUOTA_EXCEEDED_MAX))
        return

    if user.is_generating:
        await message.answer(badge("⏳ لطفاً صبر کنید. تصویر قبلی در حال ساخت است."))
        return

    if not await can_generate(session, user):
        await message.answer(badge(texts.QUOTA_EXCEEDED))
        return

    if not await acquire_queue(user.tier, user.telegram_id):
        await message.answer(badge("⏳ صف پر است. لطفاً صبر کنید..."))
        return

    try:
        await set_generating(session, user, True)
        gen_msg = await message.answer(badge("درحال ساخت...."))

        width = user.image_width if user.tier != "free" else 1024
        height = user.image_height if user.tier != "free" else 1024
        logging.info("User %d tier=%s generating %dx%d", user.telegram_id, user.tier, width, height)

        image_bytes = await generate_image(message.text, user.tier, width, height)
        logging.info("Image received: %d bytes", len(image_bytes))

        await gen_msg.delete()

        user_dir = os.path.join(IMAGES_DIR, str(user.telegram_id))
        os.makedirs(user_dir, exist_ok=True)

        file_path = os.path.join(user_dir, f"gen_{message.message_id}.png")
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
        logging.error("Image generation failed: %s", e, exc_info=True)
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
