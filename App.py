
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import subprocess
import logging
from pathlib import Path
from telegram import Update, InputFile
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext
from openai import OpenAI

# ========================
# ===== إعداد المكتبات ====
# ========================
required_libs = ["python-telegram-bot==20.3", "openai", "requests"]
for lib in required_libs:
    subprocess.run([os.sys.executable, "-m", "pip", "install", lib])

# ========================
# ===== المتغيرات =========
# ========================
BOT_TOKEN = "8605364115:AAHUmg2qyAanzsjLBUEoc5dS9ECaipyRrZY"
GROQ_API_KEY = "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"

# المجلدات
BASE_DIR = Path("ForgeFlow_Projects")
HTML_DIR = BASE_DIR / "html_files"
USER_DB = BASE_DIR / "users.txt"

BASE_DIR.mkdir(exist_ok=True)
HTML_DIR.mkdir(exist_ok=True)
USER_DB.touch(exist_ok=True)

# إعداد تسجيل الأخطاء
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# ========================
# ===== دالة OpenAI =======
# ========================
client = OpenAI(
    api_key=GROQ_API_KEY,
    base_url="https://api.groq.com/openai/v1",
)

def generate_html_code(prompt: str) -> str:
    """
    توليد كود HTML كامل وفق برومبت المستخدم
    """
    try:
        response = client.responses.create(
            input=(
                f"Create a full, responsive HTML page in golden & brown colors, "
                f"with futuristic style, Arabic/English mix, and include the prompt content: {prompt}"
            ),
            model="openai/gpt-oss-20b",
        )
        html_content = response.output_text
        return html_content
    except Exception as e:
        logging.error(f"Error generating HTML: {e}")
        return f"<!-- ERROR: {e} -->"

# ========================
# ===== إدارة النجوم ======
# ========================
def get_user_stars(user_id: int) -> int:
    """
    جلب عدد النجوم للمستخدم من قاعدة البيانات
    """
    if not USER_DB.exists():
        return 0
    with open(USER_DB, "r") as f:
        lines = f.readlines()
    for line in lines:
        uid, stars = line.strip().split(":")
        if int(uid) == user_id:
            return int(stars)
    return 0

def update_user_stars(user_id: int, stars: int):
    """
    تحديث عدد النجوم للمستخدم
    """
    lines = []
    found = False
    with open(USER_DB, "r") as f:
        lines = f.readlines()
    with open(USER_DB, "w") as f:
        for line in lines:
            uid, old_stars = line.strip().split(":")
            if int(uid) == user_id:
                f.write(f"{user_id}:{stars}\n")
                found = True
            else:
                f.write(line)
        if not found:
            f.write(f"{user_id}:{stars}\n")

# ========================
# ===== دوال البوت ========
# ========================
def start(update: Update, context: CallbackContext):
    update.message.reply_text(
        "مرحبا بك في ForgeFlow Bot!\n"
        "✨ أرسل لي برومبت HTML لتوليد صفحة ذهبية.\n"
        "💰 كل مستخدم يحتاج 25 نجمة لاستعمال البوت.\n"
        "أنت صاحب البوت، لذلك لديك صلاحية كاملة."
    )

def handle_prompt(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    stars = get_user_stars(user_id)

    # أنت صاحب البوت: صلاحية كاملة
    if user_id == 8605369415:  # <-- رقمك
        stars = 9999

    # تحقق من النجوم
    if stars < 25 and user_id != 8605369415:
        update.message.reply_text(f"❌ لديك {stars} نجوم فقط. تحتاج 25 نجمة للوصول.")
        return

    prompt_text = update.message.text.strip()
    update.message.reply_text("⏳ جاري توليد الصفحة الذهبية ...")

    html_code = generate_html_code(prompt_text)

    # حفظ HTML
    file_path = HTML_DIR / f"{user_id}_forgeflow.html"
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(html_code)

    # إرسال الملف للمستخدم
    with open(file_path, "rb") as f:
        update.message.reply_document(document=InputFile(f, filename="ForgeFlow.html"))

    # خصم النجوم لمستخدمي البوت الآخرين
    if user_id != 8605369415:
        update_user_stars(user_id, stars - 25)

# ========================
# ===== تشغيل البوت =======
# ========================
def main():
    updater = Updater(BOT_TOKEN)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_prompt))

    updater.start_polling()
    logging.info("ForgeFlow Bot running...")
    updater.idle()

if __name__ == "__main__":
    main()
