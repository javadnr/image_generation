from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from bot.config import settings
from bot.services.user import TIER_LIMITS
import bot.texts as texts


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
        buttons.append([InlineKeyboardButton(text="🥉 برنزی", callback_data="buy_bronze")])
        buttons.append([InlineKeyboardButton(text="🥈 نقره‌ای", callback_data="buy_silver")])
        buttons.append([InlineKeyboardButton(text="🥇 طلایی", callback_data="buy_gold")])
    else:
        buttons.append([InlineKeyboardButton(text=texts.PREMIUM_SETTINGS, callback_data="settings")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def settings_menu(user) -> InlineKeyboardMarkup:
    current = f"🖼 رزولوشن فعلی: {user.image_width}×{user.image_height}"
    optimize_status = texts.SETTINGS_OPTIMIZE_ON if user.optimize_prompt else texts.SETTINGS_OPTIMIZE_OFF
    optimize_text = f"✨ بهینه‌سازی پرامپت: {optimize_status}"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=current, callback_data="resolution_picker")],
        [InlineKeyboardButton(text=optimize_text, callback_data="toggle_optimize")],
        [InlineKeyboardButton(text=texts.SETTINGS_BACK, callback_data="back_premium")],
    ])


def resolution_picker(current_width: int, current_height: int) -> InlineKeyboardMarkup:
    current = f"{current_width}×{current_height}"
    options = ["1024×1024", "512×512", "768×1024", "1024×768"]
    buttons = []
    for opt in options:
        tick = "✅ " if opt == current else ""
        w, h = opt.split("×")
        buttons.append([InlineKeyboardButton(
            text=f"{tick}{opt}",
            callback_data=f"set_res_{w}_{h}",
        )])
    buttons.append([InlineKeyboardButton(
        text=texts.RESOLUTION_CUSTOM,
        callback_data="custom_resolution",
    )])
    buttons.append([InlineKeyboardButton(
        text=texts.SETTINGS_BACK,
        callback_data="settings",
    )])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def admin_status(bot_enabled: bool) -> InlineKeyboardMarkup:
    toggle_text = "🔴 غیرفعال کردن ربات" if bot_enabled else "🟢 فعال کردن ربات"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=toggle_text, callback_data="toggle_bot")],
        [InlineKeyboardButton(text="🔄 ریست روزانه همه", callback_data="reset_daily")],
    ])
