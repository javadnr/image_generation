import logging
from datetime import datetime

import jdatetime
from aiogram import Bot
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
