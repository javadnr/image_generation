import logging
import os
import tempfile
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, BufferedInputFile
from bot.config import settings
from bot.services.user import (
    get_or_create_user, set_generating, has_edit_balance, deduct_tokens,
    maybe_deactivate_low_balance,
)
from bot.services.analytics import (
    log_event, IMAGE_GENERATION_STARTED, IMAGE_GENERATION_SUCCESS, IMAGE_GENERATION_FAILED,
)
from bot.handlers.premium import answer_quota_exceeded
from bot.services.queue import acquire_queue, release_queue
from bot.services.image import edit_image
from bot.services.report import send_error_report, send_processed_report
from bot.services.models import charge_for, DEFAULT_IMAGE_SIZE, image_dimensions, size_label
from bot.keyboards.inline import (
    premium_menu, plans_button, confirm_edit_keyboard,
    edit_confirm_size_keyboard, edit_confirm_quality_keyboard,
)
from bot.texts import badge
import bot.texts as texts

router = Router()

# Pending photo edits awaiting user confirmation: {telegram_id: {file_path, caption}}
PENDING_EDITS: dict[int, dict] = {}


def _render_edit_confirm_text(user, caption: str) -> str:
    """Render confirmation text for edit with current size, quality, and caption."""
    quality = user.image_quality or "low"
    size_key = user.image_size or DEFAULT_IMAGE_SIZE
    quality_label = texts.QUALITY_LABELS.get(quality, quality)
    size_label_text = size_label(size_key)
    warning = ""
    if quality != "low":
        warning = f"\n\n{texts.QUALITY_NOT_LOW_WARNING}"
    return (
        f"{texts.CONFIRM_EDIT_TITLE}\n\n"
        f"{texts.CONFIRM_PROMPT_LABEL} «{caption[:texts.CONFIRM_PROMPT_MAX]}»\n\n"
        f"{texts.CONFIRM_SIZE_LABEL} {size_label_text}\n"
        f"{texts.CONFIRM_QUALITY_LABEL} {quality_label}"
        f"{warning}"
    )


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

    # Clean up any existing pending edit for this user.
    if user.telegram_id in PENDING_EDITS:
        old = PENDING_EDITS.pop(user.telegram_id)
        try:
            os.unlink(old["file_path"])
        except Exception:
            pass

    # Download photo to a temp file and store it as a pending edit.
    photo = message.photo[-1]
    file = await bot.get_file(photo.file_id)
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
    await bot.download_file(file.file_path, tmp.name)

    PENDING_EDITS[user.telegram_id] = {
        "file_path": tmp.name,
        "caption": prompt,
    }

    await message.answer(
        badge(_render_edit_confirm_text(user, prompt)),
        reply_markup=confirm_edit_keyboard(),
    )


