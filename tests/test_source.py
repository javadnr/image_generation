"""Fully dynamic acquisition-source tracking via /start deep links."""
import asyncio
from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool

from bot.db.models import Base
from bot.services import user as user_svc


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


async def _user_with_source(session, telegram_id, source):
    user = await user_svc.get_or_create_user(session, telegram_id)
    user.source = source
    return user


# ---------- parameter normalization (dynamic, case-preserving) ----------

def test_normalize_accepts_any_valid_payload():
    assert user_svc.normalize_source("Instagram") == "Instagram"
    assert user_svc.normalize_source("Aparat") == "Aparat"
    assert user_svc.normalize_source("YouTube") == "YouTube"
    assert user_svc.normalize_source("X") == "X"
    assert user_svc.normalize_source("XWY") == "XWY"
    assert user_svc.normalize_source("campaign_2026-ad") == "campaign_2026-ad"


def test_normalize_trims_whitespace():
    assert user_svc.normalize_source("  youtube  ") == "youtube"


def test_normalize_rejects_malformed():
    assert user_svc.normalize_source(None) is None
    assert user_svc.normalize_source("") is None
    assert user_svc.normalize_source("   ") is None
    assert user_svc.normalize_source("a b") is None
    assert user_svc.normalize_source("bad!token") is None
    assert user_svc.normalize_source("a" * 65) is None  # > Telegram max


def test_normalize_accepts_max_length():
    assert user_svc.normalize_source("a" * 64) == "a" * 64


# ---------- registration + first-touch preservation ----------

@pytest.mark.asyncio
async def test_record_source_stores_arbitrary_value(db):
    user = await user_svc.get_or_create_user(db, 9401)
    await user_svc.record_source(db, user, "XWY")
    await db.refresh(user)
    assert user.source == "XWY"


@pytest.mark.asyncio
async def test_record_source_preserves_case(db):
    user = await user_svc.get_or_create_user(db, 9402)
    await user_svc.record_source(db, user, "Aparat")
    await db.refresh(user)
    assert user.source == "Aparat"


@pytest.mark.asyncio
async def test_first_touch_wins_on_repeat_start(db):
    user = await user_svc.get_or_create_user(db, 9403)
    await user_svc.record_source(db, user, "X")
    await user_svc.record_source(db, user, "Aparat")
    await db.refresh(user)
    assert user.source == "X"


@pytest.mark.asyncio
async def test_malformed_payload_leaves_source_null(db):
    user = await user_svc.get_or_create_user(db, 9404)
    await user_svc.record_source(db, user, "not valid!")
    await db.refresh(user)
    assert user.source is None


@pytest.mark.asyncio
async def test_no_payload_leaves_source_null(db):
    user = await user_svc.get_or_create_user(db, 9405)
    await user_svc.record_source(db, user, None)
    await db.refresh(user)
    assert user.source is None


@pytest.mark.asyncio
async def test_repeat_start_does_not_duplicate_user(db):
    first = await user_svc.get_or_create_user(db, 9407)
    await user_svc.record_source(db, first, "YouTube")
    second = await user_svc.get_or_create_user(db, 9407)
    await user_svc.record_source(db, second, "X")
    assert first.id == second.id
    await db.refresh(second)
    assert second.source == "YouTube"


# ---------- dynamic stats: all-time + today ----------

@pytest.mark.asyncio
async def test_source_stats_all_time_and_today(db):
    for tid, src in (
        (9501, "Aparat"), (9502, "Aparat"), (9503, "Aparat"), (9504, "Aparat"),
        (9505, "YouTube"), (9506, "YouTube"),
        (9507, "X"), (9508, "X"), (9509, "X"),
        (9510, "XWY"),
        (9511, None),  # direct / unknown
    ):
        await _user_with_source(db, tid, src)
    await db.commit()

    stats = await user_svc.get_source_stats(db)
    by_source = {src: (total, today) for src, total, today in stats}

    # everyone registered "today" in this test
    assert by_source["Aparat"] == (4, 4)
    assert by_source["YouTube"] == (2, 2)
    assert by_source["X"] == (3, 3)
    assert by_source["XWY"] == (1, 1)
    assert by_source[None] == (1, 1)

    # sorted by all-time total desc
    totals = [total for _, total, _ in stats]
    assert totals == sorted(totals, reverse=True)


@pytest.mark.asyncio
async def test_source_with_history_but_none_today(db, monkeypatch):
    from datetime import datetime, timedelta
    from bot.services import user as us

    # one old user from months ago, one new user today
    old = await us.get_or_create_user(db, 9601)
    old.source = "X"
    old.created_at = datetime.utcnow() - timedelta(days=200)
    new = await us.get_or_create_user(db, 9602)
    new.source = "X"
    await db.commit()

    stats = await us.get_source_stats(db)
    by_source = {src: (total, today) for src, total, today in stats}
    assert by_source["X"] == (2, 1)

    # a source with only historical users still appears with today = 0
    old2 = await us.get_or_create_user(db, 9603)
    old2.source = "Legacy"
    old2.created_at = datetime.utcnow() - timedelta(days=400)
    await db.commit()

    stats = await us.get_source_stats(db)
    by_source = {src: (total, today) for src, total, today in stats}
    assert by_source["Legacy"] == (1, 0)


# ---------- end-to-end: handler records the platform ----------

class _FakeBot:
    async def get_chat_member(self, **kwargs):
        raise RuntimeError("no channel in test")


class _StartMessage:
    def __init__(self, user_id, text):
        self.from_user = SimpleNamespace(id=user_id, username="u")
        self.text = text
        self.bot = _FakeBot()
        self.answers = []

    async def answer(self, text=None, reply_markup=None, **kwargs):
        self.answers.append(text)


@pytest.mark.asyncio
async def test_cmd_start_records_platform(db):
    from bot.handlers import start as start_h

    msg = _StartMessage(9701, "/start instagram")
    await start_h.cmd_start(msg, db)

    user = await user_svc.get_or_create_user(db, 9701)
    assert user.source == "instagram"


@pytest.mark.asyncio
async def test_cmd_start_plain_has_no_source(db):
    from bot.handlers import start as start_h

    msg = _StartMessage(9702, "/start")
    await start_h.cmd_start(msg, db)

    user = await user_svc.get_or_create_user(db, 9702)
    assert user.source is None


# ---------- admin status rendering ----------

@pytest.mark.asyncio
async def test_sources_block_renders_all_stats(db):
    from bot.handlers import admin as admin_h

    await _user_with_source(db, 9801, "YouTube")
    await _user_with_source(db, 9802, "Aparat")
    await db.commit()

    stats = await user_svc.get_source_stats(db)
    block = admin_h._sources_block(stats)
    assert "YouTube — کل: 1 | امروز: 1" in block
    assert "Aparat — کل: 1 | امروز: 1" in block


def test_sources_block_empty():
    from bot.handlers import admin as admin_h
    assert admin_h._sources_block([]) == "  —"


def test_admin_stats_template_has_source_placeholder():
    import string
    import bot.texts as texts

    assert "منابع جذب" in texts.ADMIN_STATS
    fields = [f for _, f, _, _ in string.Formatter().parse(texts.ADMIN_STATS) if f]
    assert "acquisition_sources" in fields
    dummy = {f: 0 for f in fields}
    dummy["status"] = "x"
    dummy["acquisition_sources"] = "—"
    rendered = texts.ADMIN_STATS.format(**dummy)
    assert "منابع جذب" in rendered
