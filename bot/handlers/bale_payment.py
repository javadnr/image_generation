import logging
from aiogram import Router, F
from aiogram.types import Message, PreCheckoutQuery
from bot.services.payment import complete_bale_payment, PLAN_LIMITS
from bot.services.user import get_or_create_user
from bot.services.report import send_premium_report
from bot.keyboards.reply import main_menu
from bot.db.engine import async_session
from bot.config import settings
from bot.texts import badge
import bot.texts as texts

logger = logging.getLogger(__name__)
router = Router()


@router.pre_checkout_query()
async def handle_pre_checkout(query: PreCheckoutQuery, **kwargs) -> None:
    session = kwargs["session"]
    payload = query.invoice_payload

    if not payload:
        await query.answer(ok=False, error_message="خطا: اطلاعات پرداخت یافت نشد")
        return

    from sqlalchemy import select
    from bot.db.models import Transaction, User
    result = await session.execute(
        select(Transaction, User)
        .join(User, Transaction.user_id == User.id)
        .where(Transaction.id == payload)
    )
    row = result.first()
    if not row:
        await query.answer(ok=False, error_message="خطا: تراکنش یافت نشد")
        return

    tx, user = row

    if user.telegram_id != query.from_user.id:
        await query.answer(ok=False, error_message="خطا: تراکنش متعلق به شما نیست")
        return

    if tx.status != "pending":
        await query.answer(ok=False, error_message="خطا: تراکنش قبلاً پردازش شده است")
        return

    logger.info("Pre-checkout approved user=%d tx=%s", query.from_user.id, payload)
    await query.answer(ok=True)


@router.message(F.successful_payment)
async def handle_successful_payment(message: Message, **kwargs) -> None:
    session = kwargs["session"]
    user = await get_or_create_user(session, message.from_user.id)

    payment = message.successful_payment
    payload = payment.invoice_payload
    payment_charge_id = payment.telegram_payment_charge_id
    provider_charge_id = payment.provider_payment_charge_id

    logger.info(
        "Successful payment user=%d tx=%s charge=%s provider=%s amount=%d",
        message.from_user.id, payload, payment_charge_id, provider_charge_id, payment.total_amount,
    )

    result = await complete_bale_payment(
        session=session,
        tx_id=payload,
        payment_charge_id=payment_charge_id,
        provider_charge_id=provider_charge_id,
    )
    await session.commit()

    if result["success"]:
        plan = result["plan"]
        daily = result["daily_limit"]
        monthly = daily * 30
        expire = result["expires_at"]

        text = (
            f"✅ اشتراک {texts.TIER_NAMES_FA[plan]} فعال شد!\n\n"
            f"📊 سقف روزانه: {daily} تصویر\n"
            f"📊 سقف ماهانه: {monthly} تصویر\n"
            f"📅 پایان اشتراک: {expire}"
        )
        await message.answer(badge(text), reply_markup=main_menu(user))

        await send_premium_report(message.bot, message.from_user.id, plan)
        logger.info("Bale payment completed user=%d plan=%s", message.from_user.id, plan)
    else:
        await message.answer(badge("❌ پرداخت تأیید نشد. لطفاً با پشتیبانی تماس بگیرید."))
        logger.error("Bale payment completion failed user=%d tx=%s", message.from_user.id, payload)
