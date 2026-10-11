import asyncio
import base64
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool

from bot.db.models import Base, User
from bot.keyboards.inline import quality_keyboard
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


def _texts(kb):
    return [btn.text for row in kb.inline_keyboard for btn in row]


def _callbacks(kb):
    return [btn.callback_data for row in kb.inline_keyboard for btn in row]


@pytest.mark.asyncio
async def test_quality_defaults_to_low(db):
    user = User(telegram_id=901)
    db.add(user)
    await db.flush()
    await db.refresh(user)
    assert user.image_quality == "low"


@pytest.mark.asyncio
async def test_set_quality_persists_and_rejects_invalid(db):
    user = User(telegram_id=902)
    db.add(user)
    await db.flush()

    await user_svc.set_quality(db, user, "high")
    assert user.image_quality == "high"

    with pytest.raises(ValueError):
        await user_svc.set_quality(db, user, "ultra")


def test_free_user_keyboard_tick_and_locks():
    kb = quality_keyboard("free", "low")
    texts = _texts(kb)
    assert texts[0].startswith("✅ ")
    assert texts[1].startswith("🔒 ")
    assert texts[2].startswith("🔒 ")
    assert _callbacks(kb) == ["quality:low", "quality:medium", "quality:high"]


def test_premium_keyboard_tick_no_locks():
    kb = quality_keyboard("bronze", "medium")
    texts = _texts(kb)
    assert not texts[0].startswith("✅ ")
    assert texts[1].startswith("✅ ")
    assert not any(t.startswith("🔒 ") for t in texts)


@pytest.mark.asyncio
async def test_generate_passes_quality_through():
    pytest.importorskip("openai")
    from bot.services import image as image_svc

    raw = base64.b64encode(b"fakepng").decode()
    fake_result = SimpleNamespace(
        data=[SimpleNamespace(b64_json=raw, url=None)],
        usage={"total_tokens": 7},
    )
    with patch.object(image_svc, "client") as mock_client:
        mock_client.images.generate = AsyncMock(return_value=fake_result)
        data, tokens = await image_svc.generate_image("a cat", "free", 1024, 1024, quality="high")

    assert data == b"fakepng"
    assert tokens == 7
    _, kwargs = mock_client.images.generate.call_args
    assert kwargs["quality"] == "high"
