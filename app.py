import logging
import os
import asyncio
import sqlite3
from groq import Groq
from telegram import Update, LabeledPrice
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, PreCheckoutQueryHandler

# --- الإعدادات الأساسية ---
GROQ_API_KEY = "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"
TELEGRAM_TOKEN = "8605364115:AAHUmg2qyAanzsjLBUEoc5dS9ECaipyRrZY"
ADMIN_ID = 8443969410

client = Groq(api_key=GROQ_API_KEY)

# إعداد السجلات (Logs) لمراقبة الأداء
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# --- نظام قاعدة البيانات (الذاكرة الدائمة) ---
def init_db():
    conn = sqlite3.connect('ebook_master.db')
    c = conn.cursor()
    # سجل النقاش
    c.execute('''CREATE TABLE IF NOT EXISTS chat_history (user_id INTEGER, role TEXT, content TEXT)''')
    # سجل الفصول (للتكملة من حيث التوقف)
    c.execute('''CREATE TABLE IF NOT EXISTS book_progress (user_id INTEGER, title TEXT, content TEXT)''')
    conn.commit()
    conn.close()

init_db()

# --- محرك الذكاء الاصطناعي مع نظام الحماية من الانهيار (Retry Logic) ---
async def safe_ai_request(messages, retries=5):
    """دالة لطلب البيانات مع معالجة خطأ 429 والتوقف المفاجئ"""
    for i in range(retries):
        try:
            completion = client.chat.completions.create(
                model="openai/gpt-oss-120b",
                messages=messages,
                temperature=0.8,
                max_completion_tokens=4000
            )
            return completion.choices[0].message.content
        except Exception as e:
            error_str = str(e)
            if "429" in error_str:
                print(f"⚠️ المحرك ساخن جداً (Rate Limit). انتظار 30 ثانية... محاولة {i+1}")
                await asyncio.sleep(30)
            else:
                print(f"❌ خطأ غير متوقع: {error_str}. محاولة {i+1}")
                await asyncio.sleep(5)
    return None

# --- أوامر البوت ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📚 **مرحباً بك في المحرك السيادي لصناعة الكتب.**\n\n"
        "1. ناقشني في موضوع كتابك بالتفصيل.\n"
        "2. عند الجاهزية، أرسل /build.\n"
        "3. سيقوم البوت بتأليف الكتاب فصلاً فصلاً وحفظ التقدم تلقائياً."
    )

async def handle_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text

    conn = sqlite3.connect('ebook_master.db')
    conn.execute("INSERT INTO chat_history VALUES (?, ?, ?)", (user_id, "user", text))
    conn.commit()

    # جلب السجل الكامل للرد بذكاء
    cursor = conn.execute("SELECT role, content FROM chat_history WHERE user_id=?", (user_id,))
    history = [{"role": r[0], "content": r[1]} for r in cursor.fetchall()]
    
    response = await safe_ai_request(history)
    if response:
        conn.execute("INSERT INTO chat_history VALUES (?, ?, ?)", (user_id, "assistant", response))
        conn.commit()
        await update.message.reply_text(response)
    else:
        await update.message.reply_text("⚠️ المحرك مشغول حالياً، ولكنني حفظت بياناتك. حاول مراسلتي بعد قليل.")
    conn.close()

async def build_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # التحقق من الصلاحيات (أدمن فقط أو دفع نجوم)
    if user_id != ADMIN_ID:
        await update.message.reply_text("🚧 هذه الميزة تتطلب صلاحيات خاصة أو دفع رسوم الإنشاء.")
        return

    await process_book_construction(update, context)

