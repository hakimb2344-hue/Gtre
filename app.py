#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import time
import subprocess

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

# ==== جلسة مؤقتة لكل مستخدم ====
sessions = {}

# ==== دالة إنشاء موقع HTML نظيف حسب البرومبت ====
def generate_clean_html(prompt: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="ar">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ForgeFlow User Site</title>
<style>
body {{ margin:0; font-family:sans-serif; }}
.container {{ max-width:1200px; margin:auto; padding:20px; }}
</style>
</head>
<body>
<div class="container">
{prompt}
</div>
</body>
</html>"""

# ==== دوال البوت ====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    sessions[user_id] = ""
    await update.message.reply_text(
        f"👋 مرحبا بك في ForgeFlow-Bot!\nأرسل لي تفاصيل الموقع الذي تريد أن أنشئه لك.\n"
        f"اكتب /build عندما تريد أن أبدأ الإنشاء النهائي."
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()
    
    if user_id != FREE_USER_ID:
        await update.message.reply_text("❌ حاليا يحتاج البوت خطة نجوم لتشغيله. انت المستخدم الخاص.")
        return
    
    if user_id not in sessions:
        sessions[user_id] = ""
    
    # إضافة الرسالة إلى الجلسة المؤقتة
    sessions[user_id] += text + "\n"
    await update.message.reply_text("✅ تم حفظ ما كتبته، أرسل /build للبدء بإنشاء الموقع.")

async def build_site(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if user_id not in sessions or not sessions[user_id].strip():
        await update.message.reply_text("⚠️ لا يوجد أي محتوى لبناء الموقع، أرسل لي التفاصيل أولاً.")
        return
    
    prompt_text = sessions[user_id]
    await update.message.reply_text("⏳ جاري إنشاء الموقع بناءً على طلبك...")

    # استدعاء Groq API خطوة بخطوة
    try:
        final_html = ""
        for chunk in [prompt_text[i:i+1000] for i in range(0, len(prompt_text), 1000)]:
            response = client.responses.create(
                input=f"أنشئ لي موقع HTML صافي بناءً على التالي:\n{chunk}",
                model="openai/gpt-oss-20b"
            )
            partial = response.output_text
            final_html += partial
            time.sleep(5)  # الانتظار قبل استكمال التالي
    except Exception as e:
        await update.message.reply_text(f"❌ حدث خطأ أثناء إنشاء الموقع: {str(e)}")
        return

    # إنشاء ملف HTML النهائي
    html_content = generate_clean_html(final_html)
    file_path = f"forgeflow_site_{user_id}.html"
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    # إرسال الملف للمستخدم
    await update.message.reply_document(document=open(file_path, "rb"), filename="ForgeFlow_UserSite.html")
    await update.message.reply_text("✅ تم إنشاء الموقع بنجاح! يمكنك فتح الملف وتجربته.")
    
    # مسح الجلسة المؤقتة
    sessions[user_id] = ""

# ==== تهيئة التطبيق ====
app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("build", build_site))
app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))

# ==== تشغيل البوت ====
print("🤖 ForgeFlow-Bot يعمل الآن...")
app.run_polling()
