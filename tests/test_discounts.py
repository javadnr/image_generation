import asyncio
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool

from bot.db.models import Base, User
from bot.services import discounts as dis_svc
from bot.services import pricing as pricing_svc


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    tx_table = Base.metadata.tables["transactions"]
    tx_table.indexes.clear()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()


@pytest.fixture(autouse=True)
def seeded_fx_rate():
    import time
    saved = dict(pricing_svc._cache)
    pricing_svc._cache.update({"rate": 100000.0, "at": time.monotonic()})
    yield
    pricing_svc._cache.update(saved)


TEST_MODELS = {
    "gpt-image-2.5-flare": {
        "label": "gpt-image-2.5-flare",
        "free": True,
        "per_million_cost": 30,
        "cost": {
            "low": {"cost": 0.006, "tokens": 200},
            "medium": {"cost": 0.0133, "tokens": 443},
            "high": {"cost": 0.0266, "tokens": 1760},
        },
    },
}


@pytest.fixture
def catalog(monkeypatch):
    from bot.config import settings
    monkeypatch.setattr(settings, "MODELS", dict(TEST_MODELS))
    monkeypatch.setattr(settings, "BRONZE_MAX_TOKEN", 10000)
    monkeypatch.setattr(settings, "SILVER_MAX_TOKEN", 25000)
    monkeypatch.setattr(settings, "GOLD_MAX_TOKEN", 60000)
    yield


async def _make_user(session, telegram_id, tier="free"):
    user = User(telegram_id=telegram_id, tier=tier)
    session.add(user)
    await session.flush()
    return user


# ---------- command parsing ----------

def test_parse_off_valid():
    assert dis_svc.parse_off_command("/off bronze 15 1") == ("bronze", 15, 1)
    assert dis_svc.parse_off_command("/off all 10 1") == ("all", 10, 1)
    assert dis_svc.parse_off_command("/off GOLD 100 30") == ("gold", 100, 30)
    assert dis_svc.parse_off_command("/off silver 0 5") == ("silver", 0, 5)


def test_parse_off_invalid():
    assert dis_svc.parse_off_command("/off platinum 10 1") is None
    assert dis_svc.parse_off_command("/off bronze 101 1") is None
    assert dis_svc.parse_off_command("/off bronze -5 1") is None
    assert dis_svc.parse_off_command("/off bronze abc 1") is None
    assert dis_svc.parse_off_command("/off bronze 10 0") is None
    assert dis_svc.parse_off_command("/off bronze 10") is None
    assert dis_svc.parse_off_command("/off") is None
    assert dis_svc.parse_off_command("/broadcast hi") is None
    assert dis_svc.parse_off_command("") is None


# ---------- set / clear / expiry ----------

@pytest.mark.asyncio
async def test_set_and_read_discount(db):
    await dis_svc.set_discount(db, "bronze", 15, 1)
    discounts = await dis_svc.get_active_discounts(db)
    assert discounts["bronze"][0] == 15
    assert discounts["bronze"][1] > datetime.now()


@pytest.mark.asyncio
async def test_set_overwrites_same_scope(db):
    await dis_svc.set_discount(db, "silver", 10, 1)
    await dis_svc.set_discount(db, "silver", 25, 2)
    discounts = await dis_svc.get_active_discounts(db)
    assert discounts["silver"][0] == 25
    assert len([s for s in discounts if s == "silver"]) == 1


@pytest.mark.asyncio
async def test_clear_with_zero_percent(db):
    await dis_svc.set_discount(db, "gold", 20, 5)
    await dis_svc.set_discount(db, "gold", 0, 5)
    discounts = await dis_svc.get_active_discounts(db)
    assert "gold" not in discounts


@pytest.mark.asyncio
async def test_expired_discounts_excluded(db):
    from bot.db.models import Discount
    db.add(Discount(scope="bronze", percent=50,
                    expires_at=datetime.now() - timedelta(hours=1)))
    await db.commit()
    discounts = await dis_svc.get_active_discounts(db)
    assert "bronze" not in discounts


# ---------- precedence + math ----------

def test_discount_precedence():
    exp = datetime.now() + timedelta(days=1)
    assert dis_svc.discount_for("bronze", None) == 0
    assert dis_svc.discount_for("bronze", {}) == 0
    assert dis_svc.discount_for("bronze", {"all": (10, exp)}) == 10
    assert dis_svc.discount_for("bronze", {"all": (10, exp), "bronze": (15, exp)}) == 15
    assert dis_svc.discount_for("gold", {"all": (10, exp), "bronze": (15, exp)}) == 10


