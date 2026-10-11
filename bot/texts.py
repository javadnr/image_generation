from bot.config import settings


def badge(text: str) -> str:
    return f"{text}\n\n{settings.BADGE}"


WELCOME = "🎨 به ربات تولید تصویر با هوش مصنوعی خوش اومدی!\n\nاینجا فقط کافیه چیزی که می‌خوای رو توصیف کنی؛ ربات با هوش مصنوعی برات به تصویر تبدیلش می‌کنه ✨\n\n🖼️ ساخت تصاویر خلاقانه و حرفه‌ای\n🤖 استفاده از مدل‌های پیشرفته OpenAI\n⚡️ تولید سریع و باکیفیت\n\n👇 برای شروع، ایده‌ات رو همینجا بنویس.\nمثلاً:\n«یک گربه فضانورد روی مریخ، سبک سینمایی و واقع‌گرایانه»\n\n📷 برای ویرایش عکس، کافیه عکست رو با کپشن (توضیح تغییر موردنظرت) بفرستی. (مخصوص کاربران پریمیوم 💎)"

MAIN_MENU_GENERATE = "🎨 ساخت تصویر"
MAIN_MENU_BALANCE = "📊 موجودی"
MAIN_MENU_PREMIUM = "💎 خرید اشتراک"
MAIN_MENU_QUALITY = "🖼️ تنظیمات تصویر"
MAIN_MENU_MODEL = "🤖 انتخاب مدل"
MAIN_MENU_ADMIN = "📊 وضعیت ربات"

TIER_NAMES_FA = {"bronze": "برنزی", "silver": "نقره‌ای", "gold": "طلایی"}

GENERATING = "⏳ در حال تGENERATING..."
GENERATION_SUCCESS = "✅ تصویر با موفقیت ساخته شد!"
LIMIT_REACHED_BUY = "⚠️ سقف استفاده شما تمام شده است.\nبرای ساخت تصاویر بیشتر باید اشتراک تهیه کنید 👇"
INSUFFICIENT_BALANCE = "⚠️ موجودی شما برای ساخت تصویر با این کیفیت کافی نیست.\nبرای ادامه اشتراک تهیه کنید 👇"
QUOTA_REMAINING_TOKENS = "📊 موجودی شما\n\n📦 پلن: {tier}\n🤖 مدل: {model}\n🖼 تعداد تقریبی تصاویر باقی‌مانده:\n{breakdown}\n💡 تعداد واقعی ممکن است متفاوت باشد."
QUOTA_REMAINING_FREE = "📊 موجودی شما\n\n📦 پلن: رایگان\n🖼 اعتبار باقی‌مانده: {daily_remaining} از {daily_limit}"

# Quality
QUALITY_TITLE = "کیفیت تصویر خروجی بعدی رو انتخاب کن:"
QUALITY_LABELS = {"low": "پایین", "medium": "متوسط", "high": "بالا"}
QUALITY_SET = "✅ کیفیت تصویر روی {label} تنظیم شد."
QUALITY_LOCKED = "🔒 این کیفیت مخصوص کاربران پریمیوم است."

# Model
MODEL_TITLE = "مدل تولید تصویر رو انتخاب کن:"
MODEL_HELP = (
    "• gpt-image-2.5-flare: سریع‌تر، مناسب استفاده روزمره\n"
    "• gpt-image-2.5-sunburst: کندتر ولی دقیق‌تر در نمایش متن داخل تصویر\n\n"
    "💰 هر دو مدل هم‌قیمت‌اند؛ بر اساس نیازت انتخاب کن."
)
MODEL_SET = "✅ مدل تولید تصویر روی {label} تنظیم شد."
MODEL_LOCKED = "🔒 این مدل مخصوص کاربران پریمیوم است."

# Premium
PREMIUM_TITLE = "💎 اشتراک پریمیوم"
PREMIUM_BRONZE = "🥉 برنزی — {price} تومان\n۱۰ تصویر در روز"
PREMIUM_SILVER = "🥈 نقره‌ای — {price} تومان\n۲۵ تصویر در روز"
PREMIUM_GOLD = "🥇 طلایی — {price} تومان\n۵۰ تصویر در روز"
PREMIUM_CURRENT = "📦 پلن فعلی شما: {tier}"
# Balance
BALANCE_TITLE = "📊 موجودی شما\n\nremain از total تصویر در روز"

# Edit
EDIT_PREMIUM_ONLY = "⚠️ ویرایش تصویر فقط برای کاربران پریمیوم فعال است.\nبرای استفاده از این قابلیت، اشتراک تهیه کنید 👇"

