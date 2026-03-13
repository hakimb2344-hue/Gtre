#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
from openai import OpenAI
import os

# ===== مفاتيحك =====
BOT_TOKEN = "8605364115:AAHUmg2qyAanzsjLBUEoc5dS9ECaipyRrZY"
GROQ_API_KEY = "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"

# ===== إعداد Groq =====
client = OpenAI(
    api_key=GROQ_API_KEY,
    base_url="https://api.groq.com/openai/v1"
)

# ===== تخزين مؤقت للمحادثات =====
user_sessions = {}

# ===== أمر /start =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_sessions[user_id] = []
    await update.message.reply_text(
        "🚀 مرحبًا بك في Creative Website Generator Bot!\n"
        "سأطرح عليك أسئلة لفهم موقعك المثالي.\n"
        "عندما تنتهي من الرد على كل الأسئلة، اكتب /build ليتم إنشاء الموقع."
    )

# ===== تخزين رسائل المستخدم =====
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()
    
    if user_id not in user_sessions:
        user_sessions[user_id] = []

    user_sessions[user_id].append(f"User: {text}")

    await update.message.reply_text(
        "📝 تم حفظ ملاحظتك! استمر في إعطاء التفاصيل، وعندما تنتهي اكتب /build."
    )

# ===== توليد الموقع عند /build =====
async def build(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in user_sessions or len(user_sessions[user_id]) == 0:
        await update.message.reply_text("⚠️ لم يتم تسجيل أي تفاصيل. ابدأ بإرسال أفكارك أولاً.")
        return

    await update.message.reply_text("⚡ جاري توليد موقعك الإبداعي، انتظر لحظة...")

    # إنشاء البرومبت النهائي بناءً على محادثة المستخدم
    conversation_text = "\n".join(user_sessions[user_id])
    prompt = f"""
You are an extremely creative professional web designer AI.
The user has provided the following details about the website they want:
{conversation_text}

Generate a FULL modern website in ONE HTML file.
Requirements:
- Futuristic, professional, elegant, and responsive
- Hero section, services, gallery, testimonials, pricing, contact form
- Smooth animations, hover effects, gradients
- Return ONLY the HTML code
    """

    try:
        response = client.responses.create(
            input=prompt,
            model="openai/gpt-oss-20b"
        )
        html_content = response.output_text

        file_path = f"creative_site_{user_id}.html"
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(html_content)

        await update.message.reply_document(document=open(file_path, "rb"), filename="CreativeSite.html")
        await update.message.reply_text("✅ تم إنشاء الموقع بنجاح! التخزين المؤقت تم مسحه للبدء من جديد.")

    except Exception as e:
        await update.message.reply_text(f"❌ حدث خطأ أثناء إنشاء الموقع: {str(e)}")

    # مسح التخزين المؤقت بعد الإنشاء
    user_sessions[user_id] = []

# ===== إعداد التطبيق =====
app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("build", build))
app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))

# ===== تشغيل البوت =====
print("🤖 بوت Creative Website Generator يعمل الآن...")
app.run_polling()
