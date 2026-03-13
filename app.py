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

# إعداد السجلات لمراقبة العمل من الكونسول
logging.basicConfig(format='%(asctime)s - %(message)s', level=logging.INFO)

# --- إعدادات الاتصال ---
API_KEYS = [
    "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", 
    "ضع_المفتاح_الثاني_هنا" # استبدل هذا بالمفتاح الثاني
]
TELEGRAM_TOKEN = "8605364115:AAHUmg2qyAanzsjLBUEoc5dS9ECaipyRrZY"
ADMIN_ID = 8443969410 

current_key_index = 0

def rotate_key():
    global current_key_index
    current_key_index = (current_key_index + 1) % len(API_KEYS)
    print(f"🔄 تدوير المفتاح: تم التحويل للمفتاح رقم {current_key_index + 1}")

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

# --- محرك الـ PDF المحسن ---
def create_pdf(chapters, filename):
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    
    # محاولة تحميل الخط العربي
    font_path = os.path.join(os.getcwd(), "arial.ttf")
    if os.path.exists(font_path):
        pdf.add_font('ArabicFont', '', font_path, uni=True)
        font_main = 'ArabicFont'
    else:
        print("⚠️ تحذير: لم يتم العثور على arial.ttf، سيظهر النص بتنسيق ضعيف.")
        font_main = 'Arial'

    for title, content in chapters:
        pdf.add_page()
        # العنوان
        pdf.set_font(font_main, size=22)
        pdf.multi_cell(190, 15, txt=get_display(reshape(title)), align='C')
        pdf.ln(10)
        # المحتوى (النص الذي كتبه البوت)
        pdf.set_font(font_main, size=14)
        pdf.multi_cell(190, 10, txt=get_display(reshape(content)), align='R')

    # صفحة الختام
    pdf.add_page()
    pdf.set_font(font_main, size=12)
    pdf.set_text_color(128, 128, 128)
    footer = "تم اكتمال الكتاب بنجاح من السيرفر حتى الحرف الأخير - تم مسح الذاكرة المؤقتة."
    pdf.multi_cell(190, 10, txt=get_display(reshape(footer)), align='C')
    pdf.output(filename)

# --- طلب الذكاء الاصطناعي مع نظام التكرار ---
async def safe_ai_request(messages, retries=5):
    for i in range(retries):
        try:
            client = get_client()
            completion = client.chat.completions.create(
                model="openai/gpt-oss-120b",
                messages=messages,
                temperature=0.8
            )
            return completion.choices[0].message.content
        except Exception as e:
            if "429" in str(e):
                rotate_key()
                await asyncio.sleep(20) # تبريد أطول للكتب الضخمة
            else:
                await asyncio.sleep(5)
    return None

# --- الأوامر الأساسية ---

async def handle_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    conn = sqlite3.connect('ebook_master.db')
    conn.execute("INSERT INTO chat_history VALUES (?, ?, ?)", (user_id, "user", update.message.text))
    conn.commit()
    
    history = [{"role": r[0], "content": r[1]} for r in conn.execute("SELECT role, content FROM chat_history WHERE user_id=?", (user_id,)).fetchall()]
    res = await safe_ai_request(history)
    if res:
        conn.execute("INSERT INTO chat_history VALUES (?, ?, ?)", (user_id, "assistant", res))
        conn.commit()
        await update.message.reply_text(res)
    conn.close()

async def build(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID: return

    conn = sqlite3.connect('ebook_master.db')
    history = [{"role": r[0], "content": r[1]} for r in conn.execute("SELECT role, content FROM chat_history WHERE user_id=?", (user_id,)).fetchall()]
    
    if not history:
        await update.message.reply_text("🧼 الذاكرة فارغة. ناقشني في موضوع أولاً!")
        return

    status_msg = await update.message.reply_text("🚀 **بدء عملية التأليف الضخمة...**\n[░░░░░░░░░░] 0%")

    # 1. المرحلة الأولى: الخطة
    check_plan = conn.execute("SELECT title FROM book_progress WHERE user_id=?", (user_id,)).fetchall()
    if not check_plan:
        await status_msg.edit_text("📋 **المرحلة 1:** وضع خطة الفصول...")
        plan_prompt = history + [{"role": "system", "content": "أعطني 6 عناوين فصول دسمة، العناوين فقط بدون رموز."}]
        res = await safe_ai_request(plan_prompt)
        if res:
            for t in res.split('\n'):
                if t.strip(): conn.execute("INSERT INTO book_progress VALUES (?, ?, ?)", (user_id, t.strip(), ""))
            conn.commit()

    # 2. المرحلة الثانية: التأليف (هنا يتم ملء المحتوى)
    chapters = conn.execute("SELECT title, content FROM book_progress WHERE user_id=?", (user_id,)).fetchall()
    total = len(chapters)
    
    for i, (title, content) in enumerate(chapters):
        if not content or len(content) < 50: # صمام أمان لضمان وجود محتوى
            progress = int(((i) / total) * 100)
            await status_msg.edit_text(f"✍️ **المرحلة 2:** تأليف الفصل {i+1} من {total}\n📌 {title}\n[{'▓' * (progress//10)}{'░' * (10-(progress//10))}] {progress}%")
            
            write_prompt = history + [{"role": "system", "content": f"Write a VERY DETAILED and LONG chapter for the title: ({title}). No markdown. Just raw text."}]
            body = await safe_ai_request(write_prompt)
            
            if body:
                conn.execute("UPDATE book_progress SET content=? WHERE user_id=? AND title=?", (body, user_id, title))
                conn.commit()
                await asyncio.sleep(10) # تبريد بين الفصول

    # 3. المرحلة الثالثة: التجميع والتحويل
    await status_msg.edit_text("🎨 **المرحلة 3:** جاري تجميع المحتوى في ملف PDF...")
    final_data = conn.execute("SELECT title, content FROM book_progress WHERE user_id=?", (user_id,)).fetchall()
    
    # فحص أخير قبل التصدير
    if not any(c[1] for c in final_data):
        await status_msg.edit_text("❌ خطأ: لم يتم العثور على محتوى للفصول. حاول مرة أخرى.")
        return

    pdf_name = f"Book_{user_id}.pdf"
    create_pdf(final_data, pdf_name)
    
    await context.bot.send_document(chat_id=user_id, document=open(pdf_name, "rb"), caption="✅ تم إنتاج الكتاب بالكامل بنجاح!")
    
    # تنظيف الذاكرة
    conn.execute("DELETE FROM chat_history WHERE user_id=?", (user_id,))
    conn.execute("DELETE FROM book_progress WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()
    if os.path.exists(pdf_name): os.remove(pdf_name)

if __name__ == '__main__':
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("build", build))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_chat))
    print("🤖 المحرك يعمل بنظام التكملة وصمامات الأمان... أرسل رسالة للبدء.")
    app.run_polling()
