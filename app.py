import os
import asyncio
import sqlite3
import datetime
import re
import logging
from groq import Groq
from telegram import Update, LabeledPrice, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, PreCheckoutQueryHandler
from fpdf import FPDF
from arabic_reshaper import reshape
from bidi.algorithm import get_display

# --- الإعدادات ---
API_KEYS = ["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", "KEY_2"]
TELEGRAM_TOKEN = "8605364115:AAHUmg2qyAanzsjLBUEoc5dS9ECaipyRrZY"
ADMIN_ID = 8443969410
current_key_index = 0

# --- الألوان والزخرفة الذكية ---
def get_theme_color(topic):
    topic = topic.lower()
    if any(w in topic for w in ['psychology', 'peace', 'هدوء', 'نفس', 'spirit']): return (34, 139, 34)
    if any(w in topic for w in ['tech', 'future', 'تقنية', 'science']): return (0, 102, 204)
    if any(w in topic for w in ['history', 'war', 'تاريخ', 'ancient']): return (139, 69, 19)
    return (20, 40, 120)

# --- محرك الـ PDF المحسن ---
def create_styled_pdf(chapters, filename, topic, decoration):
    try:
        pdf = FPDF()
        pdf.set_auto_page_break(auto=True, margin=15)
        font_path = os.path.join(os.getcwd(), "arial.ttf")
        font_main = 'ArabicFont' if os.path.exists(font_path) else 'Arial'
        if font_main == 'ArabicFont': pdf.add_font('ArabicFont', '', font_path, uni=True)

        r, g, b = get_theme_color(topic)
        written_pages = 0

        for title, content in chapters:
            if not content or len(content.strip()) < 100: continue
            pdf.add_page()
            written_pages += 1
            is_ar = any(ord(c) > 128 for c in title)
            
            pdf.set_text_color(r, g, b)
            pdf.set_font(font_main, size=24)
            d_title = f"{decoration} {title} {decoration}" if decoration else title
            pdf.multi_cell(190, 15, txt=get_display(reshape(d_title)), align='C')
            
            pdf.ln(10)
            pdf.set_text_color(0, 0, 0)
            pdf.set_font(font_main, size=14)
            clean_txt = re.sub(r'[*_#`]', '', content)
            pdf.multi_cell(190, 10, txt=get_display(reshape(clean_txt)), align='R' if is_ar else 'L')

        if written_pages == 0: return False
        pdf.output(filename)
        return True
    except Exception as e:
        print(f"PDF Error: {e}")
        return False

# --- إدارة قاعدة البيانات ---
def init_db():
    conn = sqlite3.connect('architect_final.db')
    conn.execute('CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, expiry TEXT)')
    conn.execute('CREATE TABLE IF NOT EXISTS chat_history (user_id INTEGER, role TEXT, content TEXT)')
    conn.execute('CREATE TABLE IF NOT EXISTS book_progress (user_id INTEGER, title TEXT, content TEXT)')
    conn.commit()
    conn.close()

init_db()

def is_sub(uid):
    if uid == ADMIN_ID: return True
    conn = sqlite3.connect('architect_final.db')
    user = conn.execute("SELECT expiry FROM users WHERE user_id=?", (uid,)).fetchone()
    conn.close()
    if user: return datetime.datetime.strptime(user[0], '%Y-%m-%d') > datetime.datetime.now()
    return False

# --- محرك AI ---
async def ai_req(msgs):
    global current_key_index
    for _ in range(len(API_KEYS)):
        try:
            client = Groq(api_key=API_KEYS[current_key_index])
            res = client.chat.completions.create(model="openai/gpt-oss-120b", messages=msgs, temperature=0.7)
            return res.choices[0].message.content
        except:
            current_key_index = (current_key_index + 1) % len(API_KEYS)
            await asyncio.sleep(1)
    return None

# --- الأوامر ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if is_sub(uid):
        await update.message.reply_text("📖 **المحرك جاهز!**\nناقشني في موضوعك، أو أرسل /new للبدء من جديد، أو /build للتأليف.")
    else:
        kb = [[InlineKeyboardButton("💳 تفعيل (25 نجمة)", callback_data="pay")]]
        await update.message.reply_text("👑 **ARCHITECT AI PRO**\nأنت بحاجة لاشتراك لتأليف المجلدات.", reply_markup=InlineKeyboardMarkup(kb))

async def pay_invoice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    prices = [LabeledPrice("الاشتراك الشهري", 25)]
    await context.bot.send_invoice(
        update.effective_chat.id, "تفعيل Architect AI", "تأليف كتب غير محدود لمدة شهر",
        "sub_payload", "", "XTR", prices
    )

