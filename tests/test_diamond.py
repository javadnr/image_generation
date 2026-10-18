"""Diamond plan integration + backward-compatibility checks.

Verifies the new Diamond plan is wired everywhere the other paid plans
are, and that Free/Bronze/Silver/Gold configuration is untouched.
"""
import asyncio
from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool

from bot.db.models import Base, User
from bot.services import models as models_svc
from bot.services.payment import activate_plan, deactivate_plan

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

TEST_PLAN_TOKENS = {
    "BRONZE_MAX_TOKEN": 10000, "SILVER_MAX_TOKEN": 25000,
    "GOLD_MAX_TOKEN": 60000, "DIAMOND_MAX_TOKEN": 120000,
}


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def db():
    Base.metadata.tables["transactions"].indexes.clear()
    engine = create_async_engine(
        "sqlite+aiosqlite://", connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()


@pytest.fixture
def catalog(monkeypatch):
    from bot.config import settings
    monkeypatch.setattr(settings, "MODELS", TEST_MODELS)
    monkeypatch.setattr(settings, "PROFIT_PERCENTAGE", 20.0)
    monkeypatch.setattr(settings, "FREE_USAGE_TOKEN", 1000)
    for key, value in TEST_PLAN_TOKENS.items():
        monkeypatch.setattr(settings, key, value)
    yield


# ---------- registry / allowance ----------

def test_plans_registry_order():
    assert models_svc.PLANS == ("bronze", "silver", "gold", "diamond")


def test_plan_allowance_reads_env(catalog):
    assert models_svc.plan_allowance("diamond") == 120000
    assert models_svc.plan_allowance("bronze") == 10000
    assert models_svc.plan_allowance("silver") == 25000
    assert models_svc.plan_allowance("gold") == 60000
    assert models_svc.plan_allowance("free") == 0
    assert models_svc.plan_allowance("unknown") == 0


# ---------- pricing ----------

def test_diamond_is_priced_from_allowance(catalog, monkeypatch):
    from bot.services import pricing as pricing_svc
    pricing_svc._cache.update({"rate": 100000, "at": __import__("time").monotonic()})
    # 120000 tokens * 30 USD/1M = 3.6 USD * 100000 = 360000 -> ceil10k
    assert pricing_svc.plan_price_toman("diamond") == 360000
    # and higher than gold, never equal
    assert pricing_svc.plan_price_toman("diamond") > pricing_svc.plan_price_toman("gold")


# ---------- discounts ----------

def test_diamond_discount_scope():
    from bot.services import discounts as dis_svc
    assert "diamond" in dis_svc.VALID_SCOPES
    assert dis_svc.parse_off_command("/off diamond 15 2") == ("diamond", 15, 2)


# ---------- queue ----------

def test_diamond_queue_registered(monkeypatch):
    from bot.config import settings
    from bot.services import queue as queue_svc
    monkeypatch.setattr(settings, "DIAMOND_QUEUE_SIZE", 0)
    queue_svc.init_queues()
    assert "diamond" in queue_svc.TIER_QUEUES


# ---------- activation / lifecycle ----------

@pytest.mark.asyncio
async def test_activate_diamond_grants_allowance(db, catalog):
    user = User(telegram_id=7001, tier="free", token_balance=1000)
    db.add(user)
    await db.commit()

    await activate_plan(db, user, "diamond")
    assert user.tier == "diamond"
    assert user.token_balance == 120000
    assert user.premium_expire_date is not None


@pytest.mark.asyncio
async def test_diamond_deactivate_returns_to_free(db, catalog):
    user = User(telegram_id=7002, tier="diamond", token_balance=120000)
    db.add(user)
    await db.commit()

    await deactivate_plan(db, user)
    assert user.tier == "free"
    assert user.token_balance == 1000
    assert user.premium_expire_date is None


# ---------- UI: menu text + buttons ----------

def test_premium_text_has_diamond_description(catalog):
    from bot.handlers import premium as premium_h
    user = SimpleNamespace(tier="free")
    text = premium_h.premium_text(user, {})
    assert "الماسی" in text
    assert "120,000" in text
    assert "مناسب تیم‌ها و گروه‌های حرفه‌ای" in text
    # audience lines for all paid plans present
    assert "مناسب کاربران تازه‌کار" in text
    assert "مثل تولیدکنندگان محتوا" in text


def test_premium_menu_has_diamond_button(catalog):
    from bot.keyboards.inline import premium_menu
    user = SimpleNamespace(tier="free")
    kb = premium_menu(user, {})
    datas = [b.callback_data for row in kb.inline_keyboard for b in row]
    assert "buy_diamond" in datas
    # order: bronze, silver, gold, diamond
    assert datas == ["buy_bronze", "buy_silver", "buy_gold", "buy_diamond"]


def test_admin_stats_template_has_diamond_placeholders():
    import bot.texts as texts
    # format() must not raise: every diamond placeholder is present
    out = texts.ADMIN_STATS.format(
        status="x", total_users=0, active_today=0, joined_today=0,
        started_today=0, success_today=0, failed_today=0,
        click_total=0, click_unique=0, pricing_viewers=0, pricing_new=0,
        plan_bronze=0, plan_silver=0, plan_gold=0, plan_diamond=0,
        pay_started=0, pay_success=0,
        free_images=0, bronze_images=0, silver_images=0, gold_images=0,
        diamond_images=0,
        bronze_users=0, silver_users=0, gold_users=0, diamond_users=0,
    )
    assert "الماسی" in out


def test_tier_validations_accept_diamond():
    from bot.handlers import admin as admin_h  # noqa: F401
    from bot.handlers import premium as premium_h
    assert "diamond" in premium_h.TIER_NAMES
    assert premium_h.TIER_NAMES["diamond"].endswith("الماسی")
