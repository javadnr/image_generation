import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, BufferedInputFile
from bot.config import settings
from bot.services.user import (
    get_or_create_user, can_generate, deduct_tokens, set_generating,
    set_pending_prompt, clear_pending_prompt, claim_pending_prompt,
)
from bot.services.analytics import (
    log_event, maybe_log_first_generation_start,
    IMAGE_GENERATION_STARTED, IMAGE_GENERATION_SUCCESS, IMAGE_GENERATION_FAILED,
    HELP_VIEWED,
)
from bot.handlers.premium import answer_quota_exceeded
from bot.services.queue import acquire_queue, release_queue
from bot.services.image import generate_image
from bot.services.models import (
    default_model, charge_for, images_per_quality,
    DEFAULT_IMAGE_SIZE, image_dimensions, size_label,
)
from bot.services.report import send_error_report, send_processed_report
from bot.keyboards.reply import main_menu
from bot.keyboards.inline import plans_button, confirm_keyboard, size_keyboard
from bot.texts import badge
import bot.texts as texts

router = Router()

MENU_BUTTONS = {
    texts.MAIN_MENU_GENERATE,
    texts.MAIN_MENU_BALANCE,
    texts.MAIN_MENU_PREMIUM,
    texts.MAIN_MENU_QUALITY,
    texts.MAIN_MENU_MODEL,
    texts.MAIN_MENU_ADMIN,
}


@router.message(F.text == texts.MAIN_MENU_GENERATE)
async def generate_prompt(message: Message, session):
    user = await get_or_create_user(session, message.from_user.id)
    await log_event(session, user, HELP_VIEWED)
    await message.answer(badge(
        "🎨 ساخت تصویر\n\n"
        "ایده یا چیزی که می‌خوای ببینی رو به زبان طبیعی برام بنویس تا برات به تصویر تبدیلش کنم ✨\n\n"
        "مثلاً:\n"
        "«یک شهر آینده‌نگر در شب، باران، نورهای نئون، سبک سینمایی و واقع‌گرایانه»\n\n"
        "💡 هرچه توضیحت دقیق‌تر باشه، نتیجه به چیزی که می‌خوای نزدیک‌تر می‌شه.\n\n"
        "📷 ویرایش عکس (مخصوص کاربران پریمیوم 💎):\n"
        "عکست رو بفرست و توی کپشن بنویس چه تغییری می‌خوای؛ مثلاً «پس‌زمینه رو ساحل کن»."
    ))


@router.message(F.text, ~F.text.startswith("/"), ~F.reply_to_message)
async def handle_generate(message: Message, session):
    if message.text in MENU_BUTTONS:
        return

    user = await get_or_create_user(session, message.from_user.id)

    if user.is_generating:
        await message.answer(badge(texts.CONFIRM_BUSY))
        return

    if not await can_generate(session, user):
        await answer_quota_exceeded(message, session, user)
        return

    await set_pending_prompt(session, user, message.text)
    await message.answer(
        badge(texts.SIZE_TITLE),
        reply_markup=size_keyboard(user.image_size or DEFAULT_IMAGE_SIZE, show_back=False),
    )


@router.callback_query(F.data == "confirm_no")
async def confirm_no(callback: CallbackQuery, session):
    await clear_pending_prompt(session, callback.from_user.id)
    try:
        await callback.message.delete()
    except Exception:
        pass
    await callback.answer()


@router.callback_query(F.data == "confirm_yes")
async def confirm_yes(callback: CallbackQuery, session):
    user = await get_or_create_user(session, callback.from_user.id)
    if not await can_generate(session, user):
        await callback.answer()
        await answer_quota_exceeded(callback.message, session, user)
        return

    prompt, status = await claim_pending_prompt(session, callback.from_user.id)
    if status == "busy":
        await callback.answer(texts.CONFIRM_BUSY, show_alert=True)
        return
    if status != "ok" or not prompt:
        await callback.answer()
        try:
            await callback.message.edit_text(badge(texts.CONFIRM_EMPTY))
        except Exception:
            pass
        return

    await callback.answer()
    await session.refresh(user)
    quality = user.image_quality or "low"
    size_key = user.image_size or DEFAULT_IMAGE_SIZE
    try:
        await callback.message.edit_text(
            badge(
                f"{texts.CONFIRM_PROGRESS}\n"
                f"📝 پرامپت: «{prompt[:texts.CONFIRM_PROMPT_MAX]}»\n"
                f"🎨 کیفیت: {texts.QUALITY_LABELS.get(quality, quality)}\n"
                f"📐 اندازه: {size_label(size_key)}\n"
                f"{texts.GENERATE_SETTINGS_NOTE.format(button=texts.MAIN_MENU_QUALITY)}"
            )
        )
    except Exception:
        pass

    if not await acquire_queue(user.tier, user.telegram_id):
        user.pending_prompt = prompt
        user.is_generating = False
        await session.commit()
        await callback.message.answer(badge("⏳ لطفاً کمی صبر کنید و دوباره تلاش کنید..."))
        return

    await maybe_log_first_generation_start(session, user)
    await log_event(session, user, IMAGE_GENERATION_STARTED)
    await _run_generation(
        callback.message, session, user, prompt,
        callback.from_user, callback.bot, callback.message,
    )


async def _run_generation(message, session, user, prompt_text, tg_user, bot, gen_msg):
    width, height = 1024, 1024
    try:
        width, height = image_dimensions(user.image_size or DEFAULT_IMAGE_SIZE)
        logging.info("User %d tier=%s generating %dx%d", user.telegram_id, user.tier, width, height)

        image_bytes, tokens = await generate_image(
            prompt_text, user.tier, width, height,
            quality=user.image_quality or "low",
            model=user.image_model or None,
        )
        logging.info("Image received: %d bytes", len(image_bytes))

        await gen_msg.delete()

        model_id = user.image_model or default_model()
        quality = user.image_quality or "low"
        credit_line = None
        if tokens is not None:
            charged = charge_for(tokens)
            remaining = max(0, (user.token_balance or 0) - charged)
            credit_line = (
                f"💳 مصرف: {charged:,} اعتبار | "
                f"باقی‌مانده: {remaining:,} اعتبار"
            )
        if credit_line:
            caption = f"✅ {(prompt_text or '')[:60]}\n{credit_line}"
        else:
            caption = f"✅ {prompt_text[:100]}"

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
        left = images_per_quality(user.token_balance or 0, model_id).get(quality)
        if left == 0:
            await message.answer(
                badge(texts.CREDIT_SPENT),
                reply_markup=plans_button(),
            )
        elif left == 1:
            await message.answer(
                badge(texts.CREDIT_LOW),
                reply_markup=plans_button(),
            )
        await send_processed_report(
            bot,
            user_id=tg_user.id,
            operation="generate",
            prompt=prompt_text or "",
            tokens=tokens,
            image_bytes=image_bytes,
            remaining=user.token_balance,
        )

    except Exception as e:
        logging.error("Image generation failed: %s", e, exc_info=True)
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
            bot,
            user_id=tg_user.id,
            username=tg_user.username,
            tier=user.tier,
            model=user.image_model or "—",
            operation="generate",
            prompt=prompt_text or "",
            error=f"{type(e).__name__}: {error_text}",
            size=f"{width}x{height}",
        )
        try:
            await gen_msg.edit_text(badge(error_msg))
        except Exception:
            await message.answer(badge(error_msg))
    finally:
        await set_generating(session, user, False)
        release_queue(user.tier, user.telegram_id)