def test_discounted_price_keeps_exact_value():
    # discounted prices are NOT re-rounded: 50% of 50000 stays 25000
    assert dis_svc.discounted_price(50000, 50) == 25000
    assert dis_svc.discounted_price(80000, 15) == 68000
    assert dis_svc.discounted_price(80000, 0) == 80000
    assert dis_svc.discounted_price(None, 15) is None
    assert dis_svc.discounted_price(80000, 100) == 0


def test_plan_price_with_discount(catalog):
    # bronze: 0.3 USD * 100000 = 30000; 50% -> 15000 kept as-is
    assert pricing_svc.plan_price_toman("bronze", 0) == 30000
    assert pricing_svc.plan_price_toman("bronze", 50) == 15000
    assert pricing_svc.plan_price_toman("unknown", 50) is None


# ---------- UI ----------

def test_premium_text_shows_discount(catalog):
    from bot.handlers import premium as premium_h
    from datetime import datetime, timedelta
    user = SimpleNamespace(tier="free")
    exp = datetime.now() + timedelta(days=1)
    text = premium_h.premium_text(user, {"bronze": (15, exp)})
    assert "15٪ تخفیف" in text
    assert exp.strftime("%Y/%m/%d") in text


def test_premium_text_without_discount_has_no_tag(catalog):
    from bot.handlers import premium as premium_h
    user = SimpleNamespace(tier="free")
    text = premium_h.premium_text(user, {})
    assert "تخفیف" not in text


def test_premium_menu_shows_discounted_price(catalog):
    from bot.keyboards.inline import premium_menu
    from datetime import datetime, timedelta
    user = SimpleNamespace(tier="free")
    exp = datetime.now() + timedelta(days=1)
    kb = premium_menu(user, {"silver": (50, exp)})
    texts = [b.text for row in kb.inline_keyboard for b in row]
    assert any("تخفیف" in t for t in texts)
    # 0.75*100000=75000 -> base ceil10k 80000 -> 50% -> 40000
    assert any("۴۰ هزار تومان" in t for t in texts)


# ---------- purchase honors discount ----------

@pytest.mark.asyncio
async def test_zarinpal_purchase_uses_discounted_amount(db, catalog):
    from unittest.mock import AsyncMock, patch
    user = await _make_user(db, 111, "free")
    await db.commit()
    with patch("bot.services.payment.get_zarinpal_client") as mock:
        client = AsyncMock()
        client.request_payment.return_value = ("auth-x", "https://pay/x")
        mock.return_value = client
        from bot.services.payment import create_zarinpal_purchase
        result = await create_zarinpal_purchase(db, user, "bronze", 50)
    assert result["amount_toman"] == 15000
    assert client.request_payment.call_args[0][0] == 15000


# ---------- broadcast targeting ----------

@pytest.mark.asyncio
async def test_free_user_ids_excludes_premium(db):
    await _make_user(db, 201, "free")
    await _make_user(db, 202, "free")
    await _make_user(db, 203, "bronze")
    await _make_user(db, 204, "gold")
    await db.commit()
    ids = await dis_svc.free_user_ids(db)
    assert sorted(ids) == [201, 202]


# ---------- flood-safe fanout ----------

@pytest.mark.asyncio
async def test_fanout_retries_after_flood_wait(monkeypatch):
    import asyncio as _asyncio
    from aiogram.exceptions import TelegramRetryAfter
    from bot.handlers import admin as admin_h

    async def _nosleep(*a, **k):
        return None
    monkeypatch.setattr(_asyncio, "sleep", _nosleep)

    calls = []

    class FakeBot:
        async def send_message(self, uid, text, reply_markup=None):
            calls.append(uid)
            if len(calls) == 1:
                raise TelegramRetryAfter(method=None, message="slow down", retry_after=0)
            return True

    ok, fail = await admin_h._fanout(FakeBot(), [11, 22], "hi", None)
    assert (ok, fail) == (2, 0)
    assert calls == [11, 11, 22]


@pytest.mark.asyncio
async def test_fanout_counts_blocked_users(monkeypatch):
    import asyncio as _asyncio
    from bot.handlers import admin as admin_h

    async def _nosleep(*a, **k):
        return None
    monkeypatch.setattr(_asyncio, "sleep", _nosleep)

    class FakeBot:
        async def send_message(self, uid, text, reply_markup=None):
            if uid == 99:
                raise Exception("bot blocked")
            return True

    ok, fail = await admin_h._fanout(FakeBot(), [11, 99], "hi", None)
    assert (ok, fail) == (1, 1)
