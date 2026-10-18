import logging
import re

from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession
from bot.db.models import User, UserEvent
from bot.config import settings
from bot.services.analytics import exclude_admins, IMAGE_GENERATION_SUCCESS
from bot.utils.timezone import tehran_day_utc_window, today_in_tehran

logger = logging.getLogger(__name__)


async def get_or_create_user(session: AsyncSession, telegram_id: int) -> User:
    result = await session.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()
    if user is None:
        user = User(telegram_id=telegram_id, token_balance=settings.FREE_USAGE_TOKEN)
        session.add(user)
        await session.commit()
        await session.refresh(user)
    return user


def free_generation_enabled() -> bool:
    """Whether free-tier users may generate at all (ALLOW_FREE env flag)."""
    return bool(settings.ALLOW_FREE)


# Ad-platform attribution. First-touch wins; the deep-link payload is
# sanitized to a short token so arbitrary junk never lands in the DB.
SOURCE_MAX_LEN = 20
_SOURCE_RE = re.compile(r"^[a-z0-9_-]{1,%d}$" % SOURCE_MAX_LEN)
# Friendly labels for the admin panel; unknown tokens fall back to raw text.
SOURCE_LABELS = {
    "instagram": "اینستاگرام",
    "youtube": "یوتیوب",
    "telegram": "تلگرام",
    "bale": "بله",
}


async def record_source(session: AsyncSession, user: User, payload: str | None) -> None:
    """Store the ad platform from '/start <payload>' on first touch only."""
    if user.source or not payload:
        return
    token = payload.strip().lower()[:SOURCE_MAX_LEN]
    if _SOURCE_RE.match(token):
        user.source = token
        await session.commit()
        logger.info("Source recorded: user=%d source=%s", user.telegram_id, token)


async def get_source_counts_today(session: AsyncSession) -> dict:
    """{source-or-'' : new-user count} for today (Tehran day), admins excluded."""
    start, end = tehran_day_utc_window(today_in_tehran())
    stmt = (
        select(User.source, func.count(User.id))
        .where(User.created_at >= start, User.created_at < end)
        .group_by(User.source)
    )
    result = await session.execute(exclude_admins(stmt))
    return {(src or ""): count for src, count in result.all()}


async def can_generate(session: AsyncSession, user: User) -> bool:
    """Unified pre-check for every tier.

    Free-tier users are blocked outright when ALLOW_FREE is off, regardless
    of their remaining free credits — the single backend choke point shared
    by every generation path.

    The minimum is the raw configured estimate for the selected model and
    quality (e.g. 200 for Low) — profit is NOT added here. Actual cost,
    including profit, is deducted afterwards and may exceed the balance,
    flooring it at zero.
    """
    from bot.services.models import estimate_tokens, default_model
    if user.tier == "free" and not free_generation_enabled():
        return False
    required = estimate_tokens(
        user.image_model or default_model(),
        user.image_quality or "low",
    )
    if required is None:
        logger.warning(
            "No token estimate for model=%s quality=%s; allowing generation",
            user.image_model, user.image_quality,
        )
        return True
    return (user.token_balance or 0) >= required


async def deduct_tokens(session: AsyncSession, user: User, amount: int | None) -> int:
    """Deduct actual API usage plus profit, applied exactly once.

    Floors the balance at zero. Returns remaining token balance.
    """
    from bot.services.models import charge_for
    if amount is None:
        logger.warning("No usage reported for user=%d; deducting 0", user.telegram_id)
    charged = charge_for(amount)
    user.token_balance = max(0, (user.token_balance or 0) - charged)
    await session.commit()
    return user.token_balance


def get_edit_cost() -> int:
    return settings.IMAGE_EDIT_COST_TOKENS


def has_edit_balance(user: User) -> bool:
    """Premium-only gate helper: enough balance for one fixed-cost edit."""
    if user.tier == "free":
        return False
    return (user.token_balance or 0) >= get_edit_cost()


async def set_tier(session: AsyncSession, telegram_id: int, tier: str) -> User | None:
    from bot.services.models import plan_allowance
    result = await session.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()
    if user:
        user.tier = tier
        user.token_balance = (
            plan_allowance(tier) if tier != "free" else settings.FREE_USAGE_TOKEN
        )
        await session.commit()
        await session.refresh(user)
        logger.info(
            "Tier set by admin: user=%d tier=%s balance=%d",
            telegram_id, tier, user.token_balance,
        )
    return user


async def set_generating(session: AsyncSession, user: User, value: bool) -> None:
    user.is_generating = value
    await session.commit()


async def set_pending_prompt(session: AsyncSession, user: User, prompt: str) -> None:
    user.pending_prompt = prompt
    await session.commit()


async def clear_pending_prompt(session: AsyncSession, telegram_id: int) -> bool:
    """Clear the pending prompt. Returns True if one was pending."""
    res = await session.execute(
        update(User)
        .where(User.telegram_id == telegram_id, User.pending_prompt.is_not(None))
        .values(pending_prompt=None)
    )
    await session.commit()
    return (res.rowcount or 0) > 0


