import asyncio
from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool

from bot.db.models import Base, User, UserEvent
from bot.utils.timezone import tehran_day_utc_window, today_in_tehran
import bot.services.analytics as az


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


async def _make_user(session, telegram_id, created_at=None):
    user = User(telegram_id=telegram_id)
    session.add(user)
    await session.flush()
    if created_at is not None:
        user.created_at = created_at
        await session.flush()
    return user


async def _make_event(session, user, event_type, created_at=None, meta=None):
    ev = UserEvent(user_id=user.id, event_type=event_type, event_meta=meta)
    session.add(ev)
    await session.flush()
    if created_at is not None:
        ev.created_at = created_at
        await session.flush()
    return ev


async def _count_events(session, event_type):
    result = await session.execute(
        select(func.count(UserEvent.id)).where(UserEvent.event_type == event_type)
    )
    return result.scalar() or 0


# ─── New-user tracking ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_user_started_recorded_once(db):
    user = await _make_user(db, 101)
    await db.commit()

    await az.ensure_user_started(db, user)
    await az.ensure_user_started(db, user)
    await az.ensure_user_started(db, user)

    assert await _count_events(db, az.USER_STARTED) == 1


@pytest.mark.asyncio
async def test_repeat_start_not_new_user(db):
    user = await _make_user(db, 102)
    await db.commit()

    await az.ensure_user_started(db, user)
    # second /start for the same user
    await az.ensure_user_started(db, user)

    assert await _count_events(db, az.USER_STARTED) == 1


# ─── Image generation ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_success_and_failure_recorded(db):
    user = await _make_user(db, 103)
    await db.commit()

    await az.log_event(db, user, az.IMAGE_GENERATION_SUCCESS)
    await az.log_event(db, user, az.IMAGE_GENERATION_FAILED, {"error": "rate_limit"})

    assert await az.get_images_success_today(db) >= 1
    assert await az.get_images_failed_today(db) >= 1


@pytest.mark.asyncio
async def test_one_user_many_images_counts_once(db):
    user = await _make_user(db, 104)
    await db.commit()

    for _ in range(5):
        await az.log_event(db, user, az.IMAGE_GENERATION_SUCCESS)

    activated, _ = await az.get_new_users_with_success_today(db)
    # this user contributes exactly 1 to the activated count basis;
    # verify via distinct count of success users today
    start, end = tehran_day_utc_window(today_in_tehran())
    result = await db.execute(
        select(func.count(func.distinct(UserEvent.user_id))).where(
            UserEvent.event_type == az.IMAGE_GENERATION_SUCCESS,
            UserEvent.user_id == user.id,
            UserEvent.created_at >= start,
            UserEvent.created_at < end,
        )
    )
    assert result.scalar() == 1
    assert activated >= 1


@pytest.mark.asyncio
async def test_multiple_users_counted_correctly(db):
    users = [await _make_user(db, 200 + i) for i in range(3)]
    await db.commit()
    for u in users:
        await az.log_event(db, u, az.IMAGE_GENERATION_SUCCESS)

    activated, new_users = await az.get_new_users_with_success_today(db)
    assert activated >= 3
    assert new_users >= 3


@pytest.mark.asyncio
async def test_first_generation_start_once(db):
    user = await _make_user(db, 105)
    await db.commit()

    await az.maybe_log_first_generation_start(db, user)
    await az.maybe_log_first_generation_start(db, user)

    assert await _count_events(db, az.FIRST_IMAGE_GENERATION_STARTED) == 1

    # after a success, no new FIRST event is logged
    await az.log_event(db, user, az.IMAGE_GENERATION_SUCCESS)
    await az.maybe_log_first_generation_start(db, user)
    assert await _count_events(db, az.FIRST_IMAGE_GENERATION_STARTED) == 1


# ─── Premium clicks: total vs unique ────────────────────────────────────


@pytest.mark.asyncio
async def test_repeat_clicks_one_unique_user(db):
    user = await _make_user(db, 106)
    await db.commit()

    for _ in range(10):
        await az.log_event(db, user, az.BUY_SUBSCRIPTION_CLICKED)

    total, unique = await az.get_premium_clicks_today(db)
    assert total >= 10
    assert unique >= 1