async def precheckout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.pre_checkout_query.answer(ok=True)

async def success_pay(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.message.from_user.id
    expiry = (datetime.datetime.now() + datetime.timedelta(days=30)).strftime('%Y-%m-%d')
    conn = sqlite3.connect('architect_final.db')
    conn.execute("INSERT OR REPLACE INTO users VALUES (?, ?)", (uid, expiry))
    conn.commit()
    conn.close()
    await update.message.reply_text("🎉 تم تفعيل القوة الكاملة للمحرك لمدة 30 يوماً!")

async def new_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    conn = sqlite3.connect('architect_final.db')
    conn.execute("DELETE FROM chat_history WHERE user_id=?", (uid,))
    conn.execute("DELETE FROM book_progress WHERE user_id=?", (uid,))
    conn.commit()
    conn.close()
    await update.message.reply_text("🧼 تم تصفير الذاكرة. ما هو موضوعك الجديد؟")

async def build(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_sub(uid): return
    
    conn = sqlite3.connect('architect_final.db')
    hist_rows = conn.execute("SELECT role, content FROM chat_history WHERE user_id=?", (uid,)).fetchall()
    if not hist_rows:
        await update.message.reply_text("⚠️ يرجى مناقشة موضوع أولاً.")
        return

    status = await update.message.reply_text("🏗️ جاري هندسة وتأليف المجلد... يرجى الانتظار.")
    hist = [{"role": r[0], "content": r[1]} for r in hist_rows]
    topic_txt = hist[-1]['content']
    
    # 1. الخطة
    plan = await ai_req(hist + [{"role": "system", "content": "أعطني عناوين لـ 24 فصلاً سطر بسطر فقط."}])
    if plan:
        for t in plan.split('\n'):
            if t.strip(): conn.execute("INSERT INTO book_progress VALUES (?, ?, '')", (uid, t.strip()))
        conn.commit()

    # 2. التأليف
    chaps = conn.execute("SELECT title, content FROM book_progress WHERE user_id=?", (uid,)).fetchall()
    for i, (t, c) in enumerate(chaps):
        if not c:
            body = await ai_req(hist + [{"role": "system", "content": f"اكتب فصلاً مفصلاً جداً لعنوان ({t})."}])
            if body:
                conn.execute("UPDATE book_progress SET content=? WHERE user_id=? AND title=?", (body, uid, t))
                conn.commit()
            if i % 4 == 0: await status.edit_text(f"✍️ تقدم العمل: {int((i/len(chaps))*100)}%")

    # 3. PDF والتوصيل
    final = conn.execute("SELECT title, content FROM book_progress WHERE user_id=?", (uid,)).fetchall()
    pdf_name = f"Masterpiece_{uid}.pdf"
    
    if create_styled_pdf(final, pdf_name, topic_txt, "—"):
        with open(pdf_name, "rb") as f:
            await context.bot.send_document(chat_id=uid, document=f, caption="✅ اكتمل كتابك المزخرف!")
    else:
        await update.message.reply_text("❌ حدث خطأ في إنشاء المحتوى.")
    
    if os.path.exists(pdf_name): os.remove(pdf_name)
    conn.close()

async def chat_logic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_sub(uid):
        await start(update, context)
        return
    
    txt = update.message.text
    conn = sqlite3.connect('architect_final.db')
    conn.execute("INSERT INTO chat_history VALUES (?, 'user', ?)", (uid, txt))
    conn.commit()
    
    history = [{"role": "system", "content": "أنت مهندس كتب محترف. ناقش الفكرة وقدم ملخصات واقتراحات."}]
    rows = conn.execute("SELECT role, content FROM chat_history WHERE user_id=? ORDER BY rowid DESC LIMIT 10", (uid,)).fetchall()
    for r in reversed(rows): history.append({"role": r[0], "content": r[1]})
    
    res = await ai_req(history)
    if res:
        conn.execute("INSERT INTO chat_history VALUES (?, 'assistant', ?)", (uid, res))
        conn.commit()
        await update.message.reply_text(res)
    conn.close()

# --- التشغيل ---
app = Application.builder().token(TELEGRAM_TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("new", new_cmd))
app.add_handler(CommandHandler("build", build))
app.add_handler(CallbackQueryHandler(pay_invoice, pattern="pay"))
app.add_handler(PreCheckoutQueryHandler(precheckout))
app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, success_pay))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat_logic))
app.run_polling()
