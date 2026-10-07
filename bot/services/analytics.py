"""Centralized analytics: event names, logging, funnel/retention queries.

All user-based metrics use COUNT(DISTINCT user_id) — repeated actions by
the same user never inflate conversion rates. All "today"/day-window
comparisons use Tehran calendar days converted to naive-UTC windows
(stored timestamps are naive UTC).
"""
import logging
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import settings
from bot.db.models import GeneratedImage, User, UserEvent
from bot.utils.timezone import tehran_day_utc_window, today_in_tehran

logger = logging.getLogger(__name__)


def is_admin(telegram_id: int) -> bool:
    return telegram_id in (settings.ADMIN_IDS or [])


def non_admin_criteria():
    """SQLAlchemy criteria excluding admin users. None when no admins configured."""
    if settings.ADMIN_IDS:
        return User.telegram_id.notin_(settings.ADMIN_IDS)
    return None


def exclude_admins(stmt):
    """Append admin exclusion to a select that joins (or selects from) User."""
    filt = non_admin_criteria()
    if filt is not None:
        return stmt.where(filt)
    return stmt

# Event names
USER_STARTED = "USER_STARTED"
FIRST_IMAGE_GENERATION_STARTED = "FIRST_IMAGE_GENERATION_STARTED"
IMAGE_GENERATION_STARTED = "IMAGE_GENERATION_STARTED"
IMAGE_GENERATION_SUCCESS = "IMAGE_GENERATION_SUCCESS"
IMAGE_GENERATION_FAILED = "IMAGE_GENERATION_FAILED"
FREE_LIMIT_REACHED = "FREE_LIMIT_REACHED"
PRICING_VIEWED = "PRICING_VIEWED"
PLAN_SELECTED = "PLAN_SELECTED"
PAYMENT_STARTED = "PAYMENT_STARTED"
PAYMENT_SUCCESS = "PAYMENT_SUCCESS"
BUY_SUBSCRIPTION_CLICKED = "BUY_SUBSCRIPTION_CLICKED"
HELP_VIEWED = "HELP_VIEWED"
FEATURE_USED = "FEATURE_USED"

RETENTION_EVENT = IMAGE_GENERATION_SUCCESS
RETENTION_OFFSETS = (1, 3, 7, 14, 30)


async def log_event(
    session: AsyncSession,
    user: User,
    event_type: str,
    meta: dict | None = None,
) -> None:
    """Log an analytics event. Never raises — analytics must not break the main flow.

    Admin actions are never logged so testing doesn't pollute reports.
    """
    if is_admin(user.telegram_id):
        return
    try:
        session.add(UserEvent(user_id=user.id, event_type=event_type, event_meta=meta))
        await session.commit()
    except Exception:
        logger.exception("Failed to log event %s user=%d", event_type, user.telegram_id)
        try:
            await session.rollback()
        except Exception:
            pass


async def _has_event(session: AsyncSession, user_id: int, event_type: str) -> bool:
    result = await session.execute(
        select(func.count(UserEvent.id)).where(
            UserEvent.user_id == user_id,
            UserEvent.event_type == event_type,
        )
    )
    return (result.scalar() or 0) > 0


async def _has_event_since(
    session: AsyncSession, user_id: int, event_type: str, start
) -> bool:
    result = await session.execute(
        select(func.count(UserEvent.id)).where(
            UserEvent.user_id == user_id,
            UserEvent.event_type == event_type,
            UserEvent.created_at >= start,
        )
    )
    return (result.scalar() or 0) > 0


async def ensure_user_started(session: AsyncSession, user: User) -> None:
    """Log USER_STARTED once per user ever (repeat /start is not a new user)."""
    if not await _has_event(session, user.id, USER_STARTED):
        await log_event(session, user, USER_STARTED)


async def maybe_log_first_generation_start(session: AsyncSession, user: User) -> None:
    """Log FIRST_IMAGE_GENERATION_STARTED once per user (before their first success)."""
    if not await _has_event(session, user.id, IMAGE_GENERATION_SUCCESS):
        if not await _has_event(session, user.id, FIRST_IMAGE_GENERATION_STARTED):
            await log_event(session, user, FIRST_IMAGE_GENERATION_STARTED)


async def maybe_log_free_limit(session: AsyncSession, user: User) -> None:
    """Log FREE_LIMIT_REACHED at most once per user per day."""
    start, _ = tehran_day_utc_window(today_in_tehran())
    if not await _has_event_since(session, user.id, FREE_LIMIT_REACHED, start):
        await log_event(session, user, FREE_LIMIT_REACHED)


def _day_window(day: date):
    return tehran_day_utc_window(day)


async def _distinct_users_in_window(
    session: AsyncSession, event_type: str, day: date
) -> int:
    start, end = _day_window(day)
    stmt = (
        select(func.count(func.distinct(UserEvent.user_id)))
        .join(User, UserEvent.user_id == User.id)
        .where(
            UserEvent.event_type == event_type,
            UserEvent.created_at >= start,
            UserEvent.created_at < end,
        )
    )
    result = await session.execute(exclude_admins(stmt))
    return result.scalar() or 0


