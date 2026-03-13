import os
import asyncio
import sqlite3
import datetime
import re
import random
import logging
from telegram import Update, LabeledPrice, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, PreCheckoutQueryHandler, CallbackQueryHandler

# --- الإعدادات ---
CHANNEL_ID = "@forgeflow_project" # يوزر القناة
TELEGRAM_TOKEN = "8605364115:AAHUmg2qyAanzsjLBUEoc5dS9ECaipyRrZY"

# نصوص الإعلانات العشوائية
AD_MESSAGES = [
    "📚 هل حلمت يوماً بتأليف كتابك الخاص؟\nبوت ARCHITECT AI يحول أفكارك إلى مجلدات PDF احترافية بضغطة زر! 🚀",
    "🧠 ناقش أفكارك.. صمم هيكل كتابك.. واستلم نسخة PDF مزخرفة.\nابدأ رحلة التأليف الآن مع المهندس الذكي. ✍️",
    "💎 حصرياً: ألف كتباً تصل إلى 100 صفحة بدعم كامل للغة العربية.\nاشترك الآن بـ 25 نجمة فقط وابدأ مشروعك الأدبي! 📖",
    "🤖 لا تكتفِ بالدردشة، اصنع محتواك الخاص.\nمحرك ARCHITECT AI هو رفيقك من الفكرة حتى الطباعة. 📄"
]

# --- وظيفة النشر التلقائي ---
async def send_random_ad(context: ContextTypes.DEFAULT_TYPE):
    ad_text = random.choice(AD_MESSAGES)
    try:
        await context.bot.send_message(
            chat_id=CHANNEL_ID, 
            text=f"📢 **إعلان من ARCHITECT AI**\n\n{ad_text}\n\n🤖 ابدأ الآن: @{context.bot.username}"
        )
    except Exception as e:
        print(f"Error sending ad to channel: {e}")

# --- جدولة المهام ---
def setup_jobs(application: Application):
    job_queue = application.job_queue
    
    # حساب الثواني في اليوم (86400 ثانية) تقسيم 2 = وظيفة كل 12 ساعة تقريباً
    # سنقوم بجدولة الوظيفة لتعمل كل 12 ساعة مع "إزاحة عشوائية"
    job_queue.run_repeating(
        send_random_ad, 
        interval=43200, # 12 ساعة بالثواني
        first=10, # تبدأ بعد 10 ثواني من تشغيل البوت
        name="daily_ads"
    )

# --- (بقية دوال البوت السابقة: build, chat, start, etc.) ---

# (يجب دمج دالة التشغيل كما يلي)
if __name__ == '__main__':
    # تأكد من تثبيت 'python-telegram-bot[job-queue]'
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # إعداد الجدولة
    setup_jobs(app)
    
    # إعداد الـ Handlers (التي كتبناها في السكريبت السابق)
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("new", new_cmd))
    app.add_handler(CommandHandler("build", build))
    app.add_handler(CallbackQueryHandler(pay_invoice, pattern="pay"))
    app.add_handler(PreCheckoutQueryHandler(precheckout))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, success_pay))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat_logic))
    
    print("🚀 المحرك والناشر التلقائي يعملان الآن!")
    app.run_polling()
