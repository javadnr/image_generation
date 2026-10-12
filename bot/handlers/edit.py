import logging
import os
import tempfile
from aiogram import Router, F
from aiogram.types import Message, BufferedInputFile
from bot.config import settings
from bot.services.user import get_or_create_user, set_generating, has_edit_balance, deduct_tokens
from bot.services.analytics import (
    log_event, IMAGE_GENERATION_STARTED, IMAGE_GENERATION_SUCCESS, IMAGE_GENERATION_FAILED,
)
from bot.handlers.premium import answer_quota_exceeded
from bot.services.queue import acquire_queue, release_queue
from bot.services.image import edit_image
from bot.services.report import send_error_report, send_processed_report
from bot.services.models import charge_for
from bot.keyboards.inline import premium_menu, plans_button
from bot.texts import badge
import bot.texts as texts

router = Router()


@router.message(F.photo, F.caption)
async def handle_photo_edit(message: Message, session, bot):
    user = await get_or_create_user(session, message.from_user.id)

    if user.tier == "free":
        await message.answer(badge(texts.EDIT_PREMIUM_ONLY), reply_markup=premium_menu(user))
        return

    prompt = message.caption
    if not prompt or not prompt.strip():
        return

    if not has_edit_balance(user):
        await answer_quota_exceeded(message, session, user)
        return

    if user.is_generating:
        await message.answer(badge("⏳ لطفاً صبر کنید. تصویر قبلی در حال ساخت است."))
        return

    if not await acquire_queue(user.tier, user.telegram_id):
        await message.answer(badge("⏳ لطفاً کمی صبر کنید و دوباره تلاش کنید..."))
        return

    await log_event(session, user, IMAGE_GENERATION_STARTED)

    try:
        await set_generating(session, user, True)
        gen_msg = await message.answer(badge("درحال ویرایش تصویر...."))

        photo = message.photo[-1]
        file = await bot.get_file(photo.file_id)
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
        await bot.download_file(file.file_path, tmp.name)

        try:
            image_bytes, tokens = await edit_image(tmp.name, prompt, user.image_model or None)
        finally:
            with open(tmp.name, "rb") as f:
                original_bytes = f.read()
            os.unlink(tmp.name)
        await gen_msg.delete()

        # Caption predicts the post-deduction balance; the actual
        # deduction happens after successful delivery below.
        if tokens is not None:
            charged = charge_for(tokens)
            remaining = max(0, (user.token_balance or 0) - charged)
            caption = (
                f"✅ {(prompt or '')[:60]}\n"
                f"💳 مصرف: {charged:,} اعتبار | "
                f"باقی‌مانده: {remaining:,} اعتبار"
            )
        else:
            caption = f"✅ {prompt[:100]}"

        if settings.API_SERVER == "bale":
            from bot.utils.bale_upload import send_photo_bytes_raw
            await send_photo_bytes_raw(
                token=settings.BOT_TOKEN,
                chat_id=message.chat.id,
                image_bytes=image_bytes,
                caption=caption,
            )
        else:
            photo = BufferedInputFile(image_bytes, filename="image.png")
            await message.answer_photo(
                photo=photo,
                caption=caption,
            )

        await deduct_tokens(session, user, tokens)
        await log_event(session, user, IMAGE_GENERATION_SUCCESS, {"tier": user.tier})
        if (user.token_balance or 0) == 0:
            await message.answer(
                badge(texts.CREDIT_SPENT),
                reply_markup=plans_button(),
            )

        await send_processed_report(
            message.bot,
            user_id=message.from_user.id,
            operation="photo_edit",
            prompt=prompt or "",
            tokens=tokens,
            image_bytes=image_bytes,
            original_bytes=original_bytes,
            remaining=user.token_balance,
        )

    except Exception as e:
        logging.error("Photo edit failed: %s", e, exc_info=True)
        error_text = str(e)
        if "rate" in error_text.lower():
            error_msg = texts.ERROR_WAIT
            error_kind = "rate_limit"
        elif "moderation" in error_text.lower():
            error_msg = texts.ERROR_MODERATION
            error_kind = "moderation"
        else:
            error_msg = texts.ERROR_GENERIC
            error_kind = "generic"
        await log_event(session, user, IMAGE_GENERATION_FAILED, {"error": error_kind})
        await send_error_report(
            message.bot,
            user_id=message.from_user.id,
            username=message.from_user.username,
            tier=user.tier,
            model=user.image_model or "—",
            operation="photo_edit",
            prompt=prompt or "",
            error=f"{type(e).__name__}: {error_text}",
            size="—",
        )
        try:
            await gen_msg.edit_text(badge(error_msg))
        except Exception:
            await message.answer(badge(error_msg))
    finally:
        await set_generating(session, user, False)
        release_queue(user.tier, user.telegram_id)
