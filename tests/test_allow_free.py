"""ALLOW_FREE flag: backend gate + free-UI visibility.

ALLOW_FREE=true preserves the current free tier; ALLOW_FREE=false blocks
free generation on the backend (not just in the UI) and hides free-usage
text, without touching any stored balance.
"""
import asyncio
import sys
import types
from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool

from bot.db.models import Base
from bot.services.user import get_or_create_user, can_generate

TEST_MODELS = {
    "gpt-image-2.5-flare": {
        "label": "gpt-image-2.5-flare",
        "free": True,
        "per_million_cost": 30,
        "cost": {"low": {"cost": 0.006, "tokens": 200}},
    },
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
    monkeypatch.setattr(settings, "FREE_USAGE_TOKEN", 1000)
    yield


async def _make_user(session, telegram_id, tier="free", token_balance=10000):
    user = await get_or_create_user(session, telegram_id)
    user.tier = tier
    user.token_balance = token_balance
    await session.commit()
    return user


@pytest.fixture
def generate_handler(monkeypatch):
    """Import bot.handlers.generate, stubbing the optional openai dep."""
    if "openai" not in sys.modules:
        stub = types.ModuleType("openai")

        class _Client:
            def __init__(self, *a, **k):
                pass

        stub.AsyncOpenAI = _Client
        monkeypatch.setitem(sys.modules, "openai", stub)
    from bot.handlers import generate as generate_h
    return generate_h


class _FakeMessage:
    """Minimal Message stand-in capturing replies."""

    def __init__(self, user_id, text="a cat"):
        self.from_user = SimpleNamespace(id=user_id)
        self.text = text
        self.calls = []

    async def answer(self, text=None, reply_markup=None, **kwargs):
        self.calls.append(text)
        return SimpleNamespace(chat=SimpleNamespace(id=self.from_user.id))


# ---------- backend gate ----------

@pytest.mark.asyncio
async def test_free_blocked_on_backend_when_disabled(db, catalog, monkeypatch):
    from bot.config import settings
    monkeypatch.setattr(settings, "ALLOW_FREE", False)
    user = await _make_user(db, 9301, tier="free", token_balance=99999)
    assert await can_generate(db, user) is False


@pytest.mark.asyncio
async def test_free_allowed_on_backend_when_enabled(db, catalog, monkeypatch):
    from bot.config import settings
    monkeypatch.setattr(settings, "ALLOW_FREE", True)
    user = await _make_user(db, 9302, tier="free", token_balance=10000)
    assert await can_generate(db, user) is True


@pytest.mark.asyncio
async def test_paid_plan_unaffected_by_flag(db, catalog, monkeypatch):
    from bot.config import settings
    monkeypatch.setattr(settings, "ALLOW_FREE", False)
    user = await _make_user(db, 9303, tier="gold", token_balance=10000)
    assert await can_generate(db, user) is True


@pytest.mark.asyncio
async def test_disabled_does_not_erase_balance(db, catalog, monkeypatch):
    from bot.config import settings
    monkeypatch.setattr(settings, "ALLOW_FREE", False)
    user = await _make_user(db, 9304, tier="free", token_balance=777)
    await can_generate(db, user)
    await db.refresh(user)
    assert user.token_balance == 777


# ---------- UI bypass: invoking the handler directly ----------

@pytest.mark.asyncio
async def test_handle_generate_refuses_bypass(db, catalog, monkeypatch, generate_handler):
    from bot.config import settings
    generate_h = generate_handler
    monkeypatch.setattr(settings, "ALLOW_FREE", False)

    user = await _make_user(db, 9305, tier="free", token_balance=99999)
    msg = _FakeMessage(9305, text="draw a dragon")

    await generate_h.handle_generate(msg, db)

    joined = "\n".join(c for c in msg.calls if c)
    assert "غیرفعال" in joined  # FREE_DISABLED shown
    await db.refresh(user)
    assert user.pending_prompt is None  # never queued for generation


@pytest.mark.asyncio
async def test_handle_generate_proceeds_when_enabled(db, catalog, monkeypatch, generate_handler):
    from bot.config import settings
    generate_h = generate_handler
    monkeypatch.setattr(settings, "ALLOW_FREE", True)

    user = await _make_user(db, 9306, tier="free", token_balance=10000)
    msg = _FakeMessage(9306, text="draw a cat")

    await generate_h.handle_generate(msg, db)

    await db.refresh(user)
    assert user.pending_prompt == "draw a cat"  # normal flow preserved


@pytest.mark.asyncio
async def test_generate_prompt_button_blocked_when_disabled(db, catalog, monkeypatch, generate_handler):
    from bot.config import settings
    generate_h = generate_handler
    monkeypatch.setattr(settings, "ALLOW_FREE", False)

    await _make_user(db, 9307, tier="free", token_balance=99999)
    msg = _FakeMessage(9307)
    await generate_h.generate_prompt(msg, db)

    joined = "\n".join(c for c in msg.calls if c)
    assert "غیرفعال" in joined


@pytest.mark.asyncio
async def test_balance_blocked_when_disabled(db, catalog, monkeypatch):
    from bot.config import settings
    from bot.handlers import balance as balance_h
    monkeypatch.setattr(settings, "ALLOW_FREE", False)

    await _make_user(db, 9308, tier="free", token_balance=99999)
    msg = _FakeMessage(9308)
    await balance_h.balance(msg, db)

    joined = "\n".join(c for c in msg.calls if c)
    assert "غیرفعال" in joined


# ---------- free-usage text visibility ----------

def test_premium_text_hides_free_block_when_disabled(catalog, monkeypatch):
    from bot.config import settings
    from bot.handlers import premium as premium_h
    user = SimpleNamespace(tier="free")

    monkeypatch.setattr(settings, "ALLOW_FREE", False)
    assert "پلن رایگان" not in premium_h.premium_text(user, {})

    monkeypatch.setattr(settings, "ALLOW_FREE", True)
    assert "پلن رایگان" in premium_h.premium_text(user, {})


def test_free_disabled_text_requires_paid_plan():
    import bot.texts as texts
    assert "غیرفعال" in texts.FREE_DISABLED
    assert "پریمیوم" in texts.FREE_DISABLED
