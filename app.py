import logging
import os
import asyncio
import sqlite3
from groq import Groq
from telegram import Update, LabeledPrice
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, PreCheckoutQueryHandler
from fpdf import FPDF
import arabic_reshaper
from bidi.algorithm import get_display

# --- الإعدادات والتوكنات ---
GROQ_API_KEY = "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"
TELEGRAM_TOKEN = "8605364115:AAHUmg2qyAanzsjLBUEoc5dS9ECaipyRrZY"
ADMIN_ID = 8443969410

client = Groq(api_key=GROQ_API_KEY)

# --- نظام قاعدة البيانات (لضمان عدم ضياع العمل) ---
def init_db():
    conn = sqlite3.connect('ebook_engine.db')
    c = conn.cursor()
    # تخزين سجل النقاش
    c.execute('''CREATE TABLE IF NOT EXISTS chat_history (user_id INTEGER, role TEXT, content TEXT)''')
    # تخزين الفصول ونسبة الإنجاز
    c.execute('''CREATE TABLE IF NOT EXISTS book_progress (user_id INTEGER, title TEXT, content TEXT)''')
    # تخزين مستخدمي الـ VIP
    c.execute('''CREATE TABLE IF NOT EXISTS vips (user_id INTEGER PRIMARY KEY)''')
    conn.commit()
    conn.close()

init_db()

# --- محرك صناعة الـ PDF الاحترافي ---
def create_ebook_pdf(chapters, filename):
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    
    # تحميل الخط العربي (يجب توفر ملف arial.ttf في المجلد)
    try:
        pdf.add_font('ArabicFont', '', 'arial.ttf', uni=True)
        pdf.set_font('ArabicFont', size=14)
    except:
        pdf.set_font("Arial", size=12)

    reshaper = arabic_reshaper.ArabicReshaper({'delete_harakat': False, 'support_ligatures': True})

    for title, content in chapters:
        pdf.add_page()
        
        # تنسيق العنوان (بدون رموز، بخط كبير ولون ملكي)
        pdf.set_font('ArabicFont', size=22)
        pdf.set_text_color(44, 62, 80)
        clean_title = title.replace('#', '').replace('*', '').strip()
        pdf.multi_cell(190, 15, txt=get_display(reshaper.reshape(clean_title)), align='C')
        
        pdf.ln(10) # مسافة بعد العنوان
        
        # تنسيق المحتوى (تنظيف الرموز ومحاذاة اليمين)
        pdf.set_font('ArabicFont', size=15)
        pdf.set_text_color(0, 0, 0)
        clean_content = content.replace('#', '').replace('*', '').strip()
        pdf.multi_cell(190, 10, txt=get_display(reshaper.reshape(clean_content)), align='R')

    # --- إضافة خاتمة في نهاية آخر صفحة كما طلبت ---
    pdf.ln(20)
    pdf.set_draw_color(200, 200, 200)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(5)
    pdf.set_font('ArabicFont', size=11)
    pdf.set_text_color(120, 120, 120)
    conclusion = "تم اكتمال الكتاب بنجاح من السيرفر حتى الحرف الأخير - تم مسح الذاكرة المؤقتة."
    pdf.multi_cell(190, 10, txt=get_display(reshaper.reshape(conclusion)), align='C')

    pdf.output(filename)

# --- وظائف البوت الأساسية ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await update.message.reply_text(
        "📚 **أهلاً بك في نظام صناعة الكتب الضخمة!**\n\n"
        "ناقشني في محتوى كتابك، وعند الجاهزية أرسل أمر /build.\n"
        "النظام يحفظ تقدمك تلقائياً؛ إذا توقف المحرك سيكمل من حيث توقف."
    )

async def handle_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text

    conn = sqlite3.connect('ebook_engine.db')
    conn.execute("INSERT INTO chat_history VALUES (?, ?, ?)", (user_id, "user", text))
    conn.commit()

    # جلب التاريخ الكامل للذكاء الاصطناعي
    cursor = conn.execute("SELECT role, content FROM chat_history WHERE user_id=?", (user_id,))
    history = [{"role": r[0], "content": r[1]} for r in cursor.fetchall()]
    
    try:
        completion = client.chat.completions.create(
            model="openai/gpt-oss-120b", 
            messages=history,
            temperature=1
        )
        ai_msg = completion.choices[0].message.content
        conn.execute("INSERT INTO chat_history VALUES (?, ?, ?)", (user_id, "assistant", ai_msg))
        conn.commit()
        await update.message.reply_text(ai_msg)
    except Exception as e:
        await update.message.reply_text("⚠️ المحرك مشغول قليلاً، لكنني حفظت كلامك. حاول مرة أخرى لاحقاً.")
    finally:
        conn.close()