@router.callback_query(F.data == "confirm_yes_edit")
async def confirm_yes_edit(callback: CallbackQuery, session):
    user = await get_or_create_user(session, callback.from_user.id)

    pending = PENDING_EDITS.get(user.telegram_id)
    if not pending:
        await callback.answer()
        try:
            await callback.message.edit_text(badge(texts.CONFIRM_EMPTY))
        except Exception:
            pass
        return

    if user.tier == "free":
        await callback.answer()
        await answer_quota_exceeded(callback.message, session, user)
        return

    if not has_edit_balance(user):
        await callback.answer()
        await answer_quota_exceeded(callback.message, session, user)
        return

    quality = user.image_quality or "low"
    from bot.services.user import has_edit_quality_balance, edit_quality_min_balance
    if not has_edit_quality_balance(user, quality):
        threshold = edit_quality_min_balance(quality)
        await callback.answer(f"⚠️ برای ویرایش با کیفیت {texts.QUALITY_LABELS.get(quality, quality)} حداقل {threshold:,} اعتبار لازم است.", show_alert=True)
        return

    if user.is_generating:
        await callback.answer(texts.CONFIRM_BUSY, show_alert=True)
        return

    queue_tier = user.tier
    if not await acquire_queue(queue_tier, user.telegram_id):
        await callback.answer()
        await callback.message.answer(badge("⏳ لطفاً کمی صبر کنید و دوباره تلاش کنید..."))
        return

    await callback.answer()

    # Remove the confirmation message (yes/no buttons) before processing.
    try:
        await callback.message.delete()
    except Exception:
        pass

    gen_msg = None
    try:
        await set_generating(session, user, True)

        width, height = image_dimensions(user.image_size or DEFAULT_IMAGE_SIZE)

        gen_msg = await callback.message.answer(badge("در حال ویرایش تصویر...."))

        try:
            image_bytes, tokens = await edit_image(
                pending["file_path"], pending["caption"], user.image_model or None,
                size=f"{width}x{height}",
                quality=user.image_quality or "low",
            )
        finally:
            with open(pending["file_path"], "rb") as f:
                original_bytes = f.read()
            os.unlink(pending["file_path"])
        PENDING_EDITS.pop(user.telegram_id, None)

        await gen_msg.delete()

        if tokens is not None:
            charged = charge_for(tokens)
            remaining = max(0, (user.token_balance or 0) - charged)
            caption = (
                f"✅ {(pending['caption'] or '')[:60]}\n"
                f"💳 مصرف: {charged:,} اعتبار | "
                f"باقی‌مانده: {remaining:,} اعتبار"
            )
        else:
            caption = f"✅ {pending['caption'][:100]}"

        if settings.API_SERVER == "bale":
            from bot.utils.bale_upload import send_photo_bytes_raw
            await send_photo_bytes_raw(
                token=settings.BOT_TOKEN,
                chat_id=callback.message.chat.id,
                image_bytes=image_bytes,
                caption=caption,
            )
        else:
            photo = BufferedInputFile(image_bytes, filename="image.png")
            await callback.message.answer_photo(
                photo=photo,
                caption=caption,
            )

        await deduct_tokens(session, user, tokens)
        await log_event(session, user, IMAGE_GENERATION_SUCCESS, {"tier": user.tier})
        if await maybe_deactivate_low_balance(session, user):
            await callback.message.answer(
                badge(texts.PLAN_DEACTIVATED_LOW_BALANCE),
                reply_markup=plans_button(),
            )
        elif (user.token_balance or 0) == 0:
            await callback.message.answer(
                badge(texts.CREDIT_SPENT),
                reply_markup=plans_button(),
            )

        await send_processed_report(
            callback.bot,
            user_id=callback.from_user.id,
            operation="photo_edit",
            prompt=pending["caption"] or "",
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
            callback.bot,
            user_id=callback.from_user.id,
            username=callback.from_user.username,
            tier=user.tier,
            model=user.image_model or "—",
            operation="photo_edit",
            prompt=pending["caption"] or "",
            error=f"{type(e).__name__}: {error_text}",
            size="—",
        )
        try:
            if gen_msg:
                await gen_msg.edit_text(badge(error_msg))
            else:
                await callback.message.answer(badge(error_msg))
        except Exception:
            await callback.message.answer(badge(error_msg))
    finally:
        await set_generating(session, user, False)
        release_queue(queue_tier, user.telegram_id)


@router.callback_query(F.data == "confirm_no_edit")
async def confirm_no_edit(callback: CallbackQuery, session):
    pending = PENDING_EDITS.pop(callback.from_user.id, None)
    if pending:
        try:
            os.unlink(pending["file_path"])
        except Exception:
            pass
    try:
        await callback.message.delete()
    except Exception:
        pass
    await callback.answer()


@router.callback_query(F.data == "edt_edit_size")
async def edt_edit_size(callback: CallbackQuery, session):
    try:
        user = await get_or_create_user(session, callback.from_user.id)
        await callback.message.edit_text(
            badge("اندازه مورد نظر رو انتخاب کن:"),
            reply_markup=edit_confirm_size_keyboard(user.image_size or DEFAULT_IMAGE_SIZE),
        )
        await callback.answer()
    except Exception as e:
        logging.getLogger(__name__).exception("edt_edit_size failed: %s", e)
        try:
            await callback.answer("⚠️ خطایی رخ داد. لطفاً دوباره تلاش کنید.", show_alert=True)
        except Exception:
            pass


