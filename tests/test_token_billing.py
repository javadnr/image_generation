import asyncio

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool

from bot.db.models import Base, User
from bot.services import user as user_svc
from bot.services import models as models_svc
from bot.services.payment import activate_plan, deactivate_plan

TEST_MODELS = {
    "gpt-image-2.5-flare": {
        "label": "gpt-image-2.5-flare",
        "free": True,
        "cost": {
            "low": {"cost": 0.006, "tokens": 200},
            "medium": {"cost": 0.0133, "tokens": 443},
            "high": {"cost": 0.0266, "tokens": 1760},
        },
    },
    "gpt-image-2.5-sunburst": {
        "label": "gpt-image-2.5-sunburst",
        "free": False,
        "cost": {
            "low": {"cost": 0.006, "tokens": 200},
            "medium": {"cost": 0.0133, "tokens": 443},
            "high": {"cost": 0.0266, "tokens": 1760},
        },
    },
}

TEST_PLAN_TOKENS = {"BRONZE_MAX_TOKEN": 10000, "SILVER_MAX_TOKEN": 25000, "GOLD_MAX_TOKEN": 60000}


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def db():
    # Strip postgresql-only partial index (not supported on SQLite)
    Base.metadata.tables["transactions"].indexes.clear()

    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
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
    monkeypatch.setattr(settings, "BRONZE_MAX_TOKEN", TEST_PLAN_TOKENS["BRONZE_MAX_TOKEN"])
    monkeypatch.setattr(settings, "SILVER_MAX_TOKEN", TEST_PLAN_TOKENS["SILVER_MAX_TOKEN"])
    monkeypatch.setattr(settings, "GOLD_MAX_TOKEN", TEST_PLAN_TOKENS["GOLD_MAX_TOKEN"])
    monkeypatch.setattr(settings, "PROFIT_PERCENTAGE", 20.0)
    monkeypatch.setattr(settings, "FREE_USAGE_TOKEN", 1000)
    return TEST_MODELS


async def _make_user(
    session,
    telegram_id,
    tier="free",
    token_balance=0,
    daily_used=0,
    model="gpt-image-2.5-flare",
    quality="low",
):
    user = User(
        telegram_id=telegram_id,
        tier=tier,
        token_balance=token_balance,
        daily_used=daily_used,
        image_model=model,
        image_quality=quality,
    )
    session.add(user)
    await session.flush()
    return user


@pytest.mark.asyncio
async def test_activate_grants_allowance(db, catalog):
    user = await _make_user(db, 1001)
    await db.commit()

    await activate_plan(db, user, "bronze")
    assert user.token_balance == 10000
    assert user.tier == "bronze"
    assert user.premium_expire_date is not None


@pytest.mark.asyncio
async def test_deactivate_zeroes_balance(db, catalog):
    user = await _make_user(db, 1002, tier="gold", token_balance=60000)
    await db.commit()

    await deactivate_plan(db, user)
    assert user.tier == "free"
    assert user.token_balance == 1000
    assert user.premium_expire_date is None


@pytest.mark.asyncio
async def test_set_tier_grants_allowance(db, catalog):
    user = await _make_user(db, 1003)
    await db.commit()

    updated = await user_svc.set_tier(db, 1003, "silver")
    assert updated.token_balance == 25000

    updated = await user_svc.set_tier(db, 1003, "free")
    assert updated.token_balance == 1000


@pytest.mark.asyncio
async def test_precheck_refuses_insufficient_balance(db, catalog):
    user = await _make_user(
        db, 1004, tier="bronze", token_balance=500,
        model="gpt-image-2.5-flare", quality="high",
    )
    await db.commit()

    assert await user_svc.can_generate(db, user) is False


@pytest.mark.asyncio
async def test_precheck_allows_sufficient_balance(db, catalog):
    user = await _make_user(
        db, 1005, tier="bronze", token_balance=2000,
        model="gpt-image-2.5-flare", quality="low",
    )
    await db.commit()

    assert await user_svc.can_generate(db, user) is True


@pytest.mark.asyncio
async def test_precheck_uses_raw_minimum_without_profit(db, catalog):
    # low minimum is 200 raw; profit would require 240 — gate uses 200
    user = await _make_user(
        db, 1014, tier="bronze", token_balance=220,
        model="gpt-image-2.5-flare", quality="low",
    )
    await db.commit()
    assert await user_svc.can_generate(db, user) is True

    user.token_balance = 199
    await db.commit()
    assert await user_svc.can_generate(db, user) is False


@pytest.mark.asyncio
async def test_overrun_deduct_floors_at_zero(db, catalog):
    # 300 balance, 333 actual -> 400 charged -> delivered, balance 0
    user = await _make_user(db, 1015, tier="bronze", token_balance=300)
    await db.commit()

    assert await user_svc.can_generate(db, user) is True
    assert await user_svc.deduct_tokens(db, user, 333) == 0
    assert user.token_balance == 0


@pytest.mark.asyncio
async def test_deduct_applies_profit_once(db, catalog):
    # 20% profit: 200->240, 500->600, 501->602, 1200->1440
    user = await _make_user(db, 1006, tier="bronze", token_balance=10000)
    await db.commit()

    assert await user_svc.deduct_tokens(db, user, 200) == 9760
    assert await user_svc.deduct_tokens(db, user, 500) == 9160
    assert await user_svc.deduct_tokens(db, user, 501) == 8558
    assert await user_svc.deduct_tokens(db, user, 1200) == 7118
    assert user.token_balance == 7118


