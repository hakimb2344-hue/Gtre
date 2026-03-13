import logging
import os
import time
import asyncio
import sqlite3
from groq import Groq
from telegram import Update, LabeledPrice
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, PreCheckoutQueryHandler
from fpdf import FPDF
import arabic_reshaper
from bidi.algorithm import get_display

# --- الإعدادات ---
GROQ_API_KEY = "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"
TELEGRAM_TOKEN = "8605364115:AAHUmg2qyAanzsjLBUEoc5dS9ECaipyRrZY"
ADMIN_ID = 8443969410

client = Groq(api_key=GROQ_API_KEY)

# --- إعداد قاعدة البيانات ---
def init_db():
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    # جدول المحادثات
    c.execute('''CREATE TABLE IF NOT EXISTS chat_history (user_id INTEGER, role TEXT, content TEXT)''')
    # جدول الفصول المكتملة (التخزين المؤقت للبناء)
    c.execute('''CREATE TABLE IF NOT EXISTS pending_books (user_id INTEGER, chapter_title TEXT, chapter_content TEXT)''')
    # جدول المستخدمين VIP
    c.execute('''CREATE TABLE IF NOT EXISTS vips (user_id INTEGER PRIMARY KEY)''')
    conn.commit()
    conn.close()

init_db()

# --- وظائف قاعدة البيانات ---
def save_message(user_id, role, content):
    conn = sqlite3.connect('bot_data.db')
    conn.execute("INSERT INTO chat_history VALUES (?, ?, ?)", (user_id, role, content))
    conn.commit()
    conn.close()

def get_history(user_id):
    conn = sqlite3.connect('bot_data.db')
    cursor = conn.execute("SELECT role, content FROM chat_history WHERE user_id=?", (user_id,))
    history = [{"role": row[0], "content": row[1]} for row in cursor.fetchall()]
    conn.close()
    return history

def clear_user_data(user_id):
    conn = sqlite3.connect('bot_data.db')
    conn.execute("DELETE FROM chat_history WHERE user_id=?", (user_id,))
    conn.execute("DELETE FROM pending_books WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()

# --- نظام معالجة PDF ---
def create_final_pdf(chapters, filename):
    pdf = FPDF()
    pdf.add_page()
    try:
        pdf.add_font('ArabicFont', '', 'arial.ttf', uni=True)
        pdf.set_font('ArabicFont', size=14)
    except:
        pdf.set_font("Arial", size=12)

    reshaper = arabic_reshaper.ArabicReshaper({'delete_harakat': False, 'support_ligatures': True})
    
    for title, content in chapters:
        # إضافة العنوان (أحمر)
        pdf.set_text_color(200, 0, 0)
        pdf.multi_cell(190, 10, txt=get_display(reshaper.reshape(f"--- {title} ---")), align='C')
        pdf.ln(10)
        # إضافة المحتوى (أسود)
        pdf.set_text_color(0, 0, 0)
        pdf.multi_cell(190, 10, txt=get_display(reshaper.reshape(content)), align='R')
        pdf.add_page() 

    pdf.output(filename)

# --- محرك بناء الكتاب مع خاصية "التكملة" ---
async def build_large_book(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    history = get_history(user_id)
    
    if not history:
        await update.message.reply_text("❌ الذاكرة فارغة. ناقشني أولاً.")
        return

    # 1. تحديد الفصول (إذا لم تكن محددة مسبقاً)
    conn = sqlite3.connect('bot_data.db')
    existing_chapters = conn.execute("SELECT chapter_title FROM pending_books WHERE user_id=?", (user_id,)).fetchall()
    
    status_msg = await update.message.reply_text("🛠 جاري فحص التقدم المسبق وتجهيز المحرك...")

    if not existing_chapters:
        await status_msg.edit_text("📋 جاري وضع خطة الكتاب (الفصول)...")
        plan_prompt = history + [{"role": "system", "content": "أعطني قائمة بأسماء 6 فصول فقط لهذا الكتاب، كل فصل في سطر."}]
        res = client.chat.completions.create(model="openai/gpt-oss-120b", messages=plan_prompt)
        titles = [t.strip() for t in res.choices[0].message.content.split('\n') if t.strip()]
        # حفظ العناوين فارغة لبدء التعبئة
        for t in titles:
            conn.execute("INSERT INTO pending_books VALUES (?, ?, ?)", (user_id, t, ""))
        conn.commit()
    
    # 2. تعبئة الفصول الناقصة
    rows = conn.execute("SELECT chapter_title, chapter_content FROM pending_books WHERE user_id=?", (user_id,)).fetchall()
    
    for i, (title, content) in enumerate(rows):
        if content == "": # هذا الفصل لم يكتمل بعد
            await status_msg.edit_text(f"✍️ جاري تأليف: {title}...")
            
            # نظام تبريد (راحة)
            await asyncio.sleep(4) 
            
            chapter_prompt = history + [{"role": "system", "content": f"اكتب محتوى الفصل التالي بالتفصيل الكامل: {title}"}]
            try:
                chapter_res = client.chat.completions.create(model="openai/gpt-oss-120b", messages=chapter_prompt)
                chapter_content = chapter_res.choices[0].message.content
                # تحديث قاعدة البيانات فوراً
                conn.execute("UPDATE pending_books SET chapter_content=? WHERE user_id=? AND chapter_title=?", (chapter_content, user_id, title))
                conn.commit()
            except Exception as e:
                await update.message.reply_text(f"⚠️ توقف المحرك مؤقتاً عند {title}. أرسل /build مرة أخرى لاحقاً للتكملة.")
                conn.close()
                return

    # 3. التجميع النهائي في ملف واحد
    await status_msg.edit_text("📚 اكتمل التأليف! جاري تجميع الفصول في ملف PDF واحد...")
    all_chapters = conn.execute("SELECT chapter_title, chapter_content FROM pending_books WHERE user_id=?", (user_id,)).fetchall()
    conn.close()

    file_path = f"Final_Book_{user_id}.pdf"
    create_final_pdf(all_chapters, file_path)

    with open(file_path, 'rb') as f:
        await context.bot.send_document(chat_id=user_id, document=f, caption="✅ تم إنتاج كتابك بالكامل بنجاح!")
    
    # مسح شامل بعد النجاح فقط
    clear_user_data(user_id)
    os.remove(file_path)

# --- الأوامر الأساسية ---

async def handle_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    save_message(user_id, "user", text)
    
    # جلب رد الذكاء الاصطناعي
    history = get_history(user_id)
    response = client.chat.completions.create(model="openai/gpt-oss-120b", messages=history).choices[0].message.content
    save_message(user_id, "assistant", response)
    
    await update.message.reply_text(response)

# (أضف دوال الدفع والـ Start كما في الكود السابق مع ربطها بـ build_large_book)

if __name__ == '__main__':
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("build", build_large_book))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_msg))
    app.run_polling()
