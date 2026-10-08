from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from bot.config import settings
from bot.services.user import get_tier_limit
from bot.services.report import TIER_PRICES
import bot.texts as texts


def to_persian_digits(n: int) -> str:
    persian = "۰۱۲۳۴۵۶۷۸۹"
    return "".join(persian[int(d)] for d in str(n))


def force_join() -> InlineKeyboardMarkup:
    buttons = []
    for channel_link in settings.REQUIRED_CHANNELS.values():
        channel_name = channel_link.split("/")[-1]
        buttons.append([InlineKeyboardButton(
            text=f"📢 @{channel_name}",
            url=channel_link,
        )])
    buttons.append([InlineKeyboardButton(
        text=texts.FORCE_JOIN_VERIFY,
        callback_data="verify_join",
    )])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def premium_menu(user) -> InlineKeyboardMarkup:
    buttons = []
    if user.tier == "free":
        tier_tags = {"bronze": "", "silver": "⭐ محبوب‌ترین", "gold": "🔥 بیشترین اعتبار"}
        for tier, emoji in [("bronze", "🥉"), ("silver", "🥈"), ("gold", "🥇")]:
            price = TIER_PRICES.get(tier, 0)
            tag = tier_tags[tier]
            buttons.append([InlineKeyboardButton(
                text=f"{emoji} {texts.TIER_NAMES_FA[tier]} — {to_persian_digits(price // 1000)} هزار تومان {tag}",
                callback_data=f"buy_{tier}",
            )])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def plans_button() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💎 مشاهده پلن‌ها", callback_data="show_plans")],
    ])


def admin_status(bot_enabled: bool) -> InlineKeyboardMarkup:
    toggle_text = "🔴 غیرفعال کردن ربات" if bot_enabled else "🟢 فعال کردن ربات"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=toggle_text, callback_data="toggle_bot")],
        [InlineKeyboardButton(text="🔄 ریست روزانه همه", callback_data="reset_daily")],
    ])
