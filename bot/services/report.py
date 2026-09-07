from aiogram import Bot
from bot.config import settings

TIER_PRICES = {
    "bronze": settings.BRONZE_PRICE,
    "silver": settings.SILVER_PRICE,
    "gold": settings.GOLD_PRICE,
}


async def send_premium_report(bot: Bot, user_id: int, tier: str) -> None:
    if not settings.REPORT_CHANNEL_ID:
        return
    price = TIER_PRICES.get(tier, 0)
    await bot.send_message(
        settings.REPORT_CHANNEL_ID,
        f"💎 اکانت پریمیوم فعال شد\n"
        f"👤 کاربر: {user_id}\n"
        f"📦 پلن: {tier}\n"
        f"💰 قیمت: {price:,} تومان",
    )
