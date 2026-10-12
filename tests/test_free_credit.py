import asyncio

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool

from bot.db.models import Base, User
from bot.services import user as user_svc


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
def free_grant(monkeypatch):
    from bot.config import settings
    monkeypatch.setattr(settings, "FREE_USAGE_TOKEN", 1000)
    return 1000


async def _make_user(session, telegram_id, tier="free", token_balance=0):
    user = User(
        telegram_id=telegram_id,
        tier=tier,
        token_balance=token_balance,
    )
    session.add(user)
    await session.flush()
    return user


@pytest.mark.asyncio
async def test_new_users_get_free_grant(db, free_grant):
    user = await user_svc.get_or_create_user(db, 801)
    assert user.tier == "free"
    assert user.token_balance == 1000


@pytest.mark.asyncio
async def test_existing_user_not_regranted(db, free_grant):
    user = await _make_user(db, 802, tier="free", token_balance=250)
    await db.commit()

    same = await user_svc.get_or_create_user(db, 802)
    assert same.id == user.id
    assert same.token_balance == 250


@pytest.mark.asyncio
async def test_free_precheck_and_deduct(db, free_grant, monkeypatch):
    from bot.config import settings
    monkeypatch.setattr(settings, "MODELS", {
        "gpt-image-2.5-flare": {
            "free": True,
            "cost": {"low": {"cost": 0.006, "tokens": 200}},
        },
    })
    monkeypatch.setattr(settings, "PROFIT_PERCENTAGE", 20.0)
    user = await _make_user(db, 803, tier="free", token_balance=1000)
    await db.commit()

    assert await user_svc.can_generate(db, user) is True
    await user_svc.deduct_tokens(db, user, 200)
    assert user.token_balance == 760
    assert await user_svc.can_generate(db, user) is True
    await user_svc.deduct_tokens(db, user, 800)
    assert user.token_balance == 0
    assert await user_svc.can_generate(db, user) is False


@pytest.mark.asyncio
async def test_reset_all_daily_refills_free_only(db, free_grant):
    free = await _make_user(db, 804, tier="free", token_balance=120)
    prem = await _make_user(db, 805, tier="silver", token_balance=5000)
    await db.commit()

    await user_svc.reset_all_daily(db)

    await db.refresh(free)
    await db.refresh(prem)
    assert free.token_balance == 1000
    assert prem.token_balance == 5000


@pytest.mark.asyncio
async def test_set_tier_free_grants(db, free_grant):
    user = await _make_user(db, 806, tier="bronze", token_balance=777)
    await db.commit()

    updated = await user_svc.set_tier(db, 806, "free")
    assert updated.tier == "free"
    assert updated.token_balance == 1000