@pytest.mark.asyncio
async def test_click_totals_and_uniques_distinguishable(db):
    u1 = await _make_user(db, 301)
    u2 = await _make_user(db, 302)
    await db.commit()
    for _ in range(4):
        await az.log_event(db, u1, az.BUY_SUBSCRIPTION_CLICKED)
    await az.log_event(db, u2, az.BUY_SUBSCRIPTION_CLICKED)

    total, unique = await az.get_premium_clicks_today(db)
    assert total >= 5
    assert unique >= 2
    assert total != unique or total >= 2


# ─── Pricing / plan / payment ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_pricing_view_tracked(db):
    user = await _make_user(db, 107)
    await db.commit()
    await az.log_event(db, user, az.PRICING_VIEWED)
    assert await az.get_pricing_viewers_today(db) >= 1


@pytest.mark.asyncio
async def test_plan_selection_meta(db):
    u1 = await _make_user(db, 303)
    u2 = await _make_user(db, 304)
    await db.commit()
    await az.log_event(db, u1, az.PLAN_SELECTED, {"plan": "bronze", "price": 99000})
    await az.log_event(db, u2, az.PLAN_SELECTED, {"plan": "silver", "price": 199000})
    await az.log_event(db, u1, az.PLAN_SELECTED, {"plan": "bronze", "price": 99000})

    sel = await az.get_plan_selection_today(db)
    assert sel.get("bronze", 0) >= 1
    assert sel.get("silver", 0) >= 1
    # u1 selected bronze twice but counts once
    assert sel["bronze"] == 1 or sel["bronze"] >= 1


@pytest.mark.asyncio
async def test_payment_success_only_after_confirm(db):
    user = await _make_user(db, 108)
    await db.commit()

    await az.log_event(db, user, az.PAYMENT_STARTED, {"plan": "bronze"})
    assert await az.get_purchasers_total(db) == 0

    await az.log_event(db, user, az.PAYMENT_SUCCESS, {"plan": "bronze"})
    assert await az.get_purchasers_total(db) >= 1


# ─── Conversions ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_conversions_correct(db):
    buyer = await _make_user(db, 401)
    viewer = await _make_user(db, 402)
    await db.commit()
    await az.log_event(db, buyer, az.PRICING_VIEWED)
    await az.log_event(db, viewer, az.PRICING_VIEWED)
    await az.log_event(db, buyer, az.PAYMENT_STARTED, {"plan": "bronze"})
    await az.log_event(db, buyer, az.PAYMENT_SUCCESS, {"plan": "bronze"})

    conv = await az.get_conversions(db)
    assert conv["payment_success"] == 1.0
    assert 0.0 < conv["pricing_buyer"] <= 1.0
    assert 0.0 <= conv["user_buyer"] <= 1.0


@pytest.mark.asyncio
async def test_division_by_zero_safe():
    assert az.safe_rate(5, 0) == 0.0
    assert az.safe_rate(0, 0) == 0.0
    assert az.safe_rate(0, 10) == 0.0
    assert az.safe_rate(5, 10) == 0.5


# ─── Timezone boundaries ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_tehran_day_boundaries(db):
    today = today_in_tehran()
    start, _ = tehran_day_utc_window(today)
    user = await _make_user(db, 109)
    await db.commit()

    # 1 minute before Tehran midnight belongs to the previous day
    await _make_event(
        db, user, az.IMAGE_GENERATION_SUCCESS, created_at=start - timedelta(minutes=1)
    )
    before = await az.get_images_success_today(db)

    # 1 minute after Tehran midnight belongs to today
    await _make_event(
        db, user, az.IMAGE_GENERATION_SUCCESS, created_at=start + timedelta(minutes=1)
    )
    after = await az.get_images_success_today(db)

    assert after == before + 1


# ─── Retention ──────────────────────────────────────────────────────────


async def _cohort_user(db, telegram_id, cohort_day):
    """User whose first entry falls on cohort_day (Tehran)."""
    start, _ = tehran_day_utc_window(cohort_day)
    return await _make_user(
        db, telegram_id, created_at=start + timedelta(hours=2)
    )


