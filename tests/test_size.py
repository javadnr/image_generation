import asyncio
import base64
import os
import tempfile
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool

from bot.db.models import Base, User
from bot.keyboards.inline import size_keyboard, quality_keyboard, settings_hub_keyboard
from bot.services import user as user_svc
from bot.services.models import (
    DEFAULT_IMAGE_SIZE, VALID_IMAGE_SIZES, IMAGE_SIZES,
    size_label, image_dimensions,
)


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def catalog(monkeypatch):
    from bot.config import settings
    monkeypatch.setattr(settings, "MODELS", {
        "gpt-image-2.5-flare": {
            "label": "gpt-image-2.5-flare",
            "free": True,
            "per_million_cost": 30,
            "cost": {"low": {"cost": 0.006, "tokens": 200}},
        },
    })
    yield


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


def test_size_catalog_complete():
    assert set(IMAGE_SIZES) == {"square", "portrait", "story", "landscape", "widescreen"}
    assert DEFAULT_IMAGE_SIZE == "square"
    assert set(VALID_IMAGE_SIZES) == set(IMAGE_SIZES)
    for key, entry in IMAGE_SIZES.items():
        assert entry["width"] % 64 == 0
        assert entry["height"] % 64 == 0
        assert max(entry["width"], entry["height"]) / min(entry["width"], entry["height"]) <= 16 / 9


def test_image_dimensions_mapping():
    assert image_dimensions("square") == (1024, 1024)
    assert image_dimensions("portrait") == (768, 1024)
    assert image_dimensions("story") == (576, 1024)
    assert image_dimensions("landscape") == (1024, 768)
    assert image_dimensions("widescreen") == (1024, 576)
    assert size_label("story") == "Story (9:16)"


def test_image_dimensions_unknown_raises():
    with pytest.raises(ValueError):
        image_dimensions("banana")
    with pytest.raises(ValueError):
        image_dimensions(None)


@pytest.mark.asyncio
async def test_size_defaults_to_square(db):
    user = User(telegram_id=921)
    db.add(user)
    await db.flush()
    await db.refresh(user)
    assert user.image_size == "square"


@pytest.mark.asyncio
async def test_set_size_persists_and_rejects_invalid(db):
    user = User(telegram_id=922)
    db.add(user)
    await db.flush()

    await user_svc.set_size(db, user, "story")
    assert user.image_size == "story"

    await user_svc.set_size(db, user, "square")
    assert user.image_size == "square"

    with pytest.raises(ValueError):
        await user_svc.set_size(db, user, "panorama")


@pytest.mark.asyncio
async def test_size_change_keeps_quality(db):
    user = User(telegram_id=923, image_quality="high", image_size="square")
    db.add(user)
    await db.flush()

    await user_svc.set_size(db, user, "landscape")
    assert user.image_size == "landscape"
    assert user.image_quality == "high"

    await user_svc.set_quality(db, user, "low")
    assert user.image_quality == "low"
    assert user.image_size == "landscape"


def test_size_keyboard_tick_and_callbacks():
    kb = size_keyboard("story", show_back=False)
    texts = _texts(kb)
    assert texts[0] == "Square (1:1)"
    assert texts[2] == "✅ Story (9:16)"
    assert _callbacks(kb) == [
        "size:square", "size:portrait", "size:story",
        "size:landscape", "size:widescreen",
    ]


def test_size_keyboard_back_row():
    kb_with = size_keyboard("square", show_back=True)
    cbs_with = _callbacks(kb_with)
    assert cbs_with[-1] == "settings_home"
    assert _texts(kb_with)[-1] == "⬅️ بازگشت"

    kb_without = size_keyboard("square", show_back=False)
    assert "settings_home" not in _callbacks(kb_without)


def test_quality_keyboard_back_defaults_off():
    kb = quality_keyboard("free", "low")
    assert "settings_home" not in _callbacks(kb)
    kb_back = quality_keyboard("free", "low", show_back=True)
    assert _callbacks(kb_back)[-1] == "settings_home"


def test_settings_hub_keyboard():
    kb = settings_hub_keyboard()
    assert _callbacks(kb) == ["settings_quality", "settings_size"]


@pytest.mark.asyncio
async def test_edit_passes_size_through(catalog):
    pytest.importorskip("openai")
    from bot.services import image as image_svc

    raw = base64.b64encode(b"fakepng").decode()
    fake_result = SimpleNamespace(
        data=[SimpleNamespace(b64_json=raw, url=None)],
        usage={"total_tokens": 7},
    )
    with patch.object(image_svc, "client") as mock_client:
        mock_client.images.edit = AsyncMock(return_value=fake_result)
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp.write(b"fakeinput")
            tmp_path = tmp.name
        try:
            await image_svc.edit_image(
                tmp_path, "make it sunny",
                model="gpt-image-2.5-flare", size="768x1024",
            )
        finally:
            os.unlink(tmp_path)

    _, kwargs = mock_client.images.edit.call_args
    assert kwargs["size"] == "768x1024"
    assert kwargs["model"] == "gpt-image-2.5-flare"
    assert "quality" not in kwargs


@pytest.mark.asyncio
async def test_edit_omits_size_when_none(catalog):
    pytest.importorskip("openai")
    from bot.services import image as image_svc

    raw = base64.b64encode(b"fakepng").decode()
    fake_result = SimpleNamespace(
        data=[SimpleNamespace(b64_json=raw, url=None)],
        usage={"total_tokens": 7},
    )
    with patch.object(image_svc, "client") as mock_client:
        mock_client.images.edit = AsyncMock(return_value=fake_result)
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp.write(b"fakeinput")
            tmp_path = tmp.name
        try:
            await image_svc.edit_image(tmp_path, "make it sunny")
        finally:
            os.unlink(tmp_path)

    _, kwargs = mock_client.images.edit.call_args
    assert "size" not in kwargs
    assert "quality" not in kwargs
