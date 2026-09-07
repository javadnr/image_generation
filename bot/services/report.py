from aiogram import Bot
from bot.config import settings

TIER_PRICES = {
    "bronze": settings.BRONZE_PRICE,
    "silver": settings.SILVER_PRICE,
    "gold": settings.GOLD_PRICE,
}


async def send_premium_report(bot: Bot, user_id: int, tier: str) -> None:
    channel_id = settings.PAYMENT_REPORT_CHANNEL_ID or settings.REPORT_CHANNEL_ID
    if not channel_id:
        return
    price = TIER_PRICES.get(tier, 0)
    await bot.send_message(
        channel_id,
        f"💎 اکانت پریمیوم فعال شد\n"
        f"👤 کاربر: {user_id}\n"
        f"📦 پلن: {tier}\n"
        f"💰 قیمت: {price:,} تومان",
    )
