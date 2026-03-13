import logging
import os
import asyncio
import sqlite3
from groq import Groq
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# --- ضع المفتاحين هنا ---
API_KEYS = [
    "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", # المفتاح الأول
    "أدخل_المفتاح_الثاني_هنا"                                  # المفتاح الثاني
]

TELEGRAM_TOKEN = "8605364115:AAHUmg2qyAanzsjLBUEoc5dS9ECaipyRrZY"
ADMIN_ID = 8443969410

# مؤشر المفتاح الحالي
current_key_index = 0

def get_client():
    global current_key_index
    return Groq(api_key=API_KEYS[current_key_index])

def rotate_key():
    global current_key_index
    current_key_index = 1 if current_key_index == 0 else 0
    print(f"🔄 تم التبديل للمفتاح رقم {current_key_index + 1}")

# --- إعداد الذاكرة ---
def init_db():
    conn = sqlite3.connect('ebook_engine.db')
    conn.execute('''CREATE TABLE IF NOT EXISTS chat_history (user_id INTEGER, role TEXT, content TEXT)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS book_progress (user_id INTEGER, title TEXT, content TEXT)''')
    conn.commit()
    conn.close()

init_db()

# --- المحرك القوي ---
async def safe_ai_request(messages):
    max_attempts = 4 # يحاول مرتين لكل مفتاح
    for attempt in range(max_attempts):
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
                print(f"⚠️ المفتاح {current_key_index + 1} مجهد. تبديل...")
                rotate_key()
                await asyncio.sleep(5) # انتظار قصير جداً للتبديل
            else:
                print(f"❌ خطأ: {e}")
                await asyncio.sleep(10)
    return None

# --- الأوامر ---
async def build(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID: return

    conn = sqlite3.connect('ebook_engine.db')
    history = [{"role": r[0], "content": r[1]} for r in conn.execute("SELECT role, content FROM chat_history WHERE user_id=?", (user_id,)).fetchall()]
    
    if not history:
        await update.message.reply_text("❌ الذاكرة فارغة.")
        return

    status = await update.message.reply_text("⚙️ المحرك بدأ العمل بنظام المفتاحين...")

    # 1. الخطة
    check = conn.execute("SELECT title FROM book_progress WHERE user_id=?", (user_id,)).fetchall()
    if not check:
        plan_text = await safe_ai_request(history + [{"role": "system", "content": "أعطني 6 عناوين فصول دسمة، كل عنوان في سطر، بدون رموز."}])
        if plan_text:
            for t in plan_text.split('\n'):
                if t.strip(): conn.execute("INSERT INTO book_progress VALUES (?, ?, ?)", (user_id, t.strip(), ""))
            conn.commit()

    # 2. التأليف
    chapters = conn.execute("SELECT title, content FROM book_progress WHERE user_id=?", (user_id,)).fetchall()
    for title, content in chapters:
        if not content:
            await status.edit_text(f"✍️ تأليف: {title}\n🔑 مفتاح نشط: {current_key_index + 1}")
            body = await safe_ai_request(history + [{"role": "system", "content": f"اكتب فصلاً كاملاً لـ ({title}) بدون رموز."}])
            if body:
                conn.execute("UPDATE book_progress SET content=? WHERE user_id=? AND title=?", (body, user_id, title))
                conn.commit()
                await asyncio.sleep(5)

    # 3. الختام
    final = conn.execute("SELECT title, content FROM book_progress WHERE user_id=?", (user_id,)).fetchall()
    fname = f"Book_{user_id}.txt"
    with open(fname, "w", encoding="utf-8") as f:
        for t, c in final: f.write(f"\n[ {t} ]\n\n{c}\n\n")
        f.write("\n\nتم اكتمال الكتاب بنجاح من السيرفر حتى الحرف الأخير - تم مسح الذاكرة.")

    await context.bot.send_document(chat_id=user_id, document=open(fname, "rb"), caption="✅ كتابك جاهز!")
    
    conn.execute("DELETE FROM chat_history WHERE user_id=?", (user_id,))
    conn.execute("DELETE FROM book_progress WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()
    os.remove(fname)

async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    conn = sqlite3.connect('ebook_engine.db')
    conn.execute("INSERT INTO chat_history VALUES (?, ?, ?)", (user_id, "user", update.message.text))
    conn.commit()
    
    history = [{"role": r[0], "content": r[1]} for r in conn.execute("SELECT role, content FROM chat_history WHERE user_id=?", (user_id,)).fetchall()]
    res = await safe_ai_request(history)
    if res:
        conn.execute("INSERT INTO chat_history VALUES (?, ?, ?)", (user_id, "assistant", res))
        conn.commit()
        await update.message.reply_text(res)
    conn.close()

if __name__ == '__main__':
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("build", build))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat))
    print("🚀 المحرك المزدوج يعمل...")
    app.run_polling()
