import os
import asyncio
import sqlite3
from groq import Groq
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from fpdf import FPDF
from arabic_reshaper import reshape
from bidi.algorithm import get_display

# --- الإعدادات ---
API_KEYS = [
    "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", 
    "أدخل_المفتاح_الثاني_هنا"
]
TELEGRAM_TOKEN = "8605364115:AAHUmg2qyAanzsjLBUEoc5dS9ECaipyRrZY"
ADMIN_ID = 8443969410
current_key_index = 0

def rotate_key():
    global current_key_index
    current_key_index = 1 if current_key_index == 0 else 0
    print(f"🔄 تم التبديل للمفتاح رقم {current_key_index + 1}")

def get_client():
    return Groq(api_key=API_KEYS[current_key_index])

# --- دالة صناعة الـ PDF ---
def create_pdf(chapters, filename):
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    
    # يجب توفر ملف خط يدعم العربية في نفس المجلد باسم arial.ttf
    try:
        pdf.add_font('ArabicFont', '', 'arial.ttf', uni=True)
        pdf.set_font('ArabicFont', size=14)
    except:
        pdf.set_font("Arial", size=12) # fallback إذا لم يجد الخط

    for title, content in chapters:
        pdf.add_page()
        # تنسيق العنوان
        pdf.set_font('ArabicFont', size=18)
        pdf.multi_cell(190, 10, txt=get_display(reshape(title)), align='C')
        pdf.ln(10)
        # تنسيق المحتوى
        pdf.set_font('ArabicFont', size=12)
        pdf.multi_cell(190, 8, txt=get_display(reshape(content)), align='R')

    # إضافة جملة الختام في آخر صفحة كما طلبت
    pdf.ln(20)
    pdf.set_text_color(128, 128, 128)
    ختام = "تم اكتمال الكتاب بنجاح من السيرفر حتى الحرف الأخير - تم مسح الذاكرة المؤقتة."
    pdf.multi_cell(190, 10, txt=get_display(reshape(ختام)), align='C')
    pdf.output(filename)

# --- المحرك الرئيسي ---
async def safe_ai_request(messages):
    for _ in range(4):
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
                await asyncio.sleep(10)
    return None

async def build(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID: return

    conn = sqlite3.connect('ebook_engine.db')
    # جلب النقاش (مع استبعاد التعليمات البرمجية السابقة ليكون الكتاب "صافي")
    history = [{"role": r[0], "content": r[1]} for r in conn.execute("SELECT role, content FROM chat_history WHERE user_id=?", (user_id,)).fetchall()]
    
    if not history:
        await update.message.reply_text("🧼 الذاكرة فارغة. ابدأ بموضوع جديد!")
        return

    status = await update.message.reply_text("🛠 جاري تحضير ملف الـ PDF... انتظر قليلاً.")

    # 1. وضع الخطة
    check = conn.execute("SELECT title FROM book_progress WHERE user_id=?", (user_id,)).fetchall()
    if not check:
        res = await safe_ai_request(history + [{"role": "system", "content": "أعطني 6 عناوين فصول دسمة للموضوع الأخير فقط، بدون رموز."}])
        if res:
            for t in res.split('\n'):
                if t.strip(): conn.execute("INSERT INTO book_progress VALUES (?, ?, ?)", (user_id, t.strip(), ""))
            conn.commit()

    # 2. التأليف
    chapters_data = conn.execute("SELECT title, content FROM book_progress WHERE user_id=?", (user_id,)).fetchall()
    for title, content in chapters_data:
        if not content:
            await status.edit_text(f"✍️ جاري تأليف: {title}")
            body = await safe_ai_request(history + [{"role": "system", "content": f"اكتب محتوى مفصل للفصل: {title} بدون رموز."}])
            if body:
                conn.execute("UPDATE book_progress SET content=? WHERE user_id=? AND title=?", (body, user_id, title))
                conn.commit()
                await asyncio.sleep(8)

    # 3. تحويل إلى PDF وإرسال
    final_chapters = conn.execute("SELECT title, content FROM book_progress WHERE user_id=?", (user_id,)).fetchall()
    pdf_name = f"Book_{user_id}.pdf"
    
    try:
        create_pdf(final_chapters, pdf_name)
        await context.bot.send_document(chat_id=user_id, document=open(pdf_name, "rb"), caption="✅ تم توليد ملف الـ PDF بنجاح!")
    except Exception as e:
        await update.message.reply_text(f"❌ حدث خطأ أثناء صنع الـ PDF: {e}")

    # تنظيف شامل
    conn.execute("DELETE FROM chat_history WHERE user_id=?", (user_id,))
    conn.execute("DELETE FROM book_progress WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()
    if os.path.exists(pdf_name): os.remove(pdf_name)

async def start_clean(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # أمر لمسح الذاكرة والبدء من جديد
    user_id = update.effective_user.id
    conn = sqlite3.connect('ebook_engine.db')
    conn.execute("DELETE FROM chat_history WHERE user_id=?", (user_id,))
    conn.execute("DELETE FROM book_progress WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()
    await update.message.reply_text("🧼 تم مسح الذاكرة القديمة. أعطني موضوع الكتاب الجديد الآن!")

# (إضافة handlers لـ start_clean و build والـ chat في الـ main)
