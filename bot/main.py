import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz
from sqlalchemy import update

from bot.config import settings
from bot.db.engine import init_db, async_session
from bot.db.models import BotSettings, User
from bot.middlewares.db import DBSessionMiddleware
from bot.middlewares.force_join import (
    ForceJoinMiddleware, ForceJoinCallbackMiddleware,
    BotEnabledMiddleware, BotEnabledCallbackMiddleware,
    PrivateChatMiddleware,
)
from bot.services.queue import init_queues
from bot.handlers import start, generate, edit, balance, premium, settings as settings_handler, admin

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

IRAN_TZ = pytz.timezone("Asia/Tehran")


async def reset_daily_quotas():
    async with async_session() as session:
        from datetime import date
        await session.execute(
            update(User).values(daily_used=0, last_reset_date=date.today())
        )
        await session.commit()
    logger.info("Daily quotas reset.")


async def on_startup():
    await init_db()
    async with async_session() as session:
        from sqlalchemy import select
        result = await session.execute(select(BotSettings).where(BotSettings.id == 1))
        row = result.scalar_one_or_none()
        if not row:
            session.add(BotSettings(id=1, bot_enabled=settings.BOT_ENABLED))
            await session.commit()
        else:
            row.bot_enabled = settings.BOT_ENABLED
            await session.commit()

    init_queues()
    logger.info("Bot started (%s). Bot enabled: %s", settings.API_SERVER, settings.BOT_ENABLED)


async def main():
    if settings.API_SERVER == "bale":
        bale_api = TelegramAPIServer(
            base="https://tapi.bale.ai/bot{token}/{method}",
            file="https://tapi.bale.ai/file/bot{token}/{path}",
        )
        bot = Bot(
            token=settings.BOT_TOKEN,
            default=DefaultBotProperties(parse_mode=None),
            session=AiohttpSession(api=bale_api),
        )
    else:
        bot = Bot(
            token=settings.BOT_TOKEN,
            default=DefaultBotProperties(parse_mode=None),
        )

    dp = Dispatcher()

    dp.message.middleware(PrivateChatMiddleware())
    dp.message.middleware(BotEnabledMiddleware())
    dp.message.middleware(ForceJoinMiddleware())
    dp.message.middleware(DBSessionMiddleware())

    dp.callback_query.middleware(BotEnabledCallbackMiddleware())
    dp.callback_query.middleware(ForceJoinCallbackMiddleware())
    dp.callback_query.middleware(DBSessionMiddleware())

    dp.pre_checkout_query.middleware(DBSessionMiddleware())

    dp.include_router(start.router)
    dp.include_router(admin.router)
    dp.include_router(premium.router)
    dp.include_router(balance.router)
    dp.include_router(settings_handler.router)
    dp.include_router(generate.router)
    dp.include_router(edit.router)

    if settings.API_SERVER == "bale":
        from bot.handlers import bale_payment
        dp.include_router(bale_payment.router)

    scheduler = AsyncIOScheduler(timezone=IRAN_TZ)
    scheduler.add_job(reset_daily_quotas, CronTrigger(hour=0, minute=0, timezone=IRAN_TZ))
    scheduler.start()

    dp.startup.register(on_startup)

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
