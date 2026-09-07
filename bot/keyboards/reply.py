from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from bot.config import settings
import bot.texts as texts


def main_menu(user_id: int) -> ReplyKeyboardMarkup:
    buttons = [
        [KeyboardButton(text=texts.MAIN_MENU_GENERATE)],
        [KeyboardButton(text=texts.MAIN_MENU_BALANCE)],
        [KeyboardButton(text=texts.MAIN_MENU_PREMIUM)],
    ]
    if user_id in settings.ADMIN_IDS:
        buttons.append([KeyboardButton(text=texts.MAIN_MENU_ADMIN)])
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)