@router.callback_query(F.data == "edt_edit_quality")
async def edt_edit_quality(callback: CallbackQuery, session):
    try:
        user = await get_or_create_user(session, callback.from_user.id)
        await callback.message.edit_text(
            badge("کیفیت مورد نظر رو انتخاب کن:"),
            reply_markup=edit_confirm_quality_keyboard(user.tier, user.image_quality or "low"),
        )
        await callback.answer()
    except Exception as e:
        logging.getLogger(__name__).exception("edt_edit_quality failed: %s", e)
        try:
            await callback.answer("⚠️ خطایی رخ داد. لطفاً دوباره تلاش کنید.", show_alert=True)
        except Exception:
            pass


@router.callback_query(F.data.startswith("edt_confirm_size:"))
async def edt_confirm_size(callback: CallbackQuery, session):
    try:
        value = callback.data.split(":", 1)[1]
        from bot.services.models import VALID_IMAGE_SIZES
        if value not in VALID_IMAGE_SIZES:
            await callback.answer("⚠️ گزینه نامعتبر.", show_alert=True)
            return

        user = await get_or_create_user(session, callback.from_user.id)
        from bot.services.user import set_size
        await set_size(session, user, value)
        user.image_size = value

        pending = PENDING_EDITS.get(user.telegram_id)
        caption = pending["caption"] if pending else ""
        await callback.message.edit_text(
            badge(_render_edit_confirm_text(user, caption)),
            reply_markup=confirm_edit_keyboard(),
        )
        await callback.answer()
    except Exception as e:
        logging.getLogger(__name__).exception("edt_confirm_size failed: %s", e)
        try:
            await callback.answer("⚠️ خطایی رخ داد. لطفاً دوباره تلاش کنید.", show_alert=True)
        except Exception:
            pass


@router.callback_query(F.data.startswith("edt_confirm_quality:"))
async def edt_confirm_quality(callback: CallbackQuery, session):
    try:
        value = callback.data.split(":", 1)[1]
        from bot.services.user import VALID_QUALITIES
        if value not in VALID_QUALITIES:
            await callback.answer("⚠️ گزینه نامعتبر.", show_alert=True)
            return

        user = await get_or_create_user(session, callback.from_user.id)
        if user.tier == "free" and value != "low":
            await callback.answer(texts.QUALITY_LOCKED, show_alert=True)
            return

        from bot.services.user import set_quality, has_edit_quality_balance, edit_quality_min_balance
        if not has_edit_quality_balance(user, value):
            threshold = edit_quality_min_balance(value)
            await callback.answer(f"⚠️ برای ویرایش با کیفیت {texts.QUALITY_LABELS.get(value, value)} حداقل {threshold:,} اعتبار لازم است.", show_alert=True)
            return

        await set_quality(session, user, value)
        user.image_quality = value

        pending = PENDING_EDITS.get(user.telegram_id)
        caption = pending["caption"] if pending else ""
        await callback.message.edit_text(
            badge(_render_edit_confirm_text(user, caption)),
            reply_markup=confirm_edit_keyboard(),
        )
        await callback.answer()
    except Exception as e:
        logging.getLogger(__name__).exception("edt_confirm_quality failed: %s", e)
        try:
            await callback.answer("⚠️ خطایی رخ داد. لطفاً دوباره تلاش کنید.", show_alert=True)
        except Exception:
            pass


@router.callback_query(F.data == "edt_back_to_confirm")
async def edt_back_to_confirm(callback: CallbackQuery, session):
    try:
        user = await get_or_create_user(session, callback.from_user.id)
        pending = PENDING_EDITS.get(user.telegram_id)
        caption = pending["caption"] if pending else ""
        await callback.message.edit_text(
            badge(_render_edit_confirm_text(user, caption)),
            reply_markup=confirm_edit_keyboard(),
        )
        await callback.answer()
    except Exception as e:
        logging.getLogger(__name__).exception("edt_back_to_confirm failed: %s", e)
        try:
            await callback.answer("⚠️ خطایی رخ داد. لطفاً دوباره تلاش کنید.", show_alert=True)
        except Exception:
            pass


@router.message(F.photo, ~F.caption)
async def handle_photo_no_caption(message: Message, session):
    await message.answer(badge(texts.EDIT_NEED_CAPTION))
