from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from bot.config import settings
from bot.services.models import PLANS, model_ids, model_label, is_free_model
from bot.services.pricing import plan_price_toman
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


def premium_menu(user, discounts: dict | None = None) -> InlineKeyboardMarkup:
    from bot.services.discounts import discount_for
    buttons = []
    if user.tier == "free":
        for tier in PLANS:
            emoji = texts.PLAN_EMOJI[tier]
            tier_tag = texts.PLAN_TAGS.get(tier, "")
            pct = discount_for(tier, discounts)
            price = plan_price_toman(tier, pct)
            tag = f"🔥 {pct}٪ تخفیف {tier_tag}".strip() if pct else tier_tag
            price_text = (
                f"{to_persian_digits(price // 1000)} هزار تومان"
                if price is not None else "قیمت نامشخص"
            )
            buttons.append([InlineKeyboardButton(
                text=f"{emoji} {texts.TIER_NAMES_FA[tier]} — {price_text} {tag}",
                callback_data=f"buy_{tier}",
            )])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def plans_button() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💎 مشاهده پلن‌ها", callback_data="show_plans")],
    ])


QUALITY_OPTIONS = (("low", "پایین"), ("medium", "متوسط"), ("high", "بالا"))


def quality_keyboard(tier: str, current: str, show_back: bool = False) -> InlineKeyboardMarkup:
    buttons = []
    for value, label in QUALITY_OPTIONS:
        if tier == "free" and value != "low":
            text = f"🔒 {label}"
        else:
            tick = "✅ " if value == current else ""
            text = f"{tick}{label}"
        buttons.append([InlineKeyboardButton(text=text, callback_data=f"quality:{value}")])
    if show_back:
        buttons.append([InlineKeyboardButton(text=texts.SETTINGS_BACK, callback_data="settings_home")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def settings_hub_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=texts.SETTINGS_QUALITY_BTN, callback_data="settings_quality")],
        [InlineKeyboardButton(text=texts.SETTINGS_SIZE_BTN, callback_data="settings_size")],
    ])


def size_keyboard(current: str, show_back: bool) -> InlineKeyboardMarkup:
    from bot.services.models import IMAGE_SIZES
    buttons = []
    for value in IMAGE_SIZES:
        label = IMAGE_SIZES[value]["label"]
        tick = "✅ " if value == current else ""
        buttons.append([InlineKeyboardButton(text=f"{tick}{label}", callback_data=f"size:{value}")])
    if show_back:
        buttons.append([InlineKeyboardButton(text=texts.SETTINGS_BACK, callback_data="settings_home")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def model_keyboard(tier: str, current: str) -> InlineKeyboardMarkup:
    buttons = []
    for value in model_ids():
        if tier == "free" and not is_free_model(value):
            text = f"🔒 {model_label(value)}"
        else:
            tick = "✅ " if value == current else ""
            text = f"{tick}{model_label(value)}"
        buttons.append([InlineKeyboardButton(text=text, callback_data=f"model:{value}")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=texts.CONFIRM_YES, callback_data="confirm_yes"),
        InlineKeyboardButton(text=texts.CONFIRM_NO, callback_data="confirm_no"),
    ]])


def admin_status(bot_enabled: bool) -> InlineKeyboardMarkup:
    toggle_text = "🔴 غیرفعال کردن ربات" if bot_enabled else "🟢 فعال کردن ربات"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=toggle_text, callback_data="toggle_bot")],
        [InlineKeyboardButton(text="🔄 ریست روزانه همه", callback_data="reset_daily")],
        [InlineKeyboardButton(text="💾 پشتیبان‌گیری همین حالا", callback_data="backup_now")],
    ])