async def _distinct_users_ever(session: AsyncSession, event_type: str) -> int:
    stmt = (
        select(func.count(func.distinct(UserEvent.user_id)))
        .join(User, UserEvent.user_id == User.id)
        .where(UserEvent.event_type == event_type)
    )
    result = await session.execute(exclude_admins(stmt))
    return result.scalar() or 0


async def _event_count_in_window(session: AsyncSession, event_type: str, day: date) -> int:
    start, end = _day_window(day)
    stmt = (
        select(func.count(UserEvent.id))
        .join(User, UserEvent.user_id == User.id)
        .where(
            UserEvent.event_type == event_type,
            UserEvent.created_at >= start,
            UserEvent.created_at < end,
        )
    )
    result = await session.execute(exclude_admins(stmt))
    return result.scalar() or 0


async def get_new_users_today(session: AsyncSession) -> int:
    start, end = _day_window(today_in_tehran())
    stmt = select(func.count(User.id)).where(
        User.created_at >= start, User.created_at < end
    )
    result = await session.execute(exclude_admins(stmt))
    return result.scalar() or 0


async def get_new_users_with_success_today(session: AsyncSession) -> tuple[int, int]:
    """Return (activated, new_users): new users today with ≥1 success image today."""
    today = today_in_tehran()
    start, end = _day_window(today)
    new_users = await get_new_users_today(session)
    stmt = (
        select(func.count(func.distinct(UserEvent.user_id)))
        .join(User, UserEvent.user_id == User.id)
        .where(
            UserEvent.event_type == IMAGE_GENERATION_SUCCESS,
            UserEvent.created_at >= start,
            UserEvent.created_at < end,
            User.created_at >= start,
            User.created_at < end,
        )
    )
    result = await session.execute(exclude_admins(stmt))
    return result.scalar() or 0, new_users


async def get_images_started_today(session: AsyncSession) -> int:
    return await _event_count_in_window(session, IMAGE_GENERATION_STARTED, today_in_tehran())


async def get_images_success_today(session: AsyncSession) -> int:
    return await _event_count_in_window(session, IMAGE_GENERATION_SUCCESS, today_in_tehran())


async def get_images_failed_today(session: AsyncSession) -> int:
    return await _event_count_in_window(session, IMAGE_GENERATION_FAILED, today_in_tehran())


async def get_free_limit_users_today(session: AsyncSession) -> int:
    return await _distinct_users_in_window(session, FREE_LIMIT_REACHED, today_in_tehran())


async def get_new_free_limit_users_today(session: AsyncSession) -> int:
    today = today_in_tehran()
    start, end = _day_window(today)
    stmt = (
        select(func.count(func.distinct(UserEvent.user_id)))
        .join(User, UserEvent.user_id == User.id)
        .where(
            UserEvent.event_type == FREE_LIMIT_REACHED,
            UserEvent.created_at >= start,
            UserEvent.created_at < end,
            User.created_at >= start,
            User.created_at < end,
        )
    )
    result = await session.execute(exclude_admins(stmt))
    return result.scalar() or 0


async def get_premium_clicks_today(session: AsyncSession) -> tuple[int, int]:
    """Return (total_clicks, unique_users) for Buy Subscription today."""
    today = today_in_tehran()
    total = await _event_count_in_window(session, BUY_SUBSCRIPTION_CLICKED, today)
    unique = await _distinct_users_in_window(session, BUY_SUBSCRIPTION_CLICKED, today)
    return total, unique


async def get_new_premium_clickers_today(session: AsyncSession) -> int:
    today = today_in_tehran()
    start, end = _day_window(today)
    stmt = (
        select(func.count(func.distinct(UserEvent.user_id)))
        .join(User, UserEvent.user_id == User.id)
        .where(
            UserEvent.event_type == BUY_SUBSCRIPTION_CLICKED,
            UserEvent.created_at >= start,
            UserEvent.created_at < end,
            User.created_at >= start,
            User.created_at < end,
        )
    )
    result = await session.execute(exclude_admins(stmt))
    return result.scalar() or 0


async def get_pricing_viewers_today(session: AsyncSession) -> int:
    return await _distinct_users_in_window(session, PRICING_VIEWED, today_in_tehran())


async def get_new_pricing_viewers_today(session: AsyncSession) -> int:
    today = today_in_tehran()
    start, end = _day_window(today)
    stmt = (
        select(func.count(func.distinct(UserEvent.user_id)))
        .join(User, UserEvent.user_id == User.id)
        .where(
            UserEvent.event_type == PRICING_VIEWED,
            UserEvent.created_at >= start,
            UserEvent.created_at < end,
            User.created_at >= start,
            User.created_at < end,
        )
    )
    result = await session.execute(exclude_admins(stmt))
    return result.scalar() or 0