# Force join
FORCE_JOIN_TITLE = "⚠️ برای استفاده از ربات ابتدا در کانال‌های زیر عضو شوید:"
FORCE_JOIN_VERIFY = "✅ من عضو شدم"
FORCE_JOIN_NOT_JOINED = "⚠️ شما هنوز در همه کانال‌ها عضو نشده‌اید."

# Admin
ADMIN_STATS = (
    "📊 وضعیت ربات\n\n"
    "🟢 وضعیت: {status}\n\n"
    "👥 کاربران:\n"
    "  کل: {total_users}\n"
    "  جدید امروز: {joined_today}\n"
    "  فعال امروز: {active_today}\n\n"
    "🖼 مصرف امروز:\n"
    "  شروع: {started_today} | موفق: {success_today} | خطا: {failed_today}\n\n"
    "💎 خرید امروز:\n"
    "  کلیک اشتراک: {click_unique} نفر ({click_total} کلیک)\n"
    "  مشاهده قیمت: {pricing_viewers} نفر (جدید: {pricing_new} نفر)\n"
    "  انتخاب پلن: 🥉{plan_bronze} 🥈{plan_silver} 🥇{plan_gold}\n"
    "  شروع پرداخت: {pay_started} | موفق: {pay_success}\n\n"
    "🖼 تصاویر امروز:\n"
    "  آزاد: {free_images}\n"
    "  برنزی: {bronze_images}\n"
    "  نقره‌ای: {silver_images}\n"
    "  طلایی: {gold_images}\n\n"
    "💎 پریمیوم‌ها:\n"
    "  برنزی: {bronze_users}\n"
    "  نقره‌ای: {silver_users}\n"
    "  طلایی: {gold_users}\n\n"
    "🛠 دستورات مدیر:\n"
    "  /stats — آمار کلی\n"
    "  /set_premium <user_id> <tier> — تغییر پلن\n"
    "  /activate <tier> <user_id> — فعال‌سازی اشتراک\n"
    "  /deactivate <user_id> — بازگشت به رایگان\n"
    "  /broadcast <متن> — ارسال همگانی"
)
ADMIN_TOGGLE_ON = "🟢 ربات فعال شد."
ADMIN_TOGGLE_OFF = "🔴 ربات غیرفعال شد."
ADMIN_RESET_DONE = "✅ روزانه همه کاربران ریست شد."
BOT_DISABLED = "🔴 ربات در حال حاضر در تعمیرات است. لطفاً بعداً تلاش کنید."

# Errors
ERROR_API = "⚠️ خطای API: {error}"
ERROR_GENERIC = "⚠️ خطای غیرمنتظره رخ داد."
ERROR_WAIT = "⚠️ درخواست‌ها زیاد است. لطفاً چند لحظه صبر کنید."
ERROR_MODERATION = "⚠️ پرامپت شما مطابق سیاست‌های محتوایی نیست."

# Admin premium activation
ADMIN_USAGE = "استفاده: /set_premium <user_id> <tier>"
ADMIN_ACTIVATE_USAGE = "استفاده: /activate <tier> <user_id>\nمثال: /activate silver 123456789"
ADMIN_DEACTIVATE_USAGE = "استفاده: /deactivate <user_id>\nمثال: /deactivate 123456789"
ADMIN_DEACTIVATED = "✅ کاربر {user_id} به پلن رایگان بازگشت."
USER_DEACTIVATED = "📦 اشتراک شما به پایان رسید و به پلن رایگان بازگشتید.\n💎 برای تهیه اشتراک جدید، از دکمه «خرید اشتراک» استفاده کنید."
ADMIN_ACTIVATED = "✅ پریمیوم {tier} برای کاربر {user_id} فعال شد."
ADMIN_INVALID_TIER = "⚠️ پلن نامعتبر. tiers: free, bronze, silver, gold"
ADMIN_REPORT = "💎 اکانت پریمیوم فعال شد\n👤 کاربر: {user_id}\n📦 پلن: {tier}\n💰 قیمت: {price} تومان"
ADMIN_BROADCAST_USAGE = "استفاده:\n/broadcast متن پیام\nیا روی یک پیام ریپلای کنید و بنویسید:\n/broadcast"
ADMIN_BROADCAST_STARTED = "⏳ ارسال همگانی شروع شد..."
ADMIN_BROADCAST_DONE = "✅ ارسال همگانی تمام شد\n✔️ موفق: {ok}\n❌ ناموفق: {fail}"
