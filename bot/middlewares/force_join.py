from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery
from bot.config import settings
from bot.db.engine import async_session
from bot.services.user import get_or_create_user
import bot.texts as texts
from bot.keyboards.inline import force_join


class ForceJoinMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: Dict[str, Any],
    ) -> Any:
        if not settings.REQUIRED_CHANNELS:
            return await handler(event, data)

        user_id = event.from_user.id
        if user_id in settings.ADMIN_IDS:
            return await handler(event, data)

        bot = data.get("bot")
        for channel_id in settings.REQUIRED_CHANNELS:
            try:
                member = await bot.get_chat_member(chat_id=channel_id, user_id=user_id)
                if member.status in ("left", "kicked"):
                    await event.answer(texts.FORCE_JOIN_TITLE, reply_markup=force_join())
                    return
            except Exception:
                continue

        return await handler(event, data)


class ForceJoinCallbackMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[CallbackQuery, Dict[str, Any]], Awaitable[Any]],
        event: CallbackQuery,
        data: Dict[str, Any],
    ) -> Any:
        if not settings.REQUIRED_CHANNELS:
            return await handler(event, data)

        user_id = event.from_user.id
        if user_id in settings.ADMIN_IDS:
            return await handler(event, data)

        if event.data == "verify_join":
            return await handler(event, data)

        bot = data.get("bot")
        for channel_id in settings.REQUIRED_CHANNELS:
            try:
                member = await bot.get_chat_member(chat_id=channel_id, user_id=user_id)
                if member.status in ("left", "kicked"):
                    await event.answer(texts.FORCE_JOIN_NOT_JOINED, show_alert=True)
                    return
            except Exception:
                continue

        return await handler(event, data)


class BotEnabledMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: Dict[str, Any],
    ) -> Any:
        async with async_session() as session:
            from sqlalchemy import select
            from bot.db.models import BotSettings
            result = await session.execute(select(BotSettings).where(BotSettings.id == 1))
            settings_row = result.scalar_one_or_none()
            if settings_row and not settings_row.bot_enabled:
                user_id = event.from_user.id
                if user_id not in settings.ADMIN_IDS:
                    await event.answer(texts.BOT_DISABLED)
                    return
        return await handler(event, data)


class BotEnabledCallbackMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[CallbackQuery, Dict[str, Any]], Awaitable[Any]],
        event: CallbackQuery,
        data: Dict[str, Any],
    ) -> Any:
        async with async_session() as session:
            from sqlalchemy import select
            from bot.db.models import BotSettings
            result = await session.execute(select(BotSettings).where(BotSettings.id == 1))
            settings_row = result.scalar_one_or_none()
            if settings_row and not settings_row.bot_enabled:
                user_id = event.from_user.id
                if user_id not in settings.ADMIN_IDS and event.data != "toggle_bot":
                    await event.answer(texts.BOT_DISABLED, show_alert=True)
                    return
        return await handler(event, data)


class PrivateChatMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: Dict[str, Any],
    ) -> Any:
        if event.chat.type != "private":
            return
        return await handler(event, data)
