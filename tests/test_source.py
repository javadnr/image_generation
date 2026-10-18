"""Ad-platform attribution via /start <platform> deep links."""
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


# ---------- sanitization / first-touch ----------

@pytest.mark.asyncio
async def test_record_source_stores_token(db):
    user = await user_svc.get_or_create_user(db, 9401)
    await user_svc.record_source(db, user, "instagram")
    await db.refresh(user)
    assert user.source == "instagram"


@pytest.mark.asyncio
async def test_record_source_is_case_insensitive(db):
    user = await user_svc.get_or_create_user(db, 9402)
    await user_svc.record_source(db, user, "YouTube")
    await db.refresh(user)
    assert user.source == "youtube"


@pytest.mark.asyncio
async def test_first_touch_wins(db):
    user = await user_svc.get_or_create_user(db, 9403)
    await user_svc.record_source(db, user, "instagram")
    await user_svc.record_source(db, user, "youtube")
    await db.refresh(user)
    assert user.source == "instagram"


@pytest.mark.asyncio
async def test_junk_payload_rejected(db):
    user = await user_svc.get_or_create_user(db, 9404)
    await user_svc.record_source(db, user, "a b c !!!")
    await db.refresh(user)
    assert user.source is None


@pytest.mark.asyncio
async def test_no_payload_is_noop(db):
    user = await user_svc.get_or_create_user(db, 9405)
    await user_svc.record_source(db, user, None)
    await db.refresh(user)
    assert user.source is None


@pytest.mark.asyncio
async def test_long_payload_truncated_to_valid(db):
    user = await user_svc.get_or_create_user(db, 9406)
    await user_svc.record_source(db, user, "a" * 50)
    await db.refresh(user)
    assert user.source == "a" * 20


# ---------- daily counts ----------

@pytest.mark.asyncio
async def test_source_counts_today(db):
    for tid, src in (
        (9501, "instagram"), (9502, "instagram"),
        (9503, "youtube"), (9504, "telegram"),
        (9505, "bale"), (9506, "twitter"), (9507, None),
    ):
        user = await user_svc.get_or_create_user(db, tid)
        user.source = src
    await db.commit()

    counts = await user_svc.get_source_counts_today(db)
    assert counts.get("instagram") == 2
    assert counts.get("youtube") == 1
    assert counts.get("telegram") == 1
    assert counts.get("bale") == 1
    assert counts.get("twitter") == 1
    assert counts.get("", 0) == 1


# ---------- admin status text ----------

def test_admin_stats_shows_source_section():
    import string
    import bot.texts as texts

    assert "منبع تبلیغ" in texts.ADMIN_STATS
    fields = [f for _, f, _, _ in string.Formatter().parse(texts.ADMIN_STATS) if f]
    dummy = {f: 0 for f in fields}
    dummy["status"] = "x"
    rendered = texts.ADMIN_STATS.format(**dummy)
    assert "اینستاگرام" in rendered and "نامشخص" in rendered


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

    msg = _StartMessage(9601, "/start instagram")
    await start_h.cmd_start(msg, db)

    user = await user_svc.get_or_create_user(db, 9601)
    assert user.source == "instagram"


@pytest.mark.asyncio
async def test_cmd_start_plain_has_no_source(db):
    from bot.handlers import start as start_h

    msg = _StartMessage(9602, "/start")
    await start_h.cmd_start(msg, db)

    user = await user_svc.get_or_create_user(db, 9602)
    assert user.source is None
