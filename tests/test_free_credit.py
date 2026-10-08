import asyncio
from datetime import date, timedelta

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


async def _make_user(session, telegram_id, tier="free", daily_used=0, last_reset=None):
    user = User(
        telegram_id=telegram_id,
        tier=tier,
        daily_used=daily_used,
        last_reset_date=last_reset or date.today(),
    )
    session.add(user)
    await session.flush()
    return user


@pytest.mark.asyncio
async def test_free_credit_never_resets(db):
    yesterday = date.today() - timedelta(days=1)
    user = await _make_user(db, 801, tier="free", daily_used=2, last_reset=yesterday)
    await db.commit()

    user = await user_svc.check_and_reset_daily(db, user)
    assert user.daily_used == 2
    assert not await user_svc.can_generate(db, user)


@pytest.mark.asyncio
async def test_free_credit_usable_until_spent(db):
    user = await _make_user(db, 802, tier="free", daily_used=0)
    await db.commit()

    assert await user_svc.can_generate(db, user)
    await user_svc.consume_quota(db, user)
    assert await user_svc.can_generate(db, user)


@pytest.mark.asyncio
async def test_premium_still_resets_daily(db):
    yesterday = date.today() - timedelta(days=1)
    user = await _make_user(db, 803, tier="bronze", daily_used=10, last_reset=yesterday)
    await db.commit()

    user = await user_svc.check_and_reset_daily(db, user)
    assert user.daily_used == 0
    assert await user_svc.can_generate(db, user)


@pytest.mark.asyncio
async def test_reset_all_daily_skips_free(db):
    yesterday = date.today() - timedelta(days=1)
    free = await _make_user(db, 804, tier="free", daily_used=2, last_reset=yesterday)
    prem = await _make_user(db, 805, tier="silver", daily_used=25, last_reset=yesterday)
    await db.commit()

    await user_svc.reset_all_daily(db)

    await db.refresh(free)
    await db.refresh(prem)
    assert free.daily_used == 2
    assert prem.daily_used == 0
