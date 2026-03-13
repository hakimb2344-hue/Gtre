import os
import sqlite3
import logging
import datetime
import random
import re
import asyncio
from groq import Groq
from telegram import Update, LabeledPrice, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, PreCheckoutQueryHandler, CallbackQueryHandler
from fpdf import FPDF
from arabic_reshaper import reshape
from bidi.algorithm import get_display

# --- إعداد السجلات ---
logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)

# --- الإعدادات (نظام المفتاحين) ---
API_KEYS = [
    "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", 
    "ضع_المفتاح_الثاني_هنا"
]
current_key_index = 0
TELEGRAM_TOKEN = "8605364115:AAHUmg2qyAanzsjLBUEoc5dS9ECaipyRrZY"
CHANNEL_ID = "@forgeflow_project"
ADMIN_ID = 8443969410

# --- محرك التبديل بين المفاتيح والرد السريع ---
async def ai_req_fast(msgs):
    global current_key_index
    for _ in range(len(API_KEYS)):
        try:
            client = Groq(api_key=API_KEYS[current_key_index])
            # استخدام موديل Llama 3 70B لمعالجة البرومبتات الضخمة بسرعة
            res = client.chat.completions.create(
                model="llama3-70b-8192", 
                messages=msgs, 
                temperature=0.6,
                max_tokens=4096 # دعم مخرجات طويلة
            )
            return res.choices[0].message.content
        except Exception as e:
            logging.error(f"Key {current_key_index} failed: {e}")
            current_key_index = (current_key_index + 1) % len(API_KEYS)
            await asyncio.sleep(1)
    return None

# --- قاعدة البيانات ---
def init_db():
    conn = sqlite3.connect('architect_ultra.db')
    conn.execute('CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, expiry TEXT)')
    conn.execute('CREATE TABLE IF NOT EXISTS chat_history (user_id INTEGER, role TEXT, content TEXT)')
    conn.execute('CREATE TABLE IF NOT EXISTS book_progress (user_id INTEGER, title TEXT, content TEXT)')
    conn.commit()
    conn.close()

init_db()

# --- محرك PDF (فلتر الصفحات الفارغة ودعم العربية) ---
def create_pdf(chapters, filename, decoration="—"):
    try:
        pdf = FPDF()
        pdf.set_auto_page_break(auto=True, margin=15)
        font_path = "arial.ttf"
        
        if os.path.exists(font_path):
            pdf.add_font('ArFont', '', font_path, uni=True)
            pdf.set_font('ArFont', size=14)
        else:
            pdf.set_font('Arial', size=12)

        pages_added = 0
        for title, content in chapters:
            if not content or len(content.strip()) < 100: continue # فلتر صارم
            
            pdf.add_page()
            pages_added += 1
            
            # العناوين
            pdf.set_text_color(30, 60, 150)
            pdf.set_font(size=22) if os.path.exists(font_path) else pdf.set_font('Arial', 'B', 18)
            pdf.multi_cell(190, 10, txt=get_display(reshape(f"{decoration} {title} {decoration}")), align='C')
            
            # المحتوى
            pdf.ln(10)
            pdf.set_text_color(0, 0, 0)
            pdf.set_font(size=14) if os.path.exists(font_path) else pdf.set_font('Arial', size=12)
            clean_text = re.sub(r'[*_#`]', '', content)
            pdf.multi_cell(190, 9, txt=get_display(reshape(clean_text)), align='R')

        if pages_added == 0: return False
        pdf.output(filename)
        return True
    except Exception as e:
        logging.error(f"PDF Error: {e}")
        return False

# --- التعامل مع الرسائل والبرومبتات الضخمة ---
async def handle_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    txt = update.message.text
    
    # الرد المبدئي السريع لضمان التفاعل
    status_msg = await update.message.reply_text("⚡ جاري المعالجة...")
    
    # نظام الذاكرة
    conn = sqlite3.connect('architect_ultra.db')
    conn.execute("INSERT INTO chat_history VALUES (?, 'user', ?)", (uid, txt))
    
    # سياق المحادثة (آخر 10 رسائل لدعم البرومبتات الضخمة)
    rows = conn.execute("SELECT role, content FROM chat_history WHERE user_id=? ORDER BY rowid DESC LIMIT 10", (uid,)).fetchall()
    history = [{"role": "system", "content": "أنت مساعد خبير في هندسة الكتب. برومبتاتك دقيقة، دسمة، ومنظمة."}]
    for r in reversed(rows):
        history.append({"role": r[0], "content": r[1]})

    reply = await ai_req_fast(history)
    
    if reply:
        conn.execute("INSERT INTO chat_history VALUES (?, 'assistant', ?)", (uid, reply))
        conn.commit()
        await status_msg.edit_text(reply)
    else:
        await status_msg.edit_text("⚠️ حدث خطأ في الاتصال، تم التبديل للمفتاح الاحتياطي. أعد المحاولة.")
    conn.close()

# --- أمر التأليف (Build) - معالجة سريعة للفصول ---
async def build_book(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    status = await update.message.reply_text("🏗️ جاري تأليف المجلد (24 فصل)... قد يستغرق الأمر دقيقة واحدة بفضل المعالجة المتوازية.")
    
    # جلب خطة الكتاب من الذاكرة
    conn = sqlite3.connect('architect_ultra.db')
    hist = conn.execute("SELECT content FROM chat_history WHERE user_id=? AND role='user' ORDER BY rowid DESC LIMIT 1", (uid,)).fetchone()
    
    if not hist:
        await status.edit_text("⚠️ لا يوجد موضوع لمناقشته. ابدأ بكتابة فكرتك أولاً.")
        return

    # استراتيجية المعالجة السريعة: توليد المحتوى
    # ملاحظة: تم تبسيط التوليد هنا لضمان عدم تجاوز مهلة تليجرام، ولكن مع الحفاظ على الكثافة
    chapters = []
    # طلب توليد 3 فصول ضخمة في كل طلب AI لتسريع الوقت
    for i in range(1, 25, 3):
        prompt = f"Write chapters {i}, {i+1}, and {i+2} for a book about: {hist[0]}. Each chapter must be 800 words, highly detailed, and academic."
        content_block = await ai_req_fast([{"role": "user", "content": prompt}])
        if content_block:
            chapters.append((f"Section {i}-{i+2}", content_block))
            await status.edit_text(f"✍️ تم إنجاز الفصول حتى {i+2}...")

    filename = f"Architect_{uid}.pdf"
    if create_pdf(chapters, filename):
        with open(filename, "rb") as f:
            await context.bot.send_document(chat_id=uid, document=f, caption="✅ اكتمل المجلد بنجاح.\nتم فلترة الصفحات الفارغة.")
        os.remove(filename)
    else:
        await status.edit_text("❌ فشل في توليد محتوى كافٍ. حاول زيادة تفاصيل البرومبت.")
    conn.close()

# --- الأوامر الأساسية ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("💎 **Architect AI Ultra**\nنظام المفاتيح المزدوجة فعال. أرسل موضوعك الآن.")

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("build", build_book))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_chat))
    
    print("🚀 المحرك فائق السرعة يعمل الآن...")
    app.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()
