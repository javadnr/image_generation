import asyncio

import pytest

from bot.config import settings
from bot.services import report as report_svc


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


class _Bot:
    def __init__(self):
        self.messages = []

    async def send_message(self, chat_id, text):
        self.messages.append(text)


@pytest.mark.asyncio
async def test_premium_report_includes_source(monkeypatch):
    monkeypatch.setattr(settings, "PAYMENT_REPORT_CHANNEL_ID", 1)
    bot = _Bot()
    await report_svc.send_premium_report(bot, 123, "bronze", source="YouTube")
    assert "🧭 منبع آشنایی: YouTube" in bot.messages[0]


@pytest.mark.asyncio
async def test_premium_report_source_fallback(monkeypatch):
    monkeypatch.setattr(settings, "PAYMENT_REPORT_CHANNEL_ID", 1)
    bot = _Bot()
    await report_svc.send_premium_report(bot, 123, "bronze")
    assert "🧭 منبع آشنایی: نامشخص" in bot.messages[0]


class _PhotoBot:
    def __init__(self):
        self.captions = []

    async def send_photo(self, chat_id, photo=None, caption=None):
        self.captions.append(caption)


@pytest.mark.asyncio
async def test_processed_report_shows_actual_cost_and_capped_deduction(monkeypatch):
    monkeypatch.setattr(settings, "PROCESSED_REQUESTS_CHANNEL_ID", 1)
    bot = _PhotoBot()
    await report_svc.send_processed_report(
        bot,
        user_id=1,
        operation="generate",
        prompt="x",
        tokens=500,
        image_bytes=b"img",
        remaining=0,
        balance_before=300,
        deducted=300,
        tier="free",
    )
    caption = bot.captions[0]
    assert "🔢 توکن مصرفی (API): 500" in caption
    assert "📦 پلن: آزاد" in caption
    assert "📊 موجودی قبل از کسر: 300" in caption
    assert "➖ کسر شده از کاربر: 300" in caption
    assert "💰 باقی‌مانده: 0" in caption
