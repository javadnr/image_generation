"""Tests for the generate-confirmation flow (latest-prompt-wins + atomic claim)."""
import asyncio

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool

from bot.db.models import Base, User
from bot.services.user import (
    get_or_create_user,
    set_generating,
    set_pending_prompt,
    clear_pending_prompt,
    claim_pending_prompt,
)


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


async def _make_user(session, telegram_id=9001, tier="free", token_balance=10000):
    user = await get_or_create_user(session, telegram_id)
    user.tier = tier
    user.token_balance = token_balance
    await session.commit()
    return user


async def _pending_of(session, telegram_id):
    result = await session.execute(
        select(User.pending_prompt, User.is_generating).where(
            User.telegram_id == telegram_id
        )
    )
    return result.first()


@pytest.mark.asyncio
async def test_claim_returns_latest_prompt(db):
    await _make_user(db, 9101)
    await set_pending_prompt(db, await get_or_create_user(db, 9101), "prompt A")
    user = await get_or_create_user(db, 9101)
    await set_pending_prompt(db, user, "prompt B")

    prompt, status = await claim_pending_prompt(db, 9101)
    assert status == "ok"
    assert prompt == "prompt B"

    row = await _pending_of(db, 9101)
    assert row[0] is None  # pending cleared on claim
    assert row[1] is True  # lock held


@pytest.mark.asyncio
async def test_second_claim_while_running_reports_busy(db):
    await _make_user(db, 9102)
    user = await get_or_create_user(db, 9102)
    await set_pending_prompt(db, user, "prompt A")

    prompt, status = await claim_pending_prompt(db, 9102)
    assert (prompt, status) == ("prompt A", "ok")

    # Same session, stale in-memory state: second claim must lose.
    prompt2, status2 = await claim_pending_prompt(db, 9102)
    assert prompt2 is None
    assert status2 == "busy"


@pytest.mark.asyncio
async def test_claim_after_release_reports_empty(db):
    await _make_user(db, 9103)
    user = await get_or_create_user(db, 9103)
    await set_pending_prompt(db, user, "prompt A")

    await claim_pending_prompt(db, 9103)
    await set_generating(db, user, False)

    prompt, status = await claim_pending_prompt(db, 9103)
    assert prompt is None
    assert status == "empty"


@pytest.mark.asyncio
async def test_cancel_clears_pending(db):
    await _make_user(db, 9104)
    user = await get_or_create_user(db, 9104)
    await set_pending_prompt(db, user, "prompt A")

    assert await clear_pending_prompt(db, 9104) is True
    assert await clear_pending_prompt(db, 9104) is False

    prompt, status = await claim_pending_prompt(db, 9104)
    assert (prompt, status) == (None, "empty")


@pytest.mark.asyncio
async def test_claim_busy_keeps_pending(db):
    await _make_user(db, 9105)
    user = await get_or_create_user(db, 9105)
    await set_pending_prompt(db, user, "prompt A")
    await set_generating(db, user, True)

    prompt, status = await claim_pending_prompt(db, 9105)
    assert (prompt, status) == (None, "busy")

    row = await _pending_of(db, 9105)
    assert row[0] == "prompt A"  # untouched by the failed claim


@pytest.mark.asyncio
async def test_claim_unknown_user_reports_empty(db):
    prompt, status = await claim_pending_prompt(db, 999999)
    assert (prompt, status) == (None, "empty")


@pytest.mark.asyncio
async def test_second_session_sees_busy(db):
    await _make_user(db, 9106)
    user = await get_or_create_user(db, 9106)
    await set_pending_prompt(db, user, "prompt A")

    factory = async_sessionmaker(db.bind, expire_on_commit=False)
    async with factory() as other:
        prompt, status = await claim_pending_prompt(other, 9106)
        assert (prompt, status) == ("prompt A", "ok")

    # First session holds a stale object; the bulk UPDATE still loses.
    prompt2, status2 = await claim_pending_prompt(db, 9106)
    assert prompt2 is None
    assert status2 == "busy"


def test_confirm_keyboard_and_texts():
    from bot.keyboards.inline import confirm_keyboard
    import bot.texts as texts

    kb = confirm_keyboard()
    buttons = [b for row in kb.inline_keyboard for b in row]
    assert [b.callback_data for b in buttons] == ["confirm_yes", "confirm_no"]
    assert all(b.text for b in buttons)
    assert texts.CONFIRM_ASK and texts.CONFIRM_PROGRESS
    assert texts.CONFIRM_EMPTY and texts.CONFIRM_BUSY
    assert isinstance(texts.CONFIRM_PROMPT_MAX, int)


def test_revision_chain_valid():
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    cfg = Config("alembic.ini")
    cfg.set_main_option("script_location", "alembic")
    script = ScriptDirectory.from_config(cfg)
    assert script.get_heads() == ["0004_image_size"]
    rev = script.get_revision("0004_image_size")
    assert rev.down_revision == "0003_pending_prompt"
