import os
import sqlite3
import logging
import datetime
import random
import re
from groq import Groq
from telegram import Update, LabeledPrice, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, PreCheckoutQueryHandler, CallbackQueryHandler
from fpdf import FPDF
from arabic_reshaper import reshape
from bidi.algorithm import get_display

# --- الإعدادات ---
logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
API_KEY_GROQ = "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"
TELEGRAM_TOKEN = "8605364115:AAHUmg2qyAanzsjLBUEoc5dS9ECaipyRrZY"
CHANNEL_ID = "@forgeflow_project"
ADMIN_ID = 8443969410

# --- قاعدة البيانات ---
def init_db():
    conn = sqlite3.connect('architect_final.db')
    conn.execute('CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, expiry TEXT)')
    conn.execute('CREATE TABLE IF NOT EXISTS chat_history (user_id INTEGER, role TEXT, content TEXT)')
    conn.execute('CREATE TABLE IF NOT EXISTS book_progress (user_id INTEGER, title TEXT, content TEXT)')
    conn.commit()
    conn.close()

init_db()

# --- محرك الـ PDF (بدون أوراق فارغة) ---
def create_pdf(chapters, filename, decoration="—"):
    try:
        pdf = FPDF()
        pdf.set_auto_page_break(auto=True, margin=15)
        # تأكد من رفع ملف arial.ttf في المجلد الرئيسي
        font_path = "arial.ttf"
        if os.path.exists(font_path):
            pdf.add_font('ArFont', '', font_path, uni=True)
            pdf.set_font('ArFont', size=14)
        else:
            pdf.set_font('Arial', size=12)

        pages_added = 0
        for title, content in chapters:
            if not content or len(content.strip()) < 100: # فلتر الصفحات الفارغة
                continue
            
            pdf.add_page()
            pages_added += 1
            
            # العناوين المزخرفة
            title_text = f"{decoration} {title} {decoration}"
            pdf.set_text_color(20, 40, 120)
            pdf.cell(190, 10, txt=get_display(reshape(title_text)), align='C', ln=True)
            
            # المحتوى
            pdf.ln(10)
            pdf.set_text_color(0, 0, 0)
            clean_text = re.sub(r'[*_#`]', '', content)
            pdf.multi_cell(190, 8, txt=get_display(reshape(clean_text)), align='R')

        if pages_added == 0: return False
        pdf.output(filename)
        return True
    except Exception as e:
        logging.error(f"PDF Error: {e}")
        return False

# --- أوامر البوت ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    conn = sqlite3.connect('architect_final.db')
    user = conn.execute("SELECT expiry FROM users WHERE user_id=?", (uid,)).fetchone()
    conn.close()
    
    is_valid = uid == ADMIN_ID or (user and datetime.datetime.strptime(user[0], '%Y-%m-%d') > datetime.datetime.now())
    
    if is_valid:
        await update.message.reply_text("📖 المحرك جاهز! ناقشني في فكرتك الآن.")
    else:
        kb = [[InlineKeyboardButton("💳 تفعيل (25 نجمة)", callback_data="pay")]]
        await update.message.reply_text("🛑 يرجى التفعيل للمتابعة.", reply_markup=InlineKeyboardMarkup(kb))

async def handle_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    txt = update.message.text
    
    # حفظ النقاش
    conn = sqlite3.connect('architect_final.db')
    conn.execute("INSERT INTO chat_history VALUES (?, 'user', ?)", (uid, txt))
    conn.commit()

    # جلب رد الذكاء الاصطناعي
    try:
        client = Groq(api_key=API_KEY_GROQ)
        res = client.chat.completions.create(
            model="llama3-70b-8192",
            messages=[{"role": "system", "content": "أنت مهندس كتب. ناقش المستخدم بذكاء."}, {"role": "user", "content": txt}]
        )
        reply = res.choices[0].message.content
        conn.execute("INSERT INTO chat_history VALUES (?, 'assistant', ?)", (uid, reply))
        conn.commit()
        await update.message.reply_text(reply)
    except Exception as e:
        await update.message.reply_text("⚠️ المحرك مشغول، حاول مجدداً.")
    conn.close()

async def build_book(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    status = await update.message.reply_text("🏗️ جاري تأليف الكتاب وفلترة الصفحات...")
    
    conn = sqlite3.connect('architect_final.db')
    # هنا يتم استدعاء الفصول (كمثال سيتم توليد فصل واحد دسم)
    # ملاحظة: في النسخة الكاملة يتم التكرار على 24 فصلاً
    chapters = [("Introduction", "هذا نص تجريبي دسم جداً للتأكد من أن الصفحة لن تظهر فارغة... " * 50)]
    
    filename = f"Book_{uid}.pdf"
    if create_pdf(chapters, filename):
        with open(filename, "rb") as f:
            await context.bot.send_document(chat_id=uid, document=f, caption="✅ كتابك جاهز بدون صفحات فارغة.")
        os.remove(filename)
    else:
        await update.message.reply_text("❌ لم يتم توليد محتوى كافٍ لإنشاء الكتاب.")
    conn.close()

# --- النشر التلقائي ---
async def auto_post(context: ContextTypes.DEFAULT_TYPE):
    try:
        await context.bot.send_message(chat_id=CHANNEL_ID, text="📢 ألف كتابك الخاص الآن مع @ArchitectAI")
    except: pass

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("build", build_book))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_chat))
    
    if app.job_queue:
        app.job_queue.run_repeating(auto_post, interval=43200, first=10)
    
    app.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()