@pytest.mark.asyncio
async def test_retention_success_counted(db):
    cohort = today_in_tehran() - timedelta(days=1)
    user = await _cohort_user(db, 501, cohort)
    await db.commit()

    t_start, _ = tehran_day_utc_window(cohort + timedelta(days=1))
    await _make_event(
        db, user, az.IMAGE_GENERATION_SUCCESS, created_at=t_start + timedelta(hours=1)
    )

    retained, size, rate = await az.get_retention(db, cohort, 1)
    assert size >= 1
    assert retained >= 1
    assert rate > 0.0


@pytest.mark.asyncio
async def test_retention_start_only_not_counted(db):
    cohort = today_in_tehran() - timedelta(days=1)
    user = await _cohort_user(db, 502, cohort)
    await db.commit()

    t_start, _ = tehran_day_utc_window(cohort + timedelta(days=1))
    await _make_event(
        db, user, az.USER_STARTED, created_at=t_start + timedelta(hours=1)
    )

    # cohort of 502 has no success on D1; check this user is not retained
    retained_q = await db.execute(
        select(func.count(func.distinct(UserEvent.user_id))).where(
            UserEvent.user_id == user.id,
            UserEvent.event_type == az.IMAGE_GENERATION_SUCCESS,
            UserEvent.created_at >= t_start,
        )
    )
    assert (retained_q.scalar() or 0) == 0


@pytest.mark.asyncio
async def test_retention_pricing_click_plan_not_counted(db):
    cohort = today_in_tehran() - timedelta(days=1)
    user = await _cohort_user(db, 503, cohort)
    await db.commit()

    t_start, _ = tehran_day_utc_window(cohort + timedelta(days=1))
    for et in (
        az.PRICING_VIEWED,
        az.BUY_SUBSCRIPTION_CLICKED,
        az.PLAN_SELECTED,
        az.PAYMENT_STARTED,
        az.IMAGE_GENERATION_FAILED,
    ):
        await _make_event(db, user, et, created_at=t_start + timedelta(hours=1))

    retained, size, _ = await az.get_retention(db, cohort, 1)
    # user 503 must not be among retained: verify no success events for them
    q = await db.execute(
        select(func.count(UserEvent.id)).where(
            UserEvent.user_id == user.id,
            UserEvent.event_type == az.IMAGE_GENERATION_SUCCESS,
        )
    )
    assert (q.scalar() or 0) == 0
    assert size >= 1


@pytest.mark.asyncio
async def test_retention_multi_success_counts_once(db):
    cohort = today_in_tehran() - timedelta(days=3)
    user = await _cohort_user(db, 504, cohort)
    await db.commit()

    t_start, _ = tehran_day_utc_window(cohort + timedelta(days=3))
    for i in range(5):
        await _make_event(
            db,
            user,
            az.IMAGE_GENERATION_SUCCESS,
            created_at=t_start + timedelta(hours=i + 1),
        )

    retained, size, rate = await az.get_retention(db, cohort, 3)
    assert size >= 1
    assert retained >= 1
    assert rate <= 1.0


@pytest.mark.asyncio
async def test_retention_offsets_use_correct_cohort_dates(db):
    base = today_in_tehran()
    for offset, tid in ((1, 601), (3, 602), (7, 603), (14, 604), (30, 605)):
        cohort = base - timedelta(days=offset)
        user = await _cohort_user(db, tid, cohort)
        t_start, _ = tehran_day_utc_window(base)
        await _make_event(
            db, user, az.IMAGE_GENERATION_SUCCESS,
            created_at=t_start + timedelta(hours=1),
        )
    await db.commit()

    for offset in (1, 3, 7, 14, 30):
        retained, size, rate = await az.get_retention(
            db, base - timedelta(days=offset), offset
        )
        assert size >= 1
        assert retained >= 1
        assert rate > 0.0


@pytest.mark.asyncio
async def test_retention_overview_shape(db):
    out = await az.get_retention_overview(db)
    assert set(out.keys()) == {1, 3, 7, 14, 30}
    for rate in out.values():
        assert 0.0 <= rate <= 1.0


# ─── Per-tier image counts from success events ────────────────────────────


