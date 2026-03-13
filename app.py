import os
import asyncio
import sqlite3
import datetime
import logging
import time
from groq import Groq
from telegram import Update, LabeledPrice, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, PreCheckoutQueryHandler
from fpdf import FPDF
from arabic_reshaper import reshape
from bidi.algorithm import get_display

# --- إعداد السجلات (Logs) لمراقبة Railway ---
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# --- الإعدادات (يفضل وضعها في Variables في Railway) ---
API_KEYS = ["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", "KEY_2_HERE"]
TELEGRAM_TOKEN = "8605364115:AAHUmg2qyAanzsjLBUEoc5dS9ECaipyRrZY"
ADMIN_ID = 8443969410
current_key_index = 0

# --- البرومبت الداخلي (قوة المحرك) ---
SYSTEM_PROMPT = """
أنت الآن "The Master Book Architect". مهمتك هي تأليف مجلدات ضخمة.
1. التخطيط: صمم هيكل فصول منطقي وعميق.
2. اللغة: استخدم لغة فخمة، سردية، ومفصلة جداً.
3. التنسيق: ممنوع استخدام الرموز (#, *, -). استخدم أسطر نظيفة فقط.
أنت تنافس أعظم الكتاب في العالم، اجعل كل صفحة تحفة فنية.
"""

# --- إدارة قاعدة البيانات ---
def init_db():
    conn = sqlite3.connect('architect_data.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, expiry_date TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS chat_history (user_id INTEGER, role TEXT, content TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS book_progress (user_id INTEGER, title TEXT, content TEXT)''')
    conn.commit()
    conn.close()

init_db()

# --- وظائف مساعدة ---
def is_subscribed(user_id):
    if user_id == ADMIN_ID: return True
    conn = sqlite3.connect('architect_data.db')
    user = conn.execute("SELECT expiry_date FROM users WHERE user_id=?", (user_id,)).fetchone()
    conn.close()
    if user:
        expiry = datetime.datetime.strptime(user[0], '%Y-%m-%d')
        return expiry > datetime.datetime.now()
    return False

async def safe_ai_request(messages):
    global current_key_index
    for _ in range(len(API_KEYS) * 2):
        try:
            client = Groq(api_key=API_KEYS[current_key_index])
            completion = client.chat.completions.create(
                model="openai/gpt-oss-120b",
                messages=messages,
                temperature=0.7
            )
            return completion.choices[0].message.content
        except Exception as e:
            if "429" in str(e):
                current_key_index = (current_key_index + 1) % len(API_KEYS)
                await asyncio.sleep(10)
            else:
                logger.error(f"AI Error: {e}")
                await asyncio.sleep(5)
    return None

def create_pdf(chapters, filename):
    try:
        pdf = FPDF()
        pdf.set_auto_page_break(auto=True, margin=15)
        font_path = os.path.join(os.getcwd(), "arial.ttf")
        
        if os.path.exists(font_path):
            pdf.add_font('ArabicFont', '', font_path, uni=True)
            font_name = 'ArabicFont'
        else:
            font_name = 'Arial'
            logger.warning("arial.ttf not found! Using Arial fallback.")

        for title, content in chapters:
            pdf.add_page()
            pdf.set_font(font_name, size=20)
            pdf.multi_cell(190, 15, txt=get_display(reshape(title)), align='C')
            pdf.ln(10)
            pdf.set_font(font_name, size=13)
            pdf.multi_cell(190, 10, txt=get_display(reshape(content)), align='R')

        pdf.output(filename)
        return True
    except Exception as e:
        logger.error(f"PDF Error: {e}")
        return False