async def claim_pending_prompt(
    session: AsyncSession, telegram_id: int
) -> tuple[str | None, str]:
    """Atomically claim the user's pending prompt for generation.

    The conditional UPDATE is a single statement: on PostgreSQL concurrent
    claimers serialize on the row lock and the loser matches zero rows, so
    at most one caller ever wins. Returns (prompt, "ok"), (None, "busy")
    when a generation is already running, or (None, "empty") when there is
    no pending prompt.
    """
    res = await session.execute(
        update(User)
        .where(
            User.telegram_id == telegram_id,
            User.is_generating.is_(False),
            User.pending_prompt.is_not(None),
        )
        .values(is_generating=True)
    )
    if (res.rowcount or 0) != 1:
        state = await session.execute(
            select(User.is_generating, User.pending_prompt).where(
                User.telegram_id == telegram_id
            )
        )
        row = state.first()
        if row is not None and row[0]:
            return None, "busy"
        return None, "empty"
    row = await session.execute(
        select(User).where(User.telegram_id == telegram_id)
    )
    user = row.scalar_one()
    prompt = user.pending_prompt
    user.pending_prompt = None
    await session.commit()
    return prompt, "ok"


VALID_QUALITIES = ("low", "medium", "high")



async def set_quality(session: AsyncSession, user: User, quality: str) -> None:
    if quality not in VALID_QUALITIES:
        raise ValueError(f"Invalid quality: {quality}")
    user.image_quality = quality
    await session.commit()


async def set_size(session: AsyncSession, user: User, size: str) -> None:
    from bot.services.models import VALID_IMAGE_SIZES
    if size not in VALID_IMAGE_SIZES:
        raise ValueError(f"Invalid image size: {size}")
    user.image_size = size
    await session.commit()


async def set_model(session: AsyncSession, user: User, model: str) -> None:
    from bot.services.models import model_ids
    if model not in model_ids():
        raise ValueError(f"Invalid model: {model}")
    user.image_model = model
    await session.commit()


async def get_all_users_count(session: AsyncSession) -> int:
    result = await session.execute(select(func.count(User.id)))
    return result.scalar()


async def get_active_today_count(session: AsyncSession) -> int:
    start, end = tehran_day_utc_window(today_in_tehran())
    stmt = (
        select(func.count(func.distinct(UserEvent.user_id)))
        .join(User, UserEvent.user_id == User.id)
        .where(
            UserEvent.event_type == IMAGE_GENERATION_SUCCESS,
            UserEvent.created_at >= start,
            UserEvent.created_at < end,
        )
    )
    result = await session.execute(exclude_admins(stmt))
    return result.scalar() or 0


async def get_joined_today_count(session: AsyncSession) -> int:
    start, end = tehran_day_utc_window(today_in_tehran())
    stmt = select(func.count(User.id)).where(
        User.created_at >= start, User.created_at < end
    )
    result = await session.execute(exclude_admins(stmt))
    return result.scalar()


async def get_tier_users_count(session: AsyncSession, tier: str) -> int:
    result = await session.execute(
        select(func.count(User.id)).where(User.tier == tier)
    )
    return result.scalar()


async def get_tier_images_today(session: AsyncSession, tier: str) -> int:
    """Count today's successful generations for a tier.

    Source is IMAGE_GENERATION_SUCCESS events (images are no longer saved
    to disk/DB). Tier is read from event metadata recorded at success time.
    """
    start, end = tehran_day_utc_window(today_in_tehran())
    stmt = (
        select(UserEvent.event_meta)
        .join(User, UserEvent.user_id == User.id)
        .where(
            UserEvent.event_type == IMAGE_GENERATION_SUCCESS,
            UserEvent.created_at >= start,
            UserEvent.created_at < end,
        )
    )
    result = await session.execute(exclude_admins(stmt))
    return sum(1 for (meta,) in result.all() if (meta or {}).get("tier") == tier)


async def normalize_users_on_startup(session: AsyncSession) -> dict:
    """One-way startup guardrails, safe to run on every boot.

    - Users whose saved image_model is not in the configured MODELS
      catalog are moved to the default model (NULLs are left alone;
      readers already fall back to the default).
    - Free-tier balances above FREE_USAGE_TOKEN are clamped down to it,
      so lowering the grant takes effect for existing users.
    Returns counts for logging. Never touches premium balances.
    """
    from bot.services.models import model_ids, default_model
    counts = {"models_fixed": 0, "free_capped": 0}

    supported = set(model_ids())
    if supported:
        res = await session.execute(
            update(User)
            .where(User.image_model.is_not(None), ~User.image_model.in_(supported))
            .values(image_model=default_model())
        )
        counts["models_fixed"] = res.rowcount or 0

    grant = settings.FREE_USAGE_TOKEN
    res = await session.execute(
        update(User)
        .where(User.tier == "free", User.token_balance > grant)
        .values(token_balance=grant)
    )
    counts["free_capped"] = res.rowcount or 0

    await session.commit()
    if counts["models_fixed"] or counts["free_capped"]:
        logger.info("Startup normalization: %s", counts)
    return counts


async def reset_all_daily(session: AsyncSession, include_free: bool = True) -> None:
    """Refill free users to the configured free credit grant.

    Premium balances are paid for and never touched here.
    """
    if not include_free:
        return
    await session.execute(
        update(User)
        .where(User.tier == "free")
        .values(token_balance=settings.FREE_USAGE_TOKEN)
    )
    await session.commit()



