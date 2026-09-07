from bot.config import settings


def badge(text: str) -> str:
    return f"{text}\n\n{settings.BADGE}"


WELCOME = "🎨 به ربات تولید تصویر با هوش مصنوعی خوش اومدی!\n\nاینجا فقط کافیه چیزی که می‌خوای رو توصیف کنی؛ ربات با هوش مصنوعی برات به تصویر تبدیلش می‌کنه ✨\n\n🖼️ ساخت تصاویر خلاقانه و حرفه‌ای\n🤖 استفاده از مدل‌های پیشرفته OpenAI\n⚡️ تولید سریع و باکیفیت\n\n👇 برای شروع، ایده‌ات رو همینجا بنویس.\nمثلاً:\n«یک گربه فضانورد روی مریخ، سبک سینمایی و واقع‌گرایانه»"

MAIN_MENU_GENERATE = "🎨 ساخت تصویر"
MAIN_MENU_BALANCE = "📊 موجودی"
MAIN_MENU_PREMIUM = "💎 خرید اشتراک"
MAIN_MENU_SETTINGS = "⚙️ تنظیمات"
MAIN_MENU_ADMIN = "📊 وضعیت ربات"

TIER_NAMES_FA = {"bronze": "برنزی", "silver": "نقره‌ای", "gold": "طلایی"}

GENERATING = "⏳ در حال تGENERATING..."
GENERATION_SUCCESS = "✅ تصویر با موفقیت ساخته شد!"
QUOTA_EXCEEDED = "⚠️ سقف روزانه شما تمام شده.\nبرای ادامه اشتراک پریمیوم تهیه کنید."
QUOTA_REMAINING = "📊 موجودی شما: {remaining} از {total} تصویر در روز"

# Premium
PREMIUM_TITLE = "💎 اشتراک پریمیوم"
PREMIUM_BRONZE = "🥉 برنزی — {price} تومان\n۱۰ تصویر در روز"
PREMIUM_SILVER = "🥈 نقره‌ای — {price} تومان\n۲۵ تصویر در روز"
PREMIUM_GOLD = "🥇 طلایی — {price} تومان\n۵۰ تصویر در روز"
PREMIUM_CURRENT = "📦 پلن فعلی شما: {tier}"
PREMIUM_SETTINGS = "⚙️ تنظیمات"

# Settings
SETTINGS_TITLE = "⚙️ تنظیمات پریمیوم"
SETTINGS_RESOLUTION = "🖼 رزولوشن: {width}×{height}"
SETTINGS_OPTIMIZE = "✨ بهینه‌سازی پرامپت: {status}"
SETTINGS_OPTIMIZE_ON = "فعال"
SETTINGS_OPTIMIZE_OFF = "غیرفعال"
SETTINGS_BACK = "🔙 بازگشت"

RESOLUTION_TITLE = "🖼 رزولوشن تصویر را انتخاب کنید:"
RESOLUTION_CUSTOM = "🔄 رزولوشن سفارشی"
RESOLUTION_CUSTOM_PROMPT = "رزولوشن دلخواه را به صورت عرض×ارتفاع ارسال کنید.\nمثال: 768×512\n\nیا روی لغو بزنید:"
RESOLUTION_CANCEL = "❌ لغو"
RESOLUTION_INVALID = "⚠️ رزولوشن نامعتبر.\nمقادیر باید مضربی از ۶۴ و نسبت بزرگتر به کوچکتر حداکثر ۱۶:۹ باشند.\nمثال صحیح: 768×512"
RESOLUTION_SET = "✅ رزولوشن به {width}×{height} تغییر کرد."

# Balance
BALANCE_TITLE = "📊 موجودی شما\n\nremain از total تصویر در روز"

# Edit
EDIT_NOT_OWN = "⚠️ این تصویر توسط ربات ارسال نشده."
EDIT_NOT_SAVED = "⚠️ این تصویر ذخیره نشده و امکان ویرایش وجود ندارد."
EDIT_FILE_MISSING = "⚠️ فایل تصویر یافت نشد."
EDIT_SUCCESS = "✅ تصویر ویرایش شد!"
EDIT_REPLY_PROMPT = "📝 پرامپت ویرایش را ارسال کنید:"

# Force join
FORCE_JOIN_TITLE = "⚠️ برای استفاده از ربات ابتدا در کانال‌های زیر عضو شوید:"
FORCE_JOIN_VERIFY = "✅ من عضو شدم"
FORCE_JOIN_NOT_JOINED = "⚠️ شما هنوز در همه کانال‌ها عضو نشده‌اید."

# Admin
ADMIN_STATS = (
    "📊 وضعیت ربات\n\n"
    "🟢 وضعیت: {status}\n\n"
    "👥 کل کاربران: {total_users}\n"
    "🟢 فعال امروز: {active_today}\n"
    "🆕 عضو شده امروز: {joined_today}\n\n"
    "🖼 تصاویر تولید شده:\n"
    "  آزاد: {free_images}\n"
    "  برنزی: {bronze_images}\n"
    "  نقره‌ای: {silver_images}\n"
    "  طلایی: {gold_images}\n\n"
    "💎 پریمیوم‌ها:\n"
    "  برنزی: {bronze_users}\n"
    "  نقره‌ای: {silver_users}\n"
    "  طلایی: {gold_users}"
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
ADMIN_ACTIVATED = "✅ پریمیوم {tier} برای کاربر {user_id} فعال شد."
ADMIN_INVALID_TIER = "⚠️ پلن نامعتبر. tiers: free, bronze, silver, gold"
ADMIN_REPORT = "💎 اکانت پریمیوم فعال شد\n👤 کاربر: {user_id}\n📦 پلن: {tier}\n💰 قیمت: {price} تومان"
