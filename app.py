#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import subprocess
import time

# ==== تثبيت تلقائي للمكتبات المطلوبة ====
required_packages = ["python-telegram-bot==20.3", "openai"]
for pkg in required_packages:
    try:
        __import__(pkg.split("==")[0])
    except ImportError:
        subprocess.check_call([sys.executable, "-m", "pip", "install", pkg])

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
from openai import OpenAI

# ==== مفاتيح API ====
GROQ_API_KEY = "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"
BOT_TOKEN = "8605364115:AAHUmg2qyAanzsjLBUEoc5dS9ECaipyRrZY"

# ==== مستخدم خاص لا يحتاج دفع نجوم ====
FREE_USER_ID = 8443969410

# ==== تهيئة عميل Groq ====
client = OpenAI(
    api_key=GROQ_API_KEY,
    base_url="https://api.groq.com/openai/v1",
)

# ==== جلسات مؤقتة لكل مستخدم ====
user_sessions = {}

# ==== دالة لإنشاء كود HTML ====
def generate_html(prompt: str) -> str:
    html_code = f'''<!DOCTYPE html>
<html lang="ar">
<head>
<meta charset="UTF-8">
<title>ForgeFlow Result</title>
<style>
body {{ background: #fdf5e6; font-family: 'Cairo', sans-serif; color: #3d2f1f; }}
.container {{ max-width: 800px; margin: 50px auto; padding: 20px; background: #fffaf2; border-radius: 20px; box-shadow: 0 5px 15px rgba(0,0,0,0.1); }}
h1 {{ color: #b58a4b; }}
pre {{ background: #f0e6d2; padding: 15px; border-radius: 10px; overflow-x: auto; }}
</style>
</head>
<body>
<div class="container">
<h1>✨ ForgeFlow-Bot Generated Code</h1>
<pre>{prompt}</pre>
</div>
</body>
</html>'''
    return html_code

# ==== أمر /start ====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_sessions[user_id] = []
    await update.message.reply_text(
        "🌟 أهلاً بك في **ForgeFlow-Bot**!\n"
        "سأساعدك على إنشاء مواقع ويب إبداعية وحديثة.\n\n"
        "📝 خطوات الاستخدام:\n"
        "1️⃣ أرسل تفاصيل موقعك (الأفكار، الأقسام، التصميم المفضل، أي ملاحظات).\n"
        "2️⃣ عند الانتهاء، اكتب الأمر /build ليتم إنشاء الموقع.\n\n"
        "⚡ ملاحظة: سيتم تخزين التفاصيل مؤقتًا أثناء الحديث، وبعد إنشاء الموقع يمسح كل شيء لتبدأ من جديد."
    )

# ==== استقبال الرسائل وجمع التفاصيل ====
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()
    
    if user_id != FREE_USER_ID:
        await update.message.reply_text("❌ يجب دفع 25 نجمة لتتمكن من استخدام البوت (خطة مستقبلية).")
        return

    if user_id not in user_sessions:
        user_sessions[user_id] = []

    user_sessions[user_id].append(text)
    await update.message.reply_text("✅ تم حفظ هذه المعلومة مؤقتًا. أرسل /build عندما تريد إنشاء الموقع.")

# ==== أمر /build لإنشاء الموقع ====
async def build(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id != FREE_USER_ID:
        await update.message.reply_text("❌ يجب دفع 25 نجمة لتتمكن من استخدام البوت (خطة مستقبلية).")
        return

    if user_id not in user_sessions or len(user_sessions[user_id]) == 0:
        await update.message.reply_text("⚠️ لا يوجد أي بيانات لإنشاء الموقع. أرسل التفاصيل أولاً.")
        return

    prompt_text = " ".join(user_sessions[user_id])

    await update.message.reply_text("⏳ جاري توليد موقعك… قد يستغرق بضع ثوانٍ…")

    try:
        # تقسيم الإرسال للتعامل مع حدود الحروف
        result_text = ""
        chunk_size = 2000
        for i in range(0, len(prompt_text), chunk_size):
            chunk = prompt_text[i:i+chunk_size]
            response = client.responses.create(
                input=chunk,
                model="openai/gpt-oss-20b"
            )
            result_text += response.output_text
            time.sleep(5)  # انتظار 5 ثواني قبل إرسال الجزء التالي

    except Exception as e:
        await update.message.reply_text(f"❌ حدث خطأ أثناء توليد الموقع: {str(e)}")
        return

    # إنشاء ملف HTML باسم ثابت مع ''' من أول الكود لآخره
    html_content = generate_html(result_text)
    file_path = "forgeflow_result.html"
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    # إرسال الملف للمستخدم
    await update.message.reply_document(document=open(file_path, "rb"), filename="ForgeFlow_Result.html")
    await update.message.reply_text("✅ تم توليد الملف وإرساله! تم مسح الجلسة لتبدأ من جديد.")

    # مسح الجلسة بعد الإرسال
    user_sessions[user_id] = []

# ==== تهيئة التطبيق ====
app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("build", build))
app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))

# ==== تشغيل البوت ====
print("🤖 بوت ForgeFlow-Bot يعمل الآن...")
app.run_polling()
