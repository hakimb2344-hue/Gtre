import os
import asyncio
import sqlite3
import time
from groq import Groq
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from fpdf import FPDF
from arabic_reshaper import reshape
from bidi.algorithm import get_display

# --- الإعدادات ---
API_KEYS = [
    "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", 
    "ضع_المفتاح_الثاني_هنا"
]
TELEGRAM_TOKEN = "8605364115:AAHUmg2qyAanzsjLBUEoc5dS9ECaipyRrZY"
ADMIN_ID = 8443969410
current_key_index = 0

def rotate_key():
    global current_key_index
    current_key_index = (current_key_index + 1) % len(API_KEYS)
    return current_key_index + 1

def get_client():
    return Groq(api_key=API_KEYS[current_key_index])

# --- محرك الـ PDF المحسن ---
def create_pdf(chapters, filename):
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    # تأكد من وضع ملف arial.ttf في المجلد
    pdf.add_font('ArabicFont', '', 'arial.ttf', uni=True)
    
    for title, content in chapters:
        pdf.add_page()
        # العنوان
        pdf.set_font('ArabicFont', size=22)
        pdf.multi_cell(190, 15, txt=get_display(reshape(title)), align='C')
        pdf.ln(10)
        # المحتوى
        pdf.set_font('ArabicFont', size=14)
        pdf.multi_cell(190, 10, txt=get_display(reshape(content)), align='R')

    pdf.add_page()
    pdf.set_font('ArabicFont', size=12)
    pdf.set_text_color(100, 100, 100)
    footer = "تم اكتمال الكتاب بنجاح من السيرفر حتى الحرف الأخير - تم مسح الذاكرة المؤقتة."
    pdf.multi_cell(190, 10, txt=get_display(reshape(footer)), align='C')
    pdf.output(filename)

# --- طلب الذكاء الاصطناعي ---
async def safe_ai_request(messages):
    for attempt in range(4):
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
                await asyncio.sleep(10)
            else:
                await asyncio.sleep(5)
    return None

# --- أوامر البوت ---
async def build(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID: return

    conn = sqlite3.connect('ebook_engine.db')
    history = [{"role": r[0], "content": r[1]} for r in conn.execute("SELECT role, content FROM chat_history WHERE user_id=?", (user_id,)).fetchall()]
    
    if not history:
        await update.message.reply_text("❌ الذاكرة فارغة. ناقشني في فكرة أولاً!")
        return

    # رسالة الحالة التفاعلية
    status_msg = await update.message.reply_text("⚡ **بدء تشغيل المحرك السيادي...**\n[░░░░░░░░░░] 0%")
    start_time = time.time()

    # 1. التخطيط
    await status_msg.edit_text("📋 **المرحلة 1:** جاري هندسة هيكل الكتاب وضبط الفصول...\n[▓░░░░░░░░░] 10%")
    check = conn.execute("SELECT title FROM book_progress WHERE user_id=?", (user_id,)).fetchall()
    if not check:
        res = await safe_ai_request(history + [{"role": "system", "content": "أعطني 6 عناوين فصول دسمة، العناوين فقط، بدون رموز."}])
        if res:
            titles = [t.strip() for t in res.split('\n') if t.strip()]
            for t in titles:
                conn.execute("INSERT INTO book_progress VALUES (?, ?, ?)", (user_id, t, ""))
            conn.commit()

    # 2. التأليف المتقدم
    chapters_data = conn.execute("SELECT title, content FROM book_progress WHERE user_id=?", (user_id,)).fetchall()
    total = len(chapters_data)
    
    for i, (title, content) in enumerate(chapters_data):
        if not content:
            progress = int((i / total) * 80) + 10
            bar = "▓" * (progress // 10) + "░" * (10 - (progress // 10))
            await status_msg.edit_text(f"✍️ **المرحلة 2:** جاري تأليف الفصل {i+1} من {total}\n📌 العنوان: {title}\n🔑 المفتاح النشط: {current_key_index + 1}\n[{bar}] {progress}%")
            
            body = await safe_ai_request(history + [{"role": "system", "content": f"اكتب فصلاً كاملاً ومفصلاً لـ ({title}) بدون رموز الماركداون."}])
            if body:
                conn.execute("UPDATE book_progress SET content=? WHERE user_id=? AND title=?", (body, user_id, title))
                conn.commit()
                await asyncio.sleep(5) # تبريد

    # 3. التصميم والتحويل
    await status_msg.edit_text("🎨 **المرحلة 3:** جاري تصميم الـ PDF ودمج الفصول...\n[▓▓▓▓▓▓▓▓▓░] 90%")
    final_chapters = conn.execute("SELECT title, content FROM book_progress WHERE user_id=?", (user_id,)).fetchall()
    pdf_name = f"Book_{user_id}.pdf"
    
    create_pdf(final_chapters, pdf_name)
    
    end_time = round(time.time() - start_time, 2)
    await status_msg.edit_text(f"✅ **اكتمل البناء بنجاح!**\n⏱ الوقت المستغرق: {end_time} ثانية\n📦 جاري إرسال المجلد...")

    await context.bot.send_document(chat_id=user_id, document=open(pdf_name, "rb"), caption="📖 كتابك الرقمي جاهز بجودة PDF.")

    # تنظيف
    conn.execute("DELETE FROM chat_history WHERE user_id=?", (user_id,))
    conn.execute("DELETE FROM book_progress WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()
    if os.path.exists(pdf_name): os.remove(pdf_name)

# --- دالة المحادثة العادية (تحديث الذاكرة) ---
async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    conn = sqlite3.connect('ebook_engine.db')
    conn.execute("INSERT INTO chat_history VALUES (?, ?, ?)", (user_id, "user", update.message.text))
    conn.commit()
    
    # البوت يرسل إشارة "جاري التفكير"
    await context.bot.send_chat_action(chat_id=user_id, action="typing")
    
    history = [{"role": r[0], "content": r[1]} for r in conn.execute("SELECT role, content FROM chat_history WHERE user_id=?", (user_id,)).fetchall()]
    res = await safe_ai_request(history)
    if res:
        conn.execute("INSERT INTO chat_history VALUES (?, ?, ?)", (user_id, "assistant", res))
        conn.commit()
        await update.message.reply_text(res)
    conn.close()

# إعداد البوت... (نفس الـ Main السابق)
