from datetime import datetime
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from bot.services.user import get_or_create_user, get_edit_cost
from bot.services.report import send_premium_report
from bot.services.analytics import (
    log_event, maybe_log_free_limit, PRICING_VIEWED, BUY_SUBSCRIPTION_CLICKED,
    PLAN_SELECTED, PAYMENT_STARTED,
)
from bot.services.models import (
    plan_allowance, default_model, images_per_quality,
    edits_available,
)
from bot.services.payment import (
    create_zarinpal_purchase, verify_zarinpal_payment,
    create_bale_purchase, get_bale_payment_provider,
)
from bot.services.pricing import plan_price_toman, last_known_rate
from bot.keyboards.inline import premium_menu
from bot.keyboards.reply import main_menu
from bot.db.engine import async_session
from bot.config import settings
from bot.texts import badge
import bot.texts as texts

router = Router()

TIER_NAMES = {"free": "ندارد", "bronze": "🥉 برنزی", "silver": "🥈 نقره‌ای", "gold": "🥇 طلایی"}


def tooman_display(price: int | None) -> str:
    if price is None:
        return "قیمت نامشخص"
    thousands = price // 1000
    return f"{thousands} هزار تومان"


QUALITY_FA = {"low": "پایین", "medium": "متوسط", "high": "بالا"}


def _plan_images_text(plan: str, allowance: int) -> str:
    """Approximate image count for a plan allowance (Low-quality basis)."""
    low = images_per_quality(allowance, default_model()).get("low")
    if low is not None:
        return f"• تقریباً {low:,} تصویر"
    return f"• تقریباً {allowance:,} تصویر"


def _quality_breakdown(allowance: int) -> str | None:
    """Per-quality approximate image counts, profit-adjusted."""
    per_quality = images_per_quality(allowance, default_model())
    parts = [
        f"{count:,} {QUALITY_FA[quality]}"
        for quality, count in per_quality.items()
    ]
    parts.append(f"{edits_available(allowance, get_edit_cost())} ویرایش")
    return " | ".join(parts) if parts else None


def _fx_note() -> str | None:
    rate = last_known_rate()
    if not rate:
        return None
    return (
        f"💱 قیمت‌ها بر اساس نرخ روز دلار محاسبه شده: 1 دلار = {rate:,.0f} تومان.\n"
        f"نرخ ارز هر ۵ دقیقه به‌روزرسانی می‌شود."
    )


def _quality_breakdown_text() -> str:
    lines = []
    for plan, emoji in (("bronze", "🥉"), ("silver", "🥈"), ("gold", "🥇")):
        breakdown = _quality_breakdown(plan_allowance(plan))
        if breakdown:
            lines.append(f"{emoji} {breakdown}")
    if not lines:
        return ""
    return "📊 تعداد تقریبی تصاویر هر پلن بر اساس کیفیت:\n" + "\n".join(lines) + "\n"


def _fx_note_text() -> str:
    note = _fx_note()
    return (note + "\n") if note else ""


def premium_text(user) -> str:
    if user.tier != "free" and user.premium_expire_date:
        expire = user.premium_expire_date.strftime("%Y/%m/%d")
        remaining = (user.premium_expire_date.date() - datetime.now().date()).days
        model = user.image_model or default_model()
        per_quality = images_per_quality(user.token_balance or 0, model)
        breakdown = "\n".join(
            f"• {texts.QUALITY_LABELS[q]}: {count:,} تصویر"
            for q, count in per_quality.items()
        ) or "—"
        return badge(
            f"{texts.PREMIUM_TITLE}\n\n"
            f"🤖 مدل: {model}\n"
            f"🖼 تعداد تقریبی تصاویر باقی‌مانده:\n{breakdown}\n"
            f"📅 تاریخ پایان: {expire}\n"
            f"⏳ روزهای باقی‌مانده: {remaining}"
        )

    return badge(
        f"💎 پلن‌های پریمیوم\n\n"
        f"با خرید پریمیوم، تصاویر با کیفیت تر بساز! 🚀\n"
        f"📅 همه پلن‌ها ماهانه هستند.\n\n"
        f"🆓 پلن رایگان\n"
        f"• {settings.FREE_USAGE_TOKEN:,} اعتبار\n\n"
        f"🥉 برنزی — {tooman_display(plan_price_toman('bronze'))}\n"
        f"{_plan_images_text('bronze', plan_allowance('bronze'))}\n\n"
        f"🥈 نقره‌ای — {tooman_display(plan_price_toman('silver'))} ⭐ محبوب‌ترین\n"
        f"{_plan_images_text('silver', plan_allowance('silver'))}\n\n"
        f"🥇 طلایی — {tooman_display(plan_price_toman('gold'))} 🔥 بیشترین اعتبار\n"
        f"{_plan_images_text('gold', plan_allowance('gold'))}\n\n"
        f"📌 توجه: تعداد تصاویر نمایش‌داده‌شده بر اساس کیفیت پایین است. "
        f"تولید تصویر با کیفیت بالاتر، از موجودی شما بیشتر کم می‌کند.\n"
        f"{_quality_breakdown_text()}\n"
        f"{_fx_note_text()}\n"
        f"👇 پلن موردنظرت رو انتخاب کن:"
    )