@pytest.mark.asyncio
async def test_deduct_zero_profit_is_exact(db, catalog, monkeypatch):
    from bot.config import settings
    monkeypatch.setattr(settings, "PROFIT_PERCENTAGE", 0.0)
    user = await _make_user(db, 1012, tier="bronze", token_balance=10000)
    await db.commit()

    assert await user_svc.deduct_tokens(db, user, 1000) == 9000


@pytest.mark.asyncio
async def test_deduct_half_profit(db, catalog, monkeypatch):
    from bot.config import settings
    monkeypatch.setattr(settings, "PROFIT_PERCENTAGE", 50.0)
    user = await _make_user(db, 1013, tier="bronze", token_balance=10000)
    await db.commit()

    assert await user_svc.deduct_tokens(db, user, 1000) == 8500


@pytest.mark.asyncio
async def test_deduct_floors_at_zero(db, catalog):
    user = await _make_user(db, 1007, tier="bronze", token_balance=200)
    await db.commit()

    remaining = await user_svc.deduct_tokens(db, user, 2950)
    assert remaining == 0
    assert user.token_balance == 0


@pytest.mark.asyncio
async def test_deduct_unknown_usage_deducts_zero(db, catalog):
    user = await _make_user(db, 1008, tier="bronze", token_balance=10000)
    await db.commit()

    remaining = await user_svc.deduct_tokens(db, user, None)
    assert remaining == 10000


@pytest.mark.asyncio
async def test_missing_estimate_fails_open(db, catalog, monkeypatch):
    from bot.config import settings
    monkeypatch.setattr(settings, "MODELS", {"mystery-model": {"free": False}})
    user = await _make_user(
        db, 1009, tier="bronze", token_balance=0, model="mystery-model",
    )
    await db.commit()

    assert await user_svc.can_generate(db, user) is True


@pytest.mark.asyncio
async def test_mixed_quality_sequence(db, catalog):
    user = await _make_user(
        db, 1010, tier="silver", token_balance=25000,
        model="gpt-image-2.5-flare", quality="low",
    )
    await db.commit()

    assert await user_svc.can_generate(db, user) is True
    await user_svc.deduct_tokens(db, user, 200)
    assert user.token_balance == 24760

    user.image_quality = "high"
    assert await user_svc.can_generate(db, user) is True
    await user_svc.deduct_tokens(db, user, 2950)
    assert user.token_balance == 21220


@pytest.mark.asyncio
async def test_free_flow_uses_token_balance(db, catalog):
    user = await _make_user(db, 1011, tier="free", token_balance=1000)
    await db.commit()

    assert await user_svc.can_generate(db, user) is True
    await user_svc.deduct_tokens(db, user, 200)
    assert user.token_balance == 760
    await user_svc.deduct_tokens(db, user, 800)
    assert await user_svc.can_generate(db, user) is False


def test_plan_allowance_helper(catalog):
    assert models_svc.plan_allowance("bronze") == 10000
    assert models_svc.plan_allowance("silver") == 25000
    assert models_svc.plan_allowance("gold") == 60000
    assert models_svc.plan_allowance("free") == 0
    assert models_svc.plan_allowance("unknown") == 0


def test_estimate_helper(catalog):
    assert models_svc.estimate_tokens("gpt-image-2.5-flare", "low") == 200
    assert models_svc.estimate_tokens("gpt-image-2.5-flare", "high") == 1760
    assert models_svc.estimate_tokens("unknown-model", "low") is None
    assert models_svc.estimate_tokens("gpt-image-2.5-flare", "ultra") is None


def test_edit_cost_default():
    from bot.config import settings
    assert settings.IMAGE_EDIT_COST_TOKENS > 0


def test_get_edit_cost_respects_env(monkeypatch):
    from bot.config import settings
    monkeypatch.setattr(settings, "IMAGE_EDIT_COST_TOKENS", 1234)
    assert user_svc.get_edit_cost() == 1234


@pytest.mark.asyncio
async def test_has_edit_balance(db, monkeypatch):
    from bot.config import settings
    monkeypatch.setattr(settings, "IMAGE_EDIT_COST_TOKENS", 4000)
    free = await _make_user(db, 2001, tier="free", token_balance=99999)
    poor = await _make_user(db, 2002, tier="bronze", token_balance=3999)
    exact = await _make_user(db, 2003, tier="silver", token_balance=4000)
    rich = await _make_user(db, 2004, tier="gold", token_balance=50000)
    await db.commit()

    assert user_svc.has_edit_balance(free) is False
    assert user_svc.has_edit_balance(poor) is False
    assert user_svc.has_edit_balance(exact) is True
    assert user_svc.has_edit_balance(rich) is True


@pytest.mark.asyncio
async def test_edit_deduct_applies_profit(db, catalog, monkeypatch):
    from bot.config import settings
    monkeypatch.setattr(settings, "IMAGE_EDIT_COST_TOKENS", 4000)
    user = await _make_user(db, 2005, tier="bronze", token_balance=10000)
    await db.commit()

    # edit reported 700 actual tokens -> 840 charged at 20% profit
    remaining = await user_svc.deduct_tokens(db, user, 700)
    assert remaining == 9160