async def build_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # فحص إذا كان الأدمن أو VIP
    conn = sqlite3.connect('ebook_engine.db')
    is_vip = conn.execute("SELECT 1 FROM vips WHERE user_id=?", (user_id,)).fetchone()
    conn.close()

    if user_id == ADMIN_ID or is_vip:
        await start_writing_process(update, context)
    else:
        # طلب الدفع بالنجوم
        await context.bot.send_invoice(
            chat_id=user_id,
            title="إنشاء الكتاب الورقي",
            description="تحويل النقاش إلى ملف PDF احترافي ضخم.",
            payload="ebook_pay",
            currency="XTR",
            prices=[LabeledPrice("الخدمة", 25)],
            provider_token=""
        )

async def pre_checkout_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.pre_checkout_query.answer(ok=True)

async def start_writing_process(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id if update.message else update.callback_query.from_user.id
    conn = sqlite3.connect('ebook_engine.db')
    
    history = [{"role": r[0], "content": r[1]} for r in conn.execute("SELECT role, content FROM chat_history WHERE user_id=?", (user_id,)).fetchall()]
    if not history:
        await context.bot.send_message(user_id, "❌ لا يوجد نقاش سابق. ابدأ بالتحدث معي أولاً!")
        return

    status = await context.bot.send_message(user_id, "🔍 فحص التقدم... سيتم التكملة من حيث توقفنا.")

    # 1. نظام التكملة: تحديد الفصول إذا لم تكن موجودة
    check = conn.execute("SELECT title, content FROM book_progress WHERE user_id=?", (user_id,)).fetchall()
    if not check:
        await status.edit_text("📋 جاري وضع خطة الفصول النهائية...")
        plan_prompt = history + [{"role": "system", "content": "أعطني قائمة بـ 6 عناوين فصول للكتاب، كل عنوان في سطر، بدون رموز."}]
        res = client.chat.completions.create(model="openai/gpt-oss-120b", messages=plan_prompt)
        titles = [t.strip() for t in res.choices[0].message.content.split('\n') if t.strip()]
        for t in titles:
            conn.execute("INSERT INTO book_progress VALUES (?, ?, ?)", (user_id, t, ""))
        conn.commit()
        check = conn.execute("SELECT title, content FROM book_progress WHERE user_id=?", (user_id,)).fetchall()

    # 2. تأليف الفصول (نظام الراحة وتجنب الحظر)
    for title, content in check:
        if not content: # فصل لم يكتمل
            await status.edit_text(f"✍️ جاري تأليف: {title}...")
            await asyncio.sleep(4) # راحة للمحرك
            
            write_prompt = history + [{"role": "system", "content": f"اكتب محتوى الفصل التالي بالتفصيل: {title}. تجنب رموز # و * نهائياً."}]
            try:
                c_res = client.chat.completions.create(model="openai/gpt-oss-120b", messages=write_prompt)
                c_body = c_res.choices[0].message.content
                conn.execute("UPDATE book_progress SET content=? WHERE user_id=? AND title=?", (c_body, user_id, title))
                conn.commit()
            except:
                await context.bot.send_message(user_id, "⚠️ توقف المحرك بسبب الضغط. أرسل /build مجدداً وسأكمل فوراً!")
                conn.close()
                return

    # 3. التجميع والمسح النهائي
    await status.edit_text("📚 تجميع الفصول وإضافة خاتمة السيرفر...")
    final_chapters = conn.execute("SELECT title, content FROM book_progress WHERE user_id=?", (user_id,)).fetchall()
    
    pdf_path = f"Ebook_{user_id}.pdf"
    create_ebook_pdf(final_chapters, pdf_path)

    with open(pdf_path, 'rb') as f:
        await context.bot.send_document(chat_id=user_id, document=f, caption="✅ تم الإرسال بنجاح. ذاكرة السيرفر نظيفة الآن.")

    # مسح شامل بعد النجاح
    conn.execute("DELETE FROM chat_history WHERE user_id=?", (user_id,))
    conn.execute("DELETE FROM book_progress WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()
    os.remove(pdf_path)

# --- أوامر الإدارة ---

async def add_vip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    try:
        v_id = int(context.args[0])
        conn = sqlite3.connect('ebook_engine.db')
        conn.execute("INSERT OR REPLACE INTO vips VALUES (?)", (v_id,))
        conn.commit()
        conn.close()
        await update.message.reply_text(f"✅ المستخدم {v_id} صار VIP الآن.")
    except:
        await update.message.reply_text("⚠️ `/add_vip ID`")

# --- التشغيل الرئيسي ---

if __name__ == '__main__':
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("build", build_request))
    app.add_handler(CommandHandler("add_vip", add_vip))
    app.add_handler(PreCheckoutQueryHandler(pre_checkout_callback))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, start_writing_process))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_chat))
    
    print("المحرك يعمل بأقصى طاقة...")
    app.run_polling()