async def process_book_construction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    conn = sqlite3.connect('ebook_master.db')
    
    # جلب النقاش لبناء المحتوى بناءً عليه
    history_rows = conn.execute("SELECT role, content FROM chat_history WHERE user_id=?", (user_id,)).fetchall()
    if not history_rows:
        await update.message.reply_text("❌ الذاكرة فارغة. ناقشني أولاً في موضوع الكتاب.")
        return
    
    history = [{"role": r[0], "content": r[1]} for r in history_rows]
    status_msg = await update.message.reply_text("🔄 جاري فحص نظام التكملة وبدء البناء...")

    # 1. المرحلة الأولى: وضع الخطة (إذا لم تكن موجودة)
    check_plan = conn.execute("SELECT title FROM book_progress WHERE user_id=?", (user_id,)).fetchall()
    if not check_plan:
        await status_msg.edit_text("📋 جاري وضع خطة الفصول (تجنب الرموز)...")
        plan_prompt = history + [{"role": "system", "content": "أعطني قائمة بـ 6 عناوين فصول دسمة، كل عنوان في سطر مستقل، بدون أرقام أو رموز (#, *)."}]
        plan_text = await safe_ai_request(plan_prompt)
        
        if not plan_text:
            await status_msg.edit_text("❌ فشل المحرك في الاستجابة. حاول /build مرة أخرى.")
            return

        titles = [t.strip() for t in plan_text.split('\n') if t.strip()]
        for t in titles:
            conn.execute("INSERT INTO book_progress VALUES (?, ?, ?)", (user_id, t, ""))
        conn.commit()
        log_info = "تم إنشاء خطة فصول جديدة."
    else:
        log_info = "تم العثور على خطة فصول سابقة، جاري التكملة..."

    # 2. المرحلة الثانية: تأليف المحتوى (نظام الفصل تلو الآخر)
    chapters = conn.execute("SELECT title, content FROM book_progress WHERE user_id=?", (user_id,)).fetchall()
    
    for title, content in chapters:
        if not content or content == "":
            await status_msg.edit_text(f"✍️ جاري تأليف: {title}\n(يرجى الانتظار، النظام يعمل بنظام التبريد)")
            
            write_prompt = history + [{"role": "system", "content": f"اكتب فصلاً كاملاً وعميقاً بعنوان ({title}). يمنع استخدام النجوم أو الهاشتاقات. استخدم فقرات واضحة."}]
            chapter_body = await safe_ai_request(write_prompt)
            
            if chapter_body:
                conn.execute("UPDATE book_progress SET content=? WHERE user_id=? AND title=?", (chapter_body, user_id, title))
                conn.commit()
                # تبريد وقائي لتجنب خطأ 429
                await asyncio.sleep(12) 
            else:
                await update.message.reply_text("⚠️ انقطع الاتصال أثناء تأليف الكتاب. أرسل /build للتكملة من نفس النقطة.")
                conn.close()
                return

    # 3. المرحلة الثالثة: التجميع النهائي والتحميل
    await status_msg.edit_text("📚 تجميع الفصول وإضافة خاتمة السيرفر...")
    final_data = conn.execute("SELECT title, content FROM book_progress WHERE user_id=?", (user_id,)).fetchall()
    
    filename = f"Ebook_{user_id}.txt"
    with open(filename, "w", encoding="utf-8") as f:
        f.write(f"مخطوطة كتاب رقمي\n{'='*20}\n")
        for t, c in final_data:
            f.write(f"\n[ {t} ]\n\n{c}\n\n")
        f.write(f"\n{'='*20}\nتم اكتمال الكتاب بنجاح من السيرفر حتى الحرف الأخير - تم مسح الذاكرة المؤقتة.")

    with open(filename, "rb") as f:
        await context.bot.send_document(chat_id=user_id, document=f, caption="✅ تم إنتاج الكتاب بنجاح!")

    # مسح الذاكرة بعد النجاح التام فقط
    conn.execute("DELETE FROM chat_history WHERE user_id=?", (user_id,))
    conn.execute("DELETE FROM book_progress WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()
    os.remove(filename)

# --- التشغيل ---
if __name__ == '__main__':
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("build", build_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_chat))
    
    print("🚀 البوت يعمل الآن بنظام التكملة التلقائية ومكافحة الأخطاء...")
    app.run_polling()