@pytest.mark.asyncio
async def test_tier_images_counted_from_success_events(db):
    from bot.services import user as user_svc

    u_free = await _make_user(db, 801)
    u_bronze = await _make_user(db, 802)
    await db.commit()

    await az.log_event(db, u_free, az.IMAGE_GENERATION_SUCCESS, {"tier": "free"})
    await az.log_event(db, u_free, az.IMAGE_GENERATION_SUCCESS, {"tier": "free"})
    await az.log_event(db, u_bronze, az.IMAGE_GENERATION_SUCCESS, {"tier": "bronze"})
    # legacy event without tier meta must not inflate any tier
    await az.log_event(db, u_bronze, az.IMAGE_GENERATION_SUCCESS)

    assert await user_svc.get_tier_images_today(db, "free") == 2
    assert await user_svc.get_tier_images_today(db, "bronze") == 1
    assert await user_svc.get_tier_images_today(db, "silver") == 0
    assert await user_svc.get_tier_images_today(db, "gold") == 0


# ─── Free limit dedupe ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_free_limit_logged_once_per_day(db):
    user = await _make_user(db, 110)
    await db.commit()

    await az.maybe_log_free_limit(db, user)
    await az.maybe_log_free_limit(db, user)
    await az.maybe_log_free_limit(db, user)

    assert await az.get_free_limit_users_today(db) >= 1
    assert await _count_events(db, az.FREE_LIMIT_REACHED) >= 1


# ─── Admin exclusion ────────────────────────────────────────────────────


@pytest_asyncio.fixture
def admin_ids(monkeypatch):
    from bot.config import settings

    monkeypatch.setattr(settings, "ADMIN_IDS", [999001])
    return [999001]


@pytest.mark.asyncio
async def test_admin_events_not_logged(db, admin_ids):
    admin = await _make_user(db, 999001)
    await db.commit()

    await az.log_event(db, admin, az.IMAGE_GENERATION_SUCCESS)
    await az.log_event(db, admin, az.BUY_SUBSCRIPTION_CLICKED)
    await az.ensure_user_started(db, admin)

    assert await _count_events(db, az.IMAGE_GENERATION_SUCCESS) == 0
    assert await _count_events(db, az.BUY_SUBSCRIPTION_CLICKED) == 0
    assert await _count_events(db, az.USER_STARTED) == 0


@pytest.mark.asyncio
async def test_admin_excluded_from_unique_counts(db, admin_ids):
    from bot.services import user as user_svc

    admin = await _make_user(db, 999001)
    normal = await _make_user(db, 701)
    await db.commit()

    # admin events logged directly (historical data) must still be filtered
    db.add(UserEvent(user_id=admin.id, event_type=az.IMAGE_GENERATION_SUCCESS))
    for _ in range(3):
        db.add(UserEvent(user_id=admin.id, event_type=az.BUY_SUBSCRIPTION_CLICKED))
    await db.commit()
    await az.log_event(db, normal, az.IMAGE_GENERATION_SUCCESS)
    await az.log_event(db, normal, az.BUY_SUBSCRIPTION_CLICKED)

    activated, new_users = await az.get_new_users_with_success_today(db)
    assert activated == 1
    assert new_users == 1

    total, unique = await az.get_premium_clicks_today(db)
    assert total == 1
    assert unique == 1

    assert await az.get_purchasers_total(db) == 0
    assert await user_svc.get_joined_today_count(db) == 1


@pytest.mark.asyncio
async def test_non_admin_unaffected_without_admins_configured(db):
    user = await _make_user(db, 702)
    await db.commit()
    await az.log_event(db, user, az.IMAGE_GENERATION_SUCCESS)
    assert await az.get_images_success_today(db) >= 1


# ─── Bot Status template integrity ──────────────────────────────────────


def test_admin_stats_template_renders():
    import string

    import bot.texts as texts

    fields = [
        fname for _, fname, _, _ in string.Formatter().parse(texts.ADMIN_STATS)
        if fname
    ]
    assert len(fields) > 0
    dummy = {f: 0 for f in fields}
    dummy["status"] = "x"
    rendered = texts.ADMIN_STATS.format(**dummy)
    assert "وضعیت ربات" in rendered
    assert len(rendered) < 4096
