#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
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

# ==== دالة لإنشاء كود HTML ====
def generate_html(prompt: str) -> str:
    html_code = f"""<!DOCTYPE html>
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
<h1>✨ ForgeFlow AI Generated Code</h1>
<pre>{prompt}</pre>
</div>
</body>
</html>"""
    return html_code

# ==== دوال البوت ====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await update.message.reply_text(f"مرحبا بك في ForgeFlow Bot!\n🟊 للاستخدام تحتاج إلى 25 نجمة، إلا إذا كنت المستخدم الخاص (ID={FREE_USER_ID}).")
    if user_id == FREE_USER_ID:
        await update.message.reply_text("✅ أنت مستخدم مجاني خاص، يمكنك تجربة البوت مباشرة.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()
    
    # التحقق من الدفع أو المستخدم الخاص
    if user_id != FREE_USER_ID:
        await update.message.reply_text("❌ يجب دفع 25 نجمة لتتمكن من استخدام البوت (خطة مستقبلية).")
        return

    # استدعاء Groq API
    try:
        response = client.responses.create(
            input=text,
            model="openai/gpt-oss-20b"
        )
        result_text = response.output_text
    except Exception as e:
        result_text = f"حدث خطأ أثناء توليد الكود: {str(e)}"

    # إنشاء ملف HTML
    html_content = generate_html(result_text)
    file_path = f"forgeflow_{user_id}.html"
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    # إرسال ملف HTML للمستخدم
    await update.message.reply_document(document=open(file_path, "rb"), filename="ForgeFlow_Result.html")
    await update.message.reply_text("✅ تم توليد الملف وإرساله! استمتع بكودك الذهبي ✨")

# ==== تهيئة التطبيق ====
app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))

# ==== تشغيل البوت ====
print("🤖 بوت ForgeFlow يعمل الآن...")
app.run_polling()