async def get_plan_selection_today(session: AsyncSession) -> dict:
    """Return {plan: unique_user_count} for today's PLAN_SELECTED events."""
    start, end = _day_window(today_in_tehran())
    stmt = (
        select(UserEvent.user_id, UserEvent.event_meta)
        .join(User, UserEvent.user_id == User.id)
        .where(
            UserEvent.event_type == PLAN_SELECTED,
            UserEvent.created_at >= start,
            UserEvent.created_at < end,
        )
    )
    result = await session.execute(exclude_admins(stmt))
    per_plan: dict[str, set] = {}
    for user_id, meta in result.all():
        plan = (meta or {}).get("plan")
        if plan:
            per_plan.setdefault(plan, set()).add(user_id)
    return {plan: len(users) for plan, users in per_plan.items()}


async def get_payments_today(session: AsyncSession) -> tuple[int, int]:
    """Return (started_users, success_users) for today."""
    today = today_in_tehran()
    started = await _distinct_users_in_window(session, PAYMENT_STARTED, today)
    success = await _distinct_users_in_window(session, PAYMENT_SUCCESS, today)
    return started, success


async def get_purchasers_total(session: AsyncSession) -> int:
    return await _distinct_users_ever(session, PAYMENT_SUCCESS)


async def _intersection_count(
    session: AsyncSession, event_a: str, event_b: str
) -> int:
    admin_criteria = non_admin_criteria()

    def _users_with(event_type: str):
        stmt = (
            select(UserEvent.user_id)
            .join(User, UserEvent.user_id == User.id)
            .where(UserEvent.event_type == event_type)
        )
        if admin_criteria is not None:
            stmt = stmt.where(admin_criteria)
        return stmt.distinct().subquery()

    a = _users_with(event_a)
    b = _users_with(event_b)
    result = await session.execute(
        select(func.count()).select_from(a.join(b, a.c.user_id == b.c.user_id))
    )
    return result.scalar() or 0


def safe_rate(numerator: int, denominator: int) -> float:
    if not denominator:
        return 0.0
    return numerator / denominator


async def get_conversions(session: AsyncSession) -> dict:
    """All-time distinct-user conversion rates (0.0–1.0)."""
    result = await session.execute(exclude_admins(select(func.count(User.id))))
    total_users = result.scalar() or 0
    purchasers = await get_purchasers_total(session)
    limit_users = await _distinct_users_ever(session, FREE_LIMIT_REACHED)
    pricing_users = await _distinct_users_ever(session, PRICING_VIEWED)
    plan_users = await _distinct_users_ever(session, PLAN_SELECTED)
    pay_started_users = await _distinct_users_ever(session, PAYMENT_STARTED)
    limit_buyers = await _intersection_count(session, FREE_LIMIT_REACHED, PAYMENT_SUCCESS)
    pricing_buyers = await _intersection_count(session, PRICING_VIEWED, PAYMENT_SUCCESS)
    return {
        "user_buyer": safe_rate(purchasers, total_users),
        "limit_buyer": safe_rate(limit_buyers, limit_users),
        "pricing_buyer": safe_rate(pricing_buyers, pricing_users),
        "plan_payment": safe_rate(pay_started_users, plan_users),
        "payment_success": safe_rate(purchasers, pay_started_users),
    }


async def get_retention(
    session: AsyncSession, cohort_day: date, offset_days: int
) -> tuple[int, int, float]:
    """Return (retained, cohort_size, rate) for a cohort.

    Cohort = users whose first entry (User.created_at) falls on cohort_day
    (Tehran). Retained = cohort users with ≥1 IMAGE_GENERATION_SUCCESS on
    cohort_day + offset_days (Tehran). Each user counts once.
    """
    c_start, c_end = _day_window(cohort_day)
    target = cohort_day + timedelta(days=offset_days)
    t_start, t_end = _day_window(target)

    cohort_q = await session.execute(
        exclude_admins(
            select(User.id).where(User.created_at >= c_start, User.created_at < c_end)
        )
    )
    cohort_ids = [row[0] for row in cohort_q.all()]
    if not cohort_ids:
        return 0, 0, 0.0

    retained_q = await session.execute(
        select(func.count(func.distinct(UserEvent.user_id))).where(
            UserEvent.user_id.in_(cohort_ids),
            UserEvent.event_type == RETENTION_EVENT,
            UserEvent.created_at >= t_start,
            UserEvent.created_at < t_end,
        )
    )
    retained = retained_q.scalar() or 0
    return retained, len(cohort_ids), safe_rate(retained, len(cohort_ids))


async def get_retention_overview(session: AsyncSession) -> dict[int, float]:
    """D1/D3/D7/D14/D30 rates for the most recent complete cohort of each window."""
    today = today_in_tehran()
    out: dict[int, float] = {}
    for offset in RETENTION_OFFSETS:
        _, _, rate = await get_retention(session, today - timedelta(days=offset), offset)
        out[offset] = rate
    return out


async def get_generated_images_count_today(session: AsyncSession) -> int:
    start, end = _day_window(today_in_tehran())
    stmt = (
        select(func.count(GeneratedImage.id))
        .join(User, GeneratedImage.user_id == User.id)
        .where(
            GeneratedImage.created_at >= start, GeneratedImage.created_at < end
        )
    )
    result = await session.execute(exclude_admins(stmt))
    return result.scalar() or 0
