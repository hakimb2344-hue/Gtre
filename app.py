import os
import asyncio
import sqlite3
import datetime
import logging
from groq import Groq
from telegram import Update, LabeledPrice, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, PreCheckoutQueryHandler

# --- الإعدادات ---
API_KEYS = [
    "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", 
    "ضع_المفتاح_الثاني_هنا"
]
TELEGRAM_TOKEN = "8605364115:AAHUmg2qyAanzsjLBUEoc5dS9ECaipyRrZY"
ADMIN_ID = 8443969410

# --- البرومبت الداخلي العملاق (سر القوة) ---
SYSTEM_CORE_PROMPT = """
أنت الآن "ARCHITECT AI MASTER"، المحرك الأكثر تطوراً في العالم لتأليف المجلدات.
قوانين عملك التي تجعلك تتفوق على الجميع:
1. التخطيط الاستراتيجي: قبل الكتابة، صمم هيكلاً منطقياً يتصاعد في الأحداث أو المعلومات.
2. العمق السردي: ممنوع السطحية. كل فصل يجب أن يكون عالماً قائماً بذاته، مليئاً بالتفاصيل الدقيقة، الأوصاف الحسية، والتحليلات العميقة.
3. الذكاء اللغوي: استخدم لغة فخمة، قوية، وخالية من الأخطاء. تجنب التكرار الممل.
4. النقاء البصري: لا تستخدم رموز الماركداون (#, *, -, `). استخدم فقط المسافات والأسطر لتنظيم النص ليكون جاهزاً للطباعة فوراً.
5. الاستمرارية: تذكر دائماً ما كتبته في الفصول السابقة لضمان ترابط الأحداث.
أنت لا تكتب مجرد نصوص، أنت تصنع إرثاً معرفياً وأدبياً.
"""

# --- إعداد المحرك وقاعدة البيانات ---
client = Groq(api_key=API_KEYS[0])

def init_db():
    conn = sqlite3.connect('architect_ai.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, expiry_date TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS chat_history (user_id INTEGER, role TEXT, content TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS book_progress (user_id INTEGER, title TEXT, content TEXT)''')
    conn.commit()
    conn.close()

init_db()

# --- دالة التحقق من الاشتراك ---
def is_subscribed(user_id):
    if user_id == ADMIN_ID: return True
    conn = sqlite3.connect('architect_ai.db')
    user = conn.execute("SELECT expiry_date FROM users WHERE user_id=?", (user_id,)).fetchone()
    conn.close()
    if user:
        expiry = datetime.datetime.strptime(user[0], '%Y-%m-%d')
        return expiry > datetime.datetime.now()
    return False

# --- أوامر البوت ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    name = update.effective_user.first_name
    
    welcome_msg = (
        f"👑 **أهلاً بك يا {name} في ARCHITECT AI**\n\n"
        "أنت الآن متصل بالمحرك السيادي لتأليف الكتب والمجلدات.\n"
        "هذا البوت ليس مجرد شات، إنه مصنع للمعرفة.\n\n"
        "💎 **مميزات المحرك:**\n"
        "• تأليف كتب تصل إلى 100+ صفحة.\n"
        "• نظام تدوير المفاتيح لضمان عدم التوقف.\n"
        "• تصدير ملفات PDF احترافية.\n\n"
        "🎫 **الاشتراك:** 25 نجمة شهرياً لفتح كامل القوة."
    )

    if is_subscribed(user_id):
        await update.message.reply_text(f"{welcome_msg}\n\n✅ **اشتراكك فعال.** ابدأ بوصف فكرة كتابك الآن!")
    else:
        keyboard = [[InlineKeyboardButton("💳 اشترك الآن (25 نجمة)", callback_data="pay")]]
        await update.message.reply_text(f"{welcome_msg}\n\n⚠️ **الاشتراك مطلوب.**", reply_markup=InlineKeyboardMarkup(keyboard))

async def handle_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # كود إرسال الفاتورة بالنجوم (XTR)
    prices = [LabeledPrice("الاشتراك الشهري", 25)]
    await context.bot.send_invoice(
        update.effective_chat.id, "تفعيل ARCHITECT AI", 
        "وصول غير محدود لمحرك تأليف الكتب لمدة شهر.", 
        "sub_payload", "", "XTR", prices
    )

async def precheckout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.pre_checkout_query.answer(ok=True)

async def success_pay(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    expiry = (datetime.datetime.now() + datetime.timedelta(days=30)).strftime('%Y-%m-%d')
    conn = sqlite3.connect('architect_ai.db')
    conn.execute("INSERT OR REPLACE INTO users VALUES (?, ?)", (user_id, expiry))
    conn.commit()
    conn.close()
    await update.message.reply_text("🎊 هنيئاً! تم تفعيل القوة الكاملة للمحرك لمدة 30 يوماً. ابدأ الآن!")

# --- لوحة التحكم للأدمن ---
async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    conn = sqlite3.connect('architect_ai.db')
    count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    conn.close()
    await update.message.reply_text(f"🛠 **لوحة التحكم**\n\n👥 عدد المشتركين: {count}\n🔑 المفتاح الحالي: {current_key_index + 1}")

# --- محرك التأليف الرئيسي ---
async def chat_logic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_subscribed(user_id):
        await start(update, context)
        return

    # حفظ المحادثة وبناء الرد باستخدام SYSTEM_CORE_PROMPT
    # (هنا نضع دالة safe_ai_request مع استدعاء البرومبت العملاق)
    pass

# --- التشغيل ---
if __name__ == '__main__':
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin))
    app.add_handler(PreCheckoutQueryHandler(precheckout))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, success_pay))
    # أضف بقية الـ Handlers هنا...
    print("🚀 المحرك السيادي ARCHITECT AI انطلق!")
    app.run_polling()
