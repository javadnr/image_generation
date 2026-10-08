import logging
from datetime import datetime

import jdatetime
from aiogram import Bot
from aiogram.types import BufferedInputFile
from bot.config import settings

logger = logging.getLogger(__name__)

TIER_PRICES = {
    "bronze": settings.BRONZE_PRICE,
    "silver": settings.SILVER_PRICE,
    "gold": settings.GOLD_PRICE,
}


def format_jalali(dt: datetime | None) -> str:
    if not dt:
        return "—"
    try:
        return jdatetime.datetime.fromgregorian(datetime=dt).strftime("%Y/%m/%d ساعت %H:%M")
    except Exception:
        return dt.strftime("%Y/%m/%d %H:%M")


async def send_premium_report(
    bot: Bot,
    user_id: int,
    tier: str,
    username: str | None = None,
    payment_id: str | None = None,
    amount: int | None = None,
    expire_dt: datetime | None = None,
    paid_at: datetime | None = None,
) -> None:
    channel_id = settings.PAYMENT_REPORT_CHANNEL_ID or settings.REPORT_CHANNEL_ID
    if not channel_id:
        return
    if amount is None:
        amount = TIER_PRICES.get(tier, 0)
    username_display = f"@{username}" if username else "—"
    try:
        await bot.send_message(
            channel_id,
            "💰 گزارش خرید جدید\n"
            "─────────────────\n"
            f"👤 شناسه کاربر: {user_id}\n"
            f"📛 نام کاربری: {username_display}\n"
            f"📋 پلن خریداری شده: {tier}\n"
            f"🔢 شناسه پرداخت: {payment_id or '—'}\n"
            f"💵 مبلغ: {amount:,} Toman\n"
            "✅ وضعیت: completed\n"
            f"📅 تاریخ انقضا: {format_jalali(expire_dt)}\n"
            f"⏰ زمان تأیید: {format_jalali(paid_at)}",
        )
    except Exception:
        logger.exception("Failed to send premium report user=%d plan=%s", user_id, tier)


async def send_error_report(
    bot: Bot,
    *,
    user_id: int,
    username: str | None = None,
    tier: str = "—",
    model: str = "—",
    operation: str = "generate",
    prompt: str = "",
    error: str = "",
    size: str = "",
) -> None:
    """DM a detailed failure report to all admins. Never raises."""
    if not settings.ADMIN_IDS:
        return
    username_display = f"@{username}" if username else "—"
    text = (
        "❌ گزارش خطای تولید تصویر\n"
        "─────────────────\n"
        f"👤 شناسه کاربر: {user_id}\n"
        f"📛 نام کاربری: {username_display}\n"
        f"📦 پلن: {tier}\n"
        f"🤖 مدل: {model}\n"
        f"⚙️ عملیات: {operation}\n"
        f"🖼 ابعاد: {size or '—'}\n"
        f"📝 پرامپت: {prompt[:300] or '—'}\n"
        f"⚠️ خطا: {error[:500] or '—'}\n"
        f"⏰ زمان: {format_jalali(datetime.now())}"
    )
    for admin_id in settings.ADMIN_IDS:
        try:
            await bot.send_message(admin_id, text)
        except Exception:
            logger.exception("Failed to send error report to admin=%d", admin_id)


OPERATION_FA = {
    "generate": "ساخت تصویر",
    "edit": "ویرایش (ریپلای)",
    "photo_edit": "ویرایش (عکس+کپشن)",
}


async def send_processed_report(
    bot: Bot,
    *,
    user_id: int,
    operation: str,
    prompt: str,
    tokens: int | None,
    image_bytes: bytes,
    original_bytes: bytes | None = None,
) -> None:
    """Send processed request (prompt, tokens, user, pictures) to the channel. Never raises."""
    channel_id = settings.PROCESSED_REQUESTS_CHANNEL_ID
    if not channel_id:
        return
    caption = (
        "🖼 درخواست پردازش‌شده\n"
        "─────────────────\n"
        f"👤 شناسه کاربر: {user_id}\n"
        f"⚙️ عملیات: {OPERATION_FA.get(operation, operation)}\n"
        f"📝 پرامپت: {prompt[:400] or '—'}\n"
        f"🔢 توکن مصرفی: {tokens if tokens is not None else '—'}"
    )
    try:
        if settings.API_SERVER == "bale":
            from bot.utils.bale_upload import send_photo_bytes_raw
            await send_photo_bytes_raw(
                token=settings.BOT_TOKEN,
                chat_id=channel_id,
                image_bytes=image_bytes,
                caption=caption,
            )
            if original_bytes:
                await send_photo_bytes_raw(
                    token=settings.BOT_TOKEN,
                    chat_id=channel_id,
                    image_bytes=original_bytes,
                    caption=f"🖼 تصویر اصلی (کاربر {user_id})",
                )
        else:
            await bot.send_photo(
                channel_id,
                photo=BufferedInputFile(image_bytes, filename="result.png"),
                caption=caption,
            )
            if original_bytes:
                await bot.send_photo(
                    channel_id,
                    photo=BufferedInputFile(original_bytes, filename="original.png"),
                    caption=f"🖼 تصویر اصلی (کاربر {user_id})",
                )
    except Exception:
        logger.exception("Failed to send processed report user=%d", user_id)
