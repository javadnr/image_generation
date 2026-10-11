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

TEST_PLAN_TOKENS = {"bronze": 10000, "silver": 25000, "gold": 60000}


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
    monkeypatch.setattr(settings, "PLAN_TOKENS", dict(TEST_PLAN_TOKENS))
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
    assert user.token_balance == 0
    assert user.premium_expire_date is None


@pytest.mark.asyncio
async def test_set_tier_grants_allowance(db, catalog):
    user = await _make_user(db, 1003)
    await db.commit()

    updated = await user_svc.set_tier(db, 1003, "silver")
    assert updated.token_balance == 25000

    updated = await user_svc.set_tier(db, 1003, "free")
    assert updated.token_balance == 0


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
async def test_deduct_exact_actual_usage(db, catalog):
    user = await _make_user(db, 1006, tier="bronze", token_balance=10000)
    await db.commit()

    remaining = await user_svc.deduct_tokens(db, user, 500)
    assert remaining == 9500
    assert user.token_balance == 9500


@pytest.mark.asyncio
async def test_deduct_floors_at_zero(db, catalog):
    user = await _make_user(db, 1007, tier="bronze", token_balance=200)
    await db.commit()

    remaining = await user_svc.deduct_tokens(db, user, 3000)
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
    assert user.token_balance == 24800

    user.image_quality = "high"
    assert await user_svc.can_generate(db, user) is True
    await user_svc.deduct_tokens(db, user, 3000)
    assert user.token_balance == 21800


@pytest.mark.asyncio
async def test_free_flow_regression(db, catalog):
    user = await _make_user(db, 1011, tier="free", daily_used=0)
    await db.commit()

    assert await user_svc.can_generate(db, user) is True
    await user_svc.consume_quota(db, user)
    assert await user_svc.can_generate(db, user) is True
    await user_svc.consume_quota(db, user)
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
