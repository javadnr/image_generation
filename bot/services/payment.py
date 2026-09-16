import uuid
import logging
from datetime import datetime, timedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import User, Transaction
from bot.config import settings
from bot.services.zarinpal import ZarinPalClient
from bot.services.bale_payment import BalePaymentProvider

logger = logging.getLogger(__name__)

PLAN_PRICES = {
    "bronze": settings.BRONZE_PRICE,
    "silver": settings.SILVER_PRICE,
    "gold": settings.GOLD_PRICE,
}

PLAN_LIMITS = {
    "bronze": settings.BRONZE_LIMIT,
    "silver": settings.SILVER_LIMIT,
    "gold": settings.GOLD_LIMIT,
}

PLAN_MAX_LIMITS = {
    "bronze": settings.BRONZE_MAX_LIMIT,
    "silver": settings.SILVER_MAX_LIMIT,
    "gold": settings.GOLD_MAX_LIMIT,
}


def get_zarinpal_client() -> ZarinPalClient:
    return ZarinPalClient(settings.ZARINPAL_API_URL, settings.ZARINPAL_PROJECT_ID)


def get_bale_payment_provider() -> BalePaymentProvider | None:
    if not settings.BALE_PROVIDER_TOKEN or not settings.BOT_TOKEN:
        return None
    return BalePaymentProvider(settings.BOT_TOKEN, settings.BALE_PROVIDER_TOKEN)


LINK_EXPIRY_MINUTES = 30


async def _find_pending_tx(session: AsyncSession, user_id: int, plan: str):
    result = await session.execute(
        select(Transaction).where(
            Transaction.user_id == user_id,
            Transaction.plan == plan,
            Transaction.status == "pending",
        ).order_by(Transaction.created_at.desc()).with_for_update()
    )
    tx = result.scalar_one_or_none()
    if tx:
        age = (datetime.utcnow() - tx.created_at).total_seconds()
        if age < LINK_EXPIRY_MINUTES * 60:
            remaining = LINK_EXPIRY_MINUTES - int(age // 60)
            return tx, remaining
    return None, 0


async def activate_plan(session: AsyncSession, user: User, plan: str) -> None:
    user.tier = plan
    user.premium_expire_date = datetime.now() + timedelta(days=settings.PREMIUM_DURATION_DAYS)
    user.daily_used = 0
    user.total_used = 0
    await session.commit()


async def create_zarinpal_purchase(session: AsyncSession, user: User, plan: str) -> dict:
    existing, remaining = await _find_pending_tx(session, user.id, plan)
    if existing and existing.payment_authority:
        payment_link = f"https://www.zarinpal.com/pg/StartPay/{existing.payment_authority}"
        return {
            "transaction_id": existing.id,
            "payment_link": payment_link,
            "amount_toman": existing.amount,
            "remaining_minutes": remaining,
        }
    if existing:
        await session.delete(existing)
        await session.commit()

    amount = PLAN_PRICES[plan]
    client = get_zarinpal_client()
    authority, payment_link = await client.request_payment(amount, f"اشتراک {plan}")

    tx = Transaction(
        id=str(uuid.uuid4()),
        user_id=user.id,
        plan=plan,
        amount=amount,
        status="pending",
        payment_authority=authority,
    )
    session.add(tx)
    await session.commit()

    return {
        "transaction_id": tx.id,
        "payment_link": payment_link,
        "amount_toman": amount,
        "remaining_minutes": LINK_EXPIRY_MINUTES,
    }


async def verify_zarinpal_payment(session: AsyncSession, tx_id: str) -> dict:
    result = await session.execute(select(Transaction).where(Transaction.id == tx_id))
    tx = result.scalar_one_or_none()
    if not tx or tx.status != "pending":
        return {"success": False, "reason": "not_found_or_processed"}

    user_result = await session.execute(select(User).where(User.id == tx.user_id))
    user = user_result.scalar_one_or_none()
    if not user:
        return {"success": False, "reason": "user_not_found"}

    client = get_zarinpal_client()
    code, status = await client.verify_payment(tx.payment_authority, tx.amount)

    if code == 100:
        tx.status = "paid"
        tx.payment_ref_id = status
        tx.paid_at = datetime.utcnow()
        await activate_plan(session, user, tx.plan)
        return {
            "success": True,
            "plan": tx.plan,
            "daily_limit": PLAN_LIMITS.get(tx.plan, 0),
            "max_limit": PLAN_MAX_LIMITS.get(tx.plan, 0),
            "expires_at": user.premium_expire_date.strftime("%Y/%m/%d") if user.premium_expire_date else "—",
        }
    elif code == -51:
        return {"success": False, "reason": "link_expired"}
    elif code == -52:
        return {"success": False, "reason": "not_paid"}
    else:
        return {"success": False, "reason": f"code_{code}"}


async def create_bale_purchase(session: AsyncSession, user: User, plan: str) -> dict:
    existing, _ = await _find_pending_tx(session, user.id, plan)
    if existing:
        await session.delete(existing)
        await session.commit()

    amount = PLAN_PRICES[plan]
    tx = Transaction(
        id=str(uuid.uuid4()),
        user_id=user.id,
        plan=plan,
        amount=amount,
        status="pending",
    )
    session.add(tx)
    await session.commit()

    plan_display = {"bronze": "🥉 برنزی", "silver": "🥈 نقره‌ای", "gold": "🥇 طلایی"}
    return {
        "transaction_id": tx.id,
        "title": f"اشتراک {plan_display.get(plan, plan)}",
        "description": f"خرید اشتراک {plan} - تصویرساز هوش مصنوعی",
        "payload": tx.id,
        "prices": [{"label": plan_display.get(plan, plan), "amount": amount * 10}],
        "amount_toman": amount,
    }


async def complete_bale_payment(
    session: AsyncSession,
    tx_id: str,
    payment_charge_id: str,
    provider_charge_id: str,
) -> dict:
    result = await session.execute(select(Transaction).where(Transaction.id == tx_id))
    tx = result.scalar_one_or_none()
    if not tx or tx.status != "pending":
        return {"success": False, "reason": "not_found_or_processed"}

    user_result = await session.execute(select(User).where(User.id == tx.user_id))
    user = user_result.scalar_one_or_none()
    if not user:
        return {"success": False, "reason": "user_not_found"}

    tx.status = "paid"
    tx.payment_ref_id = f"{payment_charge_id}:{provider_charge_id}"
    tx.paid_at = datetime.utcnow()
    await activate_plan(session, user, tx.plan)

    return {
        "success": True,
        "plan": tx.plan,
        "daily_limit": PLAN_LIMITS.get(tx.plan, 0),
        "max_limit": PLAN_MAX_LIMITS.get(tx.plan, 0),
        "expires_at": user.premium_expire_date.strftime("%Y/%m/%d") if user.premium_expire_date else "—",
    }