# --- معالجة الأوامر ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if is_subscribed(user_id):
        await update.message.reply_text("✅ **مرحباً بك في المحرك السيادي.**\nأرسل فكرة كتابك الآن، وعند الجاهزية أرسل /build.")
    else:
        keyboard = [[InlineKeyboardButton("💳 تفعيل الاشتراك (25 نجمة)", callback_data="pay")]]
        await update.message.reply_text(
            "👑 **Architect AI**\n\nلتأليف كتب ضخمة ومجلدات PDF احترافية.\nسعر الاشتراك: 25 نجمة شهرياً.",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

async def pay(update: Update, context: ContextTypes.DEFAULT_TYPE):
    prices = [LabeledPrice("الاشتراك الشهري", 25)]
    await context.bot.send_invoice(
        update.effective_chat.id, "تفعيل المحرك", "اشتراك 30 يوم", "sub", "", "XTR", prices
    )

async def pre_checkout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.pre_checkout_query.answer(ok=True)

async def success_pay(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    expiry = (datetime.datetime.now() + datetime.timedelta(days=30)).strftime('%Y-%m-%d')
    conn = sqlite3.connect('architect_data.db')
    conn.execute("INSERT OR REPLACE INTO users VALUES (?, ?)", (user_id, expiry))
    conn.commit()
    conn.close()
    await update.message.reply_text("🎉 تم تفعيل القوة الكاملة للمحرك لمدة شهر!")

async def build(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_subscribed(user_id): return

    conn = sqlite3.connect('architect_data.db')
    history = [{"role": r[0], "content": r[1]} for r in conn.execute("SELECT role, content FROM chat_history WHERE user_id=?", (user_id,)).fetchall()]
    
    if not history:
        await update.message.reply_text("❌ الذاكرة فارغة.")
        return

    status = await update.message.reply_text("🛠 جاري تشغيل المحرك وتنسيق الفصول...")

    # 1. الخطة
    check = conn.execute("SELECT title FROM book_progress WHERE user_id=?", (user_id,)).fetchall()
    if not check:
        plan = await safe_ai_request(history + [{"role": "system", "content": "أعطني 6 عناوين فصول دسمة بدون رموز."}])
        if plan:
            for t in plan.split('\n'):
                if t.strip(): conn.execute("INSERT INTO book_progress VALUES (?, ?, ?)", (user_id, t.strip(), ""))
            conn.commit()

    # 2. التأليف
    chapters = conn.execute("SELECT title, content FROM book_progress WHERE user_id=?", (user_id,)).fetchall()
    for i, (title, content) in enumerate(chapters):
        if not content:
            await status.edit_text(f"✍️ تأليف الفصل {i+1}/{len(chapters)}: {title}")
            body = await safe_ai_request(history + [{"role": "system", "content": f"اكتب فصلاً مفصلاً جداً عن ({title}) بدون رموز ماركداون."}])
            if body:
                conn.execute("UPDATE book_progress SET content=? WHERE user_id=? AND title=?", (body, user_id, title))
                conn.commit()
                await asyncio.sleep(10)

    # 3. الـ PDF
    await status.edit_text("🎨 جاري تصدير المجلد النهائي...")
    final_data = conn.execute("SELECT title, content FROM book_progress WHERE user_id=?", (user_id,)).fetchall()
    pdf_name = f"Book_{user_id}.pdf"
    
    if create_pdf(final_data, pdf_name):
        with open(pdf_name, "rb") as doc:
            await context.bot.send_document(chat_id=user_id, document=doc, caption="✅ اكتمل الكتاب بنجاح!")
    
    # تنظيف
    conn.execute("DELETE FROM chat_history WHERE user_id=?", (user_id,))
    conn.execute("DELETE FROM book_progress WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()
    if os.path.exists(pdf_name): os.remove(pdf_name)

async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_subscribed(user_id): return
    
    conn = sqlite3.connect('architect_data.db')
    conn.execute("INSERT INTO chat_history VALUES (?, ?, ?)", (user_id, "user", update.message.text))
    conn.commit()
    
    history = [{"role": "system", "content": SYSTEM_PROMPT}] + [{"role": r[0], "content": r[1]} for r in conn.execute("SELECT role, content FROM chat_history WHERE user_id=?", (user_id,)).fetchall()]
    
    res = await safe_ai_request(history)
    if res:
        conn.execute("INSERT INTO chat_history VALUES (?, ?, ?)", (user_id, "assistant", res))
        conn.commit()
        await update.message.reply_text(res)
    conn.close()

# --- التشغيل ---
if __name__ == '__main__':
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("build", build))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, success_pay))
    app.add_handler(PreCheckoutQueryHandler(pre_checkout))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat))
    
    print("🚀 Architect AI is Online...")
    app.run_polling()
