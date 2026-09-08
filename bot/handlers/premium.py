from datetime import datetime
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from bot.services.user import get_or_create_user, get_tier_limit
from bot.services.report import send_premium_report, TIER_PRICES
from bot.services.payment import (
    create_zarinpal_purchase, verify_zarinpal_payment,
    create_bale_purchase, get_bale_payment_provider,
)
from bot.keyboards.inline import premium_menu
from bot.keyboards.reply import main_menu
from bot.db.engine import async_session
from bot.config import settings
from bot.texts import badge
import bot.texts as texts

router = Router()

TIER_NAMES = {"free": "ندارد", "bronze": "🥉 برنزی", "silver": "🥈 نقره‌ای", "gold": "🥇 طلایی"}


def tooman_display(price: int) -> str:
    thousands = price // 1000
    return f"{thousands} هزار تومان"


def premium_text(user) -> str:
    if user.tier != "free" and user.premium_expire_date:
        expire = user.premium_expire_date.strftime("%Y/%m/%d")
        remaining = (user.premium_expire_date.date() - datetime.now().date()).days
        daily = get_tier_limit(user.tier)
        monthly = daily * 30
        return badge(
            f"{texts.PREMIUM_TITLE}\n\n"
            f"📊 سقف روزانه: {daily} تصویر\n"
            f"📊 سقف ماهانه: {monthly} تصویر\n"
            f"📅 تاریخ پایان: {expire}\n"
            f"⏳ روزهای باقی‌مانده: {remaining}"
        )

    bronze_daily = get_tier_limit("bronze")
    silver_daily = get_tier_limit("silver")
    gold_daily = get_tier_limit("gold")

    bronze_q = settings.BRONZE_QUEUE_SIZE or "∞"
    silver_q = settings.SILVER_QUEUE_SIZE or "∞"
    gold_q = "∞"

    return badge(
        f"💎 پلن‌های پریمیوم\n\n"
        f"با خرید پریمیوم، محدودیت تولید تصویرت رو بیشتر کن و با اولویت بالاتر عکس بساز! 🚀\n\n"
        f"🥉 برنزی — {tooman_display(settings.BRONZE_PRICE)}\n"
        f"• روزانه تا {bronze_daily} تصویر\n"
        f"• حداکثر {bronze_daily * 30} تصویر در ماه\n"
        f"• صف پردازش تا {bronze_q} کاربر همزمان\n\n"
        f"🥈 نقره‌ای — {tooman_display(settings.SILVER_PRICE)}\n"
        f"• روزانه تا {silver_daily} تصویر\n"
        f"• حداکثر {silver_daily * 30} تصویر در ماه\n"
        f"• صف پردازش تا {silver_q} کاربر همزمان\n\n"
        f"🥇 طلایی — {tooman_display(settings.GOLD_PRICE)}\n"
        f"• روزانه تا {gold_daily} تصویر\n"
        f"• حداکثر {gold_daily * 30} تصویر در ماه\n"
        f"• بدون صف پردازش ⚡️\n\n"
        f"🆓 پلن رایگان\n"
        f"• روزانه {get_tier_limit('free')} تصویر\n"
        f"• صف پردازش تا {settings.FREE_QUEUE_SIZE} کاربر همزمان\n\n"
        f"💡 همه تصاویر با مدل‌های پیشرفته OpenAI تولید می‌شوند.\n\n"
        f"👇 پلن موردنظرت رو انتخاب کن:"
    )


@router.message(F.text == texts.MAIN_MENU_PREMIUM)
async def premium(message: Message, session):
    user = await get_or_create_user(session, message.from_user.id)
    await message.answer(premium_text(user), reply_markup=premium_menu(user))


@router.callback_query(F.data.startswith("buy_"))
async def buy_tier(callback: CallbackQuery, session):
    tier = callback.data.replace("buy_", "")
    if tier not in ("bronze", "silver", "gold"):
        await callback.answer(texts.ADMIN_INVALID_TIER, show_alert=True)
        return

    user = await get_or_create_user(session, callback.from_user.id)

    try:
        if settings.API_SERVER == "bale":
            result = await create_bale_purchase(session, user, tier)
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
        daily = result["daily_limit"]
        monthly = daily * 30
        expire = result["expires_at"]

        text = (
            f"✅ اشتراک {texts.TIER_NAMES_FA[plan]} فعال شد!\n\n"
            f"📊 سقف روزانه: {daily} تصویر\n"
            f"📊 سقف ماهانه: {monthly} تصویر\n"
            f"📅 پایان اشتراک: {expire}"
        )
        await callback.message.edit_text(badge(text))

        from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
        buttons = [
            [KeyboardButton(text=texts.MAIN_MENU_GENERATE), KeyboardButton(text=texts.MAIN_MENU_BALANCE)],
            [KeyboardButton(text=texts.MAIN_MENU_PREMIUM), KeyboardButton(text=texts.MAIN_MENU_SETTINGS)],
        ]
        await callback.message.answer(
            badge(texts.WELCOME),
            reply_markup=ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True),
        )

        await send_premium_report(callback.bot, callback.from_user.id, plan)
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
