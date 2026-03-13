import os
import asyncio
import sqlite3
import time
import logging
from groq import Groq
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from fpdf import FPDF
from arabic_reshaper import reshape
from bidi.algorithm import get_display

# إعداد السجلات لمراقبة الأخطاء في الكونسول
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# --- إعدادات الاتصال ---
API_KEYS = [
    "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", 
    ""
]
TELEGRAM_TOKEN = "8605364115:AAHUmg2qyAanzsjLBUEoc5dS9ECaipyRrZY"
ADMIN_ID = 8443969410 # تأكد أن هذا هو الآيدي الخاص بك

current_key_index = 0

def rotate_key():
    global current_key_index
    current_key_index = (current_key_index + 1) % len(API_KEYS)
    print(f"🔄 تم التبديل للمفتاح رقم {current_key_index + 1}")

def get_client():
    return Groq(api_key=API_KEYS[current_key_index])

# --- قاعدة البيانات ---
def init_db():
    conn = sqlite3.connect('ebook_master.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS chat_history (user_id INTEGER, role TEXT, content TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS book_progress (user_id INTEGER, title TEXT, content TEXT)''')
    conn.commit()
    conn.close()

init_db()

# --- محرك الـ PDF ---
def create_pdf(chapters, filename):
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    try:
        pdf.add_font('ArabicFont', '', 'arial.ttf', uni=True)
        font_name = 'ArabicFont'
    except:
        font_name = 'Arial' # Fallback

    for title, content in chapters:
        pdf.add_page()
        pdf.set_font(font_name, size=20)
        pdf.multi_cell(190, 15, txt=get_display(reshape(title)), align='C')
        pdf.ln(10)
        pdf.set_font(font_name, size=14)
        pdf.multi_cell(190, 10, txt=get_display(reshape(content)), align='R')

    pdf.add_page()
    pdf.set_font(font_name, size=12)
    pdf.set_text_color(100, 100, 100)
    footer = "تم اكتمال الكتاب بنجاح من السيرفر حتى الحرف الأخير - تم مسح الذاكرة المؤقتة."
    pdf.multi_cell(190, 10, txt=get_display(reshape(footer)), align='C')
    pdf.output(filename)

# --- طلب الذكاء الاصطناعي ---
async def safe_ai_request(messages):
    for attempt in range(len(API_KEYS) * 2):
        try:
            client = get_client()
            completion = client.chat.completions.create(
                model="openai/gpt-oss-120b",
                messages=messages,
                temperature=0.7
            )
            return completion.choices[0].message.content
        except Exception as e:
            if "429" in str(e):
                rotate_key()
                await asyncio.sleep(5)
            else:
                print(f"❌ خطأ API: {e}")
                await asyncio.sleep(2)
    return None

# --- معالجة الرسائل والأوامر ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 مرحباً! أنا بوت تأليف الكتب الرقمية.\n\nأرسل لي فكرة كتابك، وعندما تنتهي أرسل /build.")

async def handle_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text

    # حفظ في القاعدة
    conn = sqlite3.connect('ebook_master.db')
    conn.execute("INSERT INTO chat_history VALUES (?, ?, ?)", (user_id, "user", text))
    conn.commit()

    # الرد التلقائي
    await context.bot.send_chat_action(chat_id=user_id, action="typing")
    history = [{"role": r[0], "content": r[1]} for r in conn.execute("SELECT role, content FROM chat_history WHERE user_id=?", (user_id,)).fetchall()]
    
    response = await safe_ai_request(history)
    if response:
        conn.execute("INSERT INTO chat_history VALUES (?, ?, ?)", (user_id, "assistant", response))
        conn.commit()
        await update.message.reply_text(response)
    conn.close()

async def build(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("🚫 عذراً، هذا الأمر للمدير فقط.")
        return

    conn = sqlite3.connect('ebook_master.db')
    history = [{"role": r[0], "content": r[1]} for r in conn.execute("SELECT role, content FROM chat_history WHERE user_id=?", (user_id,)).fetchall()]
    
    if not history:
        await update.message.reply_text("⭕ الذاكرة فارغة. ناقشني في فكرة أولاً.")
        return

    status_msg = await update.message.reply_text("🚀 جاري تحضير المحرك وفحص الفصول...")

    # 1. الخطة
    check = conn.execute("SELECT title FROM book_progress WHERE user_id=?", (user_id,)).fetchall()
    if not check:
        await status_msg.edit_text("📋 المرحلة 1: هندسة هيكل الكتاب...")
        res = await safe_ai_request(history + [{"role": "system", "content": "أعطني 6 عناوين فصول دسمة للموضوع الأخير، العناوين فقط بدون رموز."}])
        if res:
            for t in res.split('\n'):
                if t.strip(): conn.execute("INSERT INTO book_progress VALUES (?, ?, ?)", (user_id, t.strip(), ""))
            conn.commit()

    # 2. التأليف
    chapters = conn.execute("SELECT title, content FROM book_progress WHERE user_id=?", (user_id,)).fetchall()
    for i, (title, content) in enumerate(chapters):
        if not content:
            await status_msg.edit_text(f"✍️ المرحلة 2: تأليف الفصل {i+1} من {len(chapters)}\n📌 {title}")
            body = await safe_ai_request(history + [{"role": "system", "content": f"اكتب فصلاً كاملاً لـ ({title}) بدون رموز الماركداون."}])
            if body:
                conn.execute("UPDATE book_progress SET content=? WHERE user_id=? AND title=?", (body, user_id, title))
                conn.commit()
                await asyncio.sleep(5)

    # 3. PDF
    await status_msg.edit_text("🎨 المرحلة 3: جاري تصدير ملف PDF...")
    final_chapters = conn.execute("SELECT title, content FROM book_progress WHERE user_id=?", (user_id,)).fetchall()
    pdf_name = f"Book_{user_id}.pdf"
    create_pdf(final_chapters, pdf_name)
    
    await context.bot.send_document(chat_id=user_id, document=open(pdf_name, "rb"), caption="✅ تم إنتاج المجلد بنجاح!")
    
    # تنظيف
    conn.execute("DELETE FROM chat_history WHERE user_id=?", (user_id,))
    conn.execute("DELETE FROM book_progress WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()
    if os.path.exists(pdf_name): os.remove(pdf_name)

# --- التشغيل الرئيسي ---
if __name__ == '__main__':
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("build", build))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_chat))
    
    print("🤖 البوت يعمل الآن... أرسل رسالة لتجريبه!")
    app.run_polling()
