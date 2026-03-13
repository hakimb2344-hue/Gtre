import os
import asyncio
import sqlite3
import datetime
import re
import random
import logging
from groq import Groq
from telegram import Update, LabeledPrice, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, PreCheckoutQueryHandler, CallbackQueryHandler

# --- إعداد السجلات (Logs) لمراقبة الأخطاء في Railway ---
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# --- الإعدادات ---
API_KEYS = ["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"] 
TELEGRAM_TOKEN = "8605364115:AAHUmg2qyAanzsjLBUEoc5dS9ECaipyRrZY"
CHANNEL_ID = "@forgeflow_project"
ADMIN_ID = 8443969410

# --- الألوان الذكية ---
def get_theme_color(topic):
    topic = topic.lower()
    if any(w in topic for w in ['psychology', 'peace', 'هدوء']): return (34, 139, 34)
    if any(w in topic for w in ['tech', 'future', 'تقنية']): return (0, 102, 204)
    return (20, 40, 120)

# --- قاعدة البيانات ---
def init_db():
    conn = sqlite3.connect('architect_v4.db')
    conn.execute('CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, expiry TEXT)')
    conn.execute('CREATE TABLE IF NOT EXISTS chat_history (user_id INTEGER, role TEXT, content TEXT)')
    conn.execute('CREATE TABLE IF NOT EXISTS book_progress (user_id INTEGER, title TEXT, content TEXT)')
    conn.commit()
    conn.close()

init_db()

# --- فحص الاشتراك ---
def is_sub(uid):
    if uid == ADMIN_ID: return True
    conn = sqlite3.connect('architect_v4.db')
    user = conn.execute("SELECT expiry FROM users WHERE user_id=?", (uid,)).fetchone()
    conn.close()
    if user: return datetime.datetime.strptime(user[0], '%Y-%m-%d') > datetime.datetime.now()
    return False

# --- طلبات AI ---
async def ai_req(msgs):
    try:
        client = Groq(api_key=API_KEYS[0])
        res = client.chat.completions.create(model="openai/gpt-oss-120b", messages=msgs, temperature=0.7)
        return res.choices[0].message.content
    except Exception as e:
        logger.error(f"AI Error: {e}")
        return None

# --- الأوامر الرئيسية ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if is_sub(uid):
        await update.message.reply_text("✅ المحرك جاهز. ناقشني في فكرتك أو أرسل /build.")
    else:
        kb = [[InlineKeyboardButton("💳 تفعيل (25 نجمة)", callback_data="pay")]]
        await update.message.reply_text("👑 ARCHITECT AI PRO\nأنت بحاجة لاشتراك لتأليف الكتب.", reply_markup=InlineKeyboardMarkup(kb))

async def pay_invoice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    prices = [LabeledPrice("الاشتراك الشهري", 25)]
    await context.bot.send_invoice(
        query.message.chat_id, "تفعيل المحرك", "تأليف كتب غير محدود لمدة شهر",
        "sub_payload", "", "XTR", prices
    )

async def precheckout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.pre_checkout_query.answer(ok=True)

async def success_pay(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.message.from_user.id
    expiry = (datetime.datetime.now() + datetime.timedelta(days=30)).strftime('%Y-%m-%d')
    conn = sqlite3.connect('architect_v4.db')
    conn.execute("INSERT OR REPLACE INTO users VALUES (?, ?)", (uid, expiry))
    conn.commit()
    conn.close()
    await update.message.reply_text("🎉 تم التفعيل بنجاح لمدة 30 يوماً!")

async def chat_logic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_sub(uid): return
    txt = update.message.text
    conn = sqlite3.connect('architect_v4.db')
    conn.execute("INSERT INTO chat_history VALUES (?, 'user', ?)", (uid, txt))
    conn.commit()
    
    res = await ai_req([{"role": "system", "content": "ناقش المستخدم بذكاء في فكرة كتابه."}, {"role": "user", "content": txt}])
    if res:
        await update.message.reply_text(res)
    conn.close()

# --- وظيفة النشر التلقائي في القناة ---
async def send_random_ad(context: ContextTypes.DEFAULT_TYPE):
    ads = ["📚 صمم كتابك الـ PDF الآن!", "🧠 حول أفكارك إلى مجلدات رقمية.", "🚀 Architect AI: رفيقك في التأليف."]
    try:
        await context.bot.send_message(chat_id=CHANNEL_ID, text=f"📢 {random.choice(ads)}\nابدأ الآن: @{context.bot.username}")
    except Exception as e:
        logger.error(f"Ad Error: {e}")

# --- تشغيل البوت ---
def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # جدولة الإعلانات (كل 12 ساعة)
    if app.job_queue:
        app.job_queue.run_repeating(send_random_ad, interval=43200, first=10)

    # الروابط (Handlers)
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(pay_invoice, pattern="pay"))
    app.add_handler(PreCheckoutQueryHandler(precheckout))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, success_pay))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat_logic))
    
    print("🚀 البوت يعمل الآن...")
    app.run_polling()

if __name__ == '__main__':
    main()