async def answer_quota_exceeded(message: Message, session, user) -> None:
    """Tell the user they must buy for more, then show the plans."""
    await maybe_log_free_limit(session, user)
    if user.tier == "free":
        await message.answer(badge(texts.LIMIT_REACHED_BUY))
    else:
        await message.answer(badge(texts.INSUFFICIENT_BALANCE))
    await message.answer(premium_text(user), reply_markup=premium_menu(user))


@router.message(F.text == texts.MAIN_MENU_PREMIUM)
async def premium(message: Message, session):
    user = await get_or_create_user(session, message.from_user.id)
    await log_event(session, user, BUY_SUBSCRIPTION_CLICKED)
    await log_event(session, user, PRICING_VIEWED)
    await message.answer(premium_text(user), reply_markup=premium_menu(user))


@router.callback_query(F.data == "show_plans")
async def show_plans(callback: CallbackQuery, session):
    user = await get_or_create_user(session, callback.from_user.id)
    await callback.message.answer(premium_text(user), reply_markup=premium_menu(user))
    await callback.answer()


@router.callback_query(F.data.startswith("buy_"))
async def buy_tier(callback: CallbackQuery, session):
    tier = callback.data.replace("buy_", "")
    if tier not in ("bronze", "silver", "gold"):
        await callback.answer(texts.ADMIN_INVALID_TIER, show_alert=True)
        return

    user = await get_or_create_user(session, callback.from_user.id)
    await log_event(session, user, PLAN_SELECTED, {"plan": tier, "price": plan_price_toman(tier)})

    try:
        if settings.API_SERVER == "bale":
            result = await create_bale_purchase(session, user, tier)
            await log_event(
                session, user, PAYMENT_STARTED,
                {"plan": tier, "amount": result["amount_toman"], "provider": "bale"},
            )
            await callback.answer()

            bale_provider = get_bale_payment_provider()
            if not bale_provider:
                await callback.message.answer(badge("⚠️ پرداخت Bale در دسترس نیست."), reply_markup=premium_menu(user))
                return

            await bale_provider.send_invoice(
                chat_id=callback.message.chat.id,
                title=result["title"],
                description=result["description"],
                payload=result["payload"],
                prices=result["prices"],
            )
        else:
            result = await create_zarinpal_purchase(session, user, tier)
            await log_event(
                session, user, PAYMENT_STARTED,
                {"plan": tier, "amount": result["amount_toman"], "provider": "zarinpal"},
            )
            await callback.answer()

            tx_id = result["transaction_id"]
            payment_link = result["payment_link"]
            amount = result["amount_toman"]
            remaining = result["remaining_minutes"]

            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=f"💳 پرداخت {amount:,} تومان", url=payment_link)],
                [InlineKeyboardButton(text="✅ پرداخت را انجام دادم", callback_data=f"checkpay:{tx_id}")],
            ])

            text = (
                f"📋 پلن انتخابی: {texts.TIER_NAMES_FA[tier]}\n"
                f"💰 مبلغ: {amount:,} تومان\n"
                f"📅 مدت: {settings.PREMIUM_DURATION_DAYS} روز\n\n"
                f"💡 روی دکمه پرداخت کلیک کنید و پس از تکمیل، دکمه «پرداخت را انجام دادم» را بزنید.\n"
                f"⏳ لینک پرداخت به مدت {remaining} دقیقه معتبر است."
            )
            await callback.message.answer(badge(text), reply_markup=keyboard)
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("Payment creation error user=%d", callback.from_user.id)
        await callback.message.answer(badge("⚠️ خطایی در ایجاد پرداخت رخ داد. لطفاً دوباره تلاش کنید."))


@router.callback_query(F.data.startswith("checkpay:"))
async def handle_check_payment(callback: CallbackQuery, session):
    tx_id = callback.data.split(":", 1)[1]

    async with async_session() as session:
        result = await verify_zarinpal_payment(session, tx_id)

    if result["success"]:
        plan = result["plan"]
        expire = result["expires_at"]

        text = (
            f"✅ اشتراک {texts.TIER_NAMES_FA[plan]} فعال شد!\n\n"
            f"📅 پایان اشتراک: {expire}"
        )
        await callback.message.edit_text(badge(text))

        async with async_session() as fresh_session:
            fresh_user = await get_or_create_user(fresh_session, callback.from_user.id)
            await callback.message.answer(
                badge(texts.WELCOME),
                reply_markup=main_menu(fresh_user),
            )

        await send_premium_report(
            callback.bot,
            callback.from_user.id,
            plan,
            username=callback.from_user.username,
            payment_id=result.get("payment_ref_id"),
            amount=result.get("amount"),
            expire_dt=result.get("expire_dt"),
            paid_at=result.get("paid_at"),
        )
        await callback.answer()
    elif result.get("reason") == "link_expired":
        await callback.answer("⚠️ لینک پرداخت منقضی شده است. لطفاً دوباره خرید کنید.", show_alert=True)
    elif result.get("reason") == "not_paid":
        await callback.answer("⚠️ پرداخت انجام نشد. لطفاً دوباره تلاش کنید.", show_alert=True)
    else:
        await callback.answer("⚠️ خطایی رخ داد. لطفاً دوباره تلاش کنید.", show_alert=True)


@router.callback_query(F.data == "back_premium")
async def back_to_premium(callback: CallbackQuery, session):
    user = await get_or_create_user(session, callback.from_user.id)
    await callback.message.edit_text(premium_text(user), reply_markup=premium_menu(user))
    await callback.answer()
