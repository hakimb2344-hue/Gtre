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

# --- الإعدادات الأساسية ---
API_KEYS = ["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", "ضع_المفتاح_الثاني_هنا"]
TELEGRAM_TOKEN = "8605364115:AAHUmg2qyAanzsjLBUEoc5dS9ECaipyRrZY"
ADMIN_ID = 8443969410
current_key_index = 0

# --- الألوان الذكية ---
def get_theme_color(topic):
    topic = topic.lower()
    if any(w in topic for w in ['nature', 'psychology', 'peace', 'هدوء', 'نفس']): return (34, 139, 34)
    if any(w in topic for w in ['tech', 'future', 'تقنية', 'فضاء']): return (0, 102, 204)
    if any(w in topic for w in ['history', 'war', 'تاريخ', 'قديم']): return (139, 69, 19)
    return (20, 40, 120)

# --- محرك الـ PDF المزخرف ---
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
            
            # زخرفة العنوان
            pdf.set_text_color(r, g, b)
            pdf.set_font(font_main, size=22)
            d_title = f"{decoration} {title} {decoration}" if decoration else title
            pdf.multi_cell(190, 15, txt=get_display(reshape(d_title)), align='C')
            
            pdf.ln(10)
            pdf.set_text_color(0, 0, 0)
            pdf.set_font(font_main, size=13)
            clean_txt = re.sub(r'[*_#`]', '', content)
            pdf.multi_cell(190, 9, txt=get_display(reshape(clean_txt)), align='R' if is_ar else 'L')

        if written_pages == 0: return False
        pdf.output(filename)
        return True
    except Exception as e:
        print(f"PDF Error: {e}")
        return False

# --- قاعدة البيانات ---
def init_db():
    conn = sqlite3.connect('master.db')
    conn.execute('CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, expiry TEXT)')
    conn.execute('CREATE TABLE IF NOT EXISTS chat_history (user_id INTEGER, role TEXT, content TEXT)')
    conn.execute('CREATE TABLE IF NOT EXISTS book_progress (user_id INTEGER, title TEXT, content TEXT)')
    conn.commit()
    conn.close()

init_db()

def is_sub(uid):
    if uid == ADMIN_ID: return True
    conn = sqlite3.connect('master.db')
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
            await asyncio.sleep(2)
    return None

# --- الأوامر ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if is_sub(uid):
        await update.message.reply_text("✅ المحرك جاهز. ناقشني في موضوعك، أو أرسل /new للبدء من جديد، أو /build للتأليف.")
    else:
        kb = [[InlineKeyboardButton("💳 اشترك (25 نجمة)", callback_data="pay")]]
        await update.message.reply_text("👑 ARCHITECT AI PRO\nاشترك لتأليف مجلداتك الخاصة.", reply_markup=InlineKeyboardMarkup(kb))

async def new_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    conn = sqlite3.connect('master.db')
    conn.execute("DELETE FROM chat_history WHERE user_id=?", (uid,))
    conn.execute("DELETE FROM book_progress WHERE user_id=?", (uid,))
    conn.commit()
    conn.close()
    await update.message.reply_text("🧼 تم تصفير الذاكرة. ما هو موضوعك الجديد؟")

async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_sub(uid): return
    txt = update.message.text
    conn = sqlite3.connect('master.db')
    conn.execute("INSERT INTO chat_history VALUES (?, 'user', ?)", (uid, txt))
    conn.commit()
    
    hist = [{"role": "system", "content": "أنت مهندس كتب محترف. ناقش المستخدم بذكاء وقدم اقتراحات."}]
    rows = conn.execute("SELECT role, content FROM chat_history WHERE user_id=? ORDER BY rowid DESC LIMIT 8", (uid,)).fetchall()
    for r in reversed(rows): hist.append({"role": r[0], "content": r[1]})
    
    res = await ai_req(hist)
    if res:
        conn.execute("INSERT INTO chat_history VALUES (?, 'assistant', ?)", (uid, res))
        conn.commit()
        await update.message.reply_text(res)
    conn.close()

async def build(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_sub(uid): return
    
    conn = sqlite3.connect('master.db')
    hist = [{"role": r[0], "content": r[1]} for r in conn.execute("SELECT role, content FROM chat_history WHERE user_id=?", (uid,)).fetchall()]
    
    if not hist:
        await update.message.reply_text("⚠️ ناقشني في فكرة أولاً!")
        return

    status = await update.message.reply_text("🏗️ جاري هندسة الفصول والتأليف... (قد يستغرق دقائق)")
    
    # تحديد الزخرفة والموضوع
    topic_txt = hist[-1]['content']
    decor = re.search(r'(زخرفة|decoration)\s*[:=]\s*(\S+)', topic_txt)
    decor_val = decor.group(2) if decor else None

    # 1. الخطة
    plan = await ai_req(hist + [{"role": "system", "content": "أعطني عناوين لـ 24 فصلاً دسيماً لهذا الكتاب. العناوين فقط سطر بسطر."}])
    if plan:
        for t in plan.split('\n'):
            if t.strip(): conn.execute("INSERT INTO book_progress VALUES (?, ?, '')", (uid, t.strip()))
        conn.commit()

    # 2. التأليف
    chaps = conn.execute("SELECT title, content FROM book_progress WHERE user_id=?", (uid,)).fetchall()
    for i, (t, c) in enumerate(chaps):
        if not c:
            await status.edit_text(f"✍️ تأليف الفصل {i+1}/{len(chaps)}...")
            body = await ai_req(hist + [{"role": "system", "content": f"اكتب فصلاً دسيماً ومطولاً جداً لعنوان ({t})."}])
            if body:
                conn.execute("UPDATE book_progress SET content=? WHERE user_id=? AND title=?", (body, uid, t))
                conn.commit()
                await asyncio.sleep(2)

    # 3. PDF
    final = conn.execute("SELECT title, content FROM book_progress WHERE user_id=?", (uid,)).fetchall()
    pdf_name = f"Book_{uid}.pdf"
    if create_styled_pdf(final, pdf_name, topic_txt, decor_val):
        await context.bot.send_document(chat_id=uid, document=open(pdf_name, "rb"), caption="✅ تم!")
    
    if os.path.exists(pdf_name): os.remove(pdf_name)
    conn.close()

# --- التشغيل ---
app = Application.builder().token(TELEGRAM_TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("new", new_cmd))
app.add_handler(CommandHandler("build", build))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat))
print("🚀 الماكينة تعمل!")
app.run_polling()
