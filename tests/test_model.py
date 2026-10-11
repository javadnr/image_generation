import asyncio
import base64
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool

from bot.db.models import Base, User
from bot.keyboards.inline import model_keyboard
from bot.services import user as user_svc
from bot.services import models as models_svc

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
    },
}


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
    return TEST_MODELS


def _texts(kb):
    return [btn.text for row in kb.inline_keyboard for btn in row]


def _callbacks(kb):
    return [btn.callback_data for row in kb.inline_keyboard for btn in row]


def test_catalog_helpers(catalog):
    assert models_svc.model_ids() == [
        "gpt-image-2.5-flare", "gpt-image-2.5-sunburst",
    ]
    assert models_svc.is_free_model("gpt-image-2.5-flare") is True
    assert models_svc.is_free_model("gpt-image-2.5-sunburst") is False
    assert models_svc.default_model() == "gpt-image-2.5-flare"
    assert models_svc.model_cost("gpt-image-2.5-flare", "low") == (0.006, 200)
    assert models_svc.model_cost("gpt-image-2.5-flare", "high") == (0.0266, 1760)
    assert models_svc.model_cost("gpt-image-2.5-sunburst", "low") == (None, None)
    assert models_svc.model_cost("unknown", "low") == (None, None)


def test_fallback_when_env_empty(monkeypatch):
    from bot.config import settings
    monkeypatch.setattr(settings, "MODELS", {})
    assert models_svc.model_ids() == [
        "gpt-image-2.5-flare", "gpt-image-2.5-sunburst",
    ]
    assert models_svc.default_model() == "gpt-image-2.5-flare"
    assert models_svc.model_cost("gpt-image-2.5-flare", "medium") == (0.0133, 443)


@pytest.mark.asyncio
async def test_model_defaults_to_first_free(db, catalog):
    user = User(telegram_id=911)
    db.add(user)
    await db.flush()
    await db.refresh(user)
    # column default is flare; catalog default is first free model
    assert user.image_model in ("gpt-image-2.5-flare",)
    assert models_svc.default_model() == "gpt-image-2.5-flare"


@pytest.mark.asyncio
async def test_set_model_persists_and_rejects_invalid(db, catalog):
    user = User(telegram_id=912)
    db.add(user)
    await db.flush()

    await user_svc.set_model(db, user, "gpt-image-2.5-sunburst")
    assert user.image_model == "gpt-image-2.5-sunburst"

    with pytest.raises(ValueError):
        await user_svc.set_model(db, user, "dall-e-3")


def test_free_user_keyboard_tick_and_lock(catalog):
    kb = model_keyboard("free", "gpt-image-2.5-flare")
    texts = _texts(kb)
    assert texts[0].startswith("✅ ")
    assert texts[1].startswith("🔒 ")
    assert _callbacks(kb) == [
        "model:gpt-image-2.5-flare",
        "model:gpt-image-2.5-sunburst",
    ]


def test_premium_keyboard_tick_no_locks(catalog):
    kb = model_keyboard("gold", "gpt-image-2.5-sunburst")
    texts = _texts(kb)
    assert not texts[0].startswith("✅ ")
    assert texts[1].startswith("✅ ")
    assert not any(t.startswith("🔒 ") for t in texts)


@pytest.mark.asyncio
async def test_generate_passes_model_through(catalog):
    pytest.importorskip("openai")
    from bot.services import image as image_svc

    raw = base64.b64encode(b"fakepng").decode()
    fake_result = SimpleNamespace(
        data=[SimpleNamespace(b64_json=raw, url=None)],
        usage={"total_tokens": 7},
    )
    with patch.object(image_svc, "client") as mock_client:
        mock_client.images.generate = AsyncMock(return_value=fake_result)
        await image_svc.generate_image(
            "a cat", "free", 1024, 1024,
            quality="low", model="gpt-image-2.5-sunburst",
        )

    _, kwargs = mock_client.images.generate.call_args
    assert kwargs["model"] == "gpt-image-2.5-sunburst"


@pytest.mark.asyncio
async def test_generate_falls_back_to_tier_model(catalog):
    pytest.importorskip("openai")
    from bot.services import image as image_svc

    raw = base64.b64encode(b"fakepng").decode()
    fake_result = SimpleNamespace(
        data=[SimpleNamespace(b64_json=raw, url=None)],
        usage={"total_tokens": 7},
    )
    with patch.object(image_svc, "client") as mock_client:
        mock_client.images.generate = AsyncMock(return_value=fake_result)
        await image_svc.generate_image("a cat", "free", 1024, 1024, model=None)

    _, kwargs = mock_client.images.generate.call_args
    assert kwargs["model"] == image_svc.TIER_MODELS["free"]
