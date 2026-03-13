#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import subprocess

# ==== تثبيت تلقائي للمكتبات ====
required_packages = ["python-telegram-bot==20.3", "openai"]
for pkg in required_packages:
    try:
        __import__(pkg.split("==")[0])
    except ImportError:
        subprocess.check_call([sys.executable, "-m", "pip", "install", pkg])

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
from openai import OpenAI
import time

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

# ==== برومبت داخلي قوي لإنشاء المواقع ====
FORGE_PROMPT = """
[SYSTEM INSTRUCTION - READ CAREFULLY]

You are an expert Frontend Developer and a professional UI/UX Designer. Your task is to build a complete, clean, and production-ready website based on the description and specifications provided below.

Strictly adhere to the project structure, required technologies, and quality standards mentioned in this document. The code you produce must be modular, readable, and scalable.

---

## 1. Core Task
[Write a precise description of the website you want to build here. Be as specific as possible. For example: "Build a single-page landing page for a startup that offers an AI-powered image generation tool. The page should highlight the service's key features, pricing plans, and showcase a gallery of generated images."]

## 2. Features & Functionality
- [Feature 1: Example: A Hero section with a main headline (H1), a supporting sub-headline, and two clear Call-to-Action (CTA) buttons.]
- [Feature 2: Example: A "How It Works" section explaining the process in 3 simple steps, each with an icon and short description.]
- [Feature 3: Example: A responsive image gallery (Grid layout) displaying examples of generated images, with a subtle hover effect.]
- [Feature 4: Example: A Pricing section with 3 cards (e.g., Free, Pro, Enterprise), each listing key features and the price.]
- [Feature 5: Example: A simple footer with links to social media (icons) and a copyright notice.]
- [Feature 6: Example: The website must be fully responsive and work perfectly on mobile, tablet, and desktop devices.]

## 3. Technical Stack & Constraints
- **Framework:** Use **Next.js (App Router)** with **TypeScript**.
- **Styling:** Use **Tailwind CSS** exclusively for all styling. Do not use plain CSS or other UI libraries unless specifically requested.
- **Components:** Build the UI using **functional components** and ensure code is clean and well-structured.
- **Icons:** Use a popular icon library like **Lucide React** or **React Icons**.
- **Fonts:** Use a system font stack or integrate a font like 'Inter' from Google Fonts.
- **State Management:** Use React hooks (useState) for any local UI state (e.g., mobile menu toggle).
- **Deployment:** Ensure the project structure is ready for deployment on platforms like Vercel (i.e., has a correct package.json with build and start scripts).

## 4. Design & User Experience (UI/UX)
- **Color Palette:**
    - Primary Color: `#3B82F6` (Blue)
    - Secondary Color: `#10B981` (Green)
    - Background: `#FFFFFF` (White)
    - Text: `#1F2937` (Dark Gray)
    - Accent/Gray: `#F3F4F6` (Light Gray)
- **Spacing & Layout:** Use ample white space. Content should be centered with a max-width container (`mx-auto`, `px-4`).
- **Visual Style:** Aim for a clean, modern, and professional look with subtle rounded corners (`rounded-lg`) on cards and buttons.
- **Animations:** Add subtle, performant animations on scroll (e.g., fade-in effects) or on hover. You can use simple CSS transitions or a lightweight library like `framer-motion` if needed, but keep it minimal.

## 5. Code Quality & Structure
- The code must be well-organized inside the `/app` directory.
- Break down the UI into reusable components stored in a `/components` folder (e.g., `Header.tsx`, `Hero.tsx`, `PricingCard.tsx`).
- Use semantic HTML tags (`<header>`, `<section>`, `<article>`, `<footer>`).
- Ensure all interactive elements (buttons, links) are accessible (e.g., include `aria-labels` where necessary).

## 6. Process & Deliverables
1.  **Setup:** Initialize the Next.js project and install necessary dependencies (Tailwind, Lucide, etc.).
2.  **Layout:** Create the root layout and implement the basic page structure.
3.  **Build:** Construct the page section by section (Hero, Features, Gallery, Pricing, Footer).
4.  **Polish:** Add responsiveness, final styling touches, and animations.
5.  **Output:** Provide the complete code for all files. Explain any complex logic if necessary.
"""

# ==== دالة توليد HTML ====
def generate_html(prompt: str) -> str:
    html_code = f"""<!DOCTYPE html>
<html lang="ar">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ForgeFlow-Bot Result</title>
<style>
body {{ background: #fdf5e6; font-family: 'Cairo', sans-serif; color: #3d2f1f; margin:0; padding:0; }}
.container {{ max-width: 1000px; margin: 30px auto; padding: 20px; background: #fffaf2; border-radius: 20px; box-shadow: 0 5px 15px rgba(0,0,0,0.1); }}
h1 {{ color: #b58a4b; text-align:center; }}
pre {{ background: #f0e6d2; padding: 15px; border-radius: 10px; overflow-x:auto; white-space: pre-wrap; word-wrap: break-word; }}
@media(max-width:768px) {{
.container {{ margin:10px; padding:15px; }}
}}
</style>
</head>
<body>
<div class="container">
<h1>✨ ForgeFlow-Bot AI Generated Website</h1>
<pre>{prompt}</pre>
</div>
</body>
</html>"""
    return html_code

# ==== جلسة مؤقتة لتخزين الرسائل ====
user_sessions = {}

# ==== دوال البوت ====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await update.message.reply_text(
        f"مرحبا بك في ForgeFlow-Bot!\n🟊 للاستخدام تحتاج إلى 25 نجمة، إلا إذا كنت المستخدم الخاص (ID={FREE_USER_ID}).\n"
        "للبدء، أرسل وصف الموقع الذي تريد إنشاءه."
    )
    if user_id == FREE_USER_ID:
        await update.message.reply_text("✅ أنت مستخدم مجاني خاص، يمكنك تجربة البوت مباشرة.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()

    # التحقق من الدفع أو المستخدم الخاص
    if user_id != FREE_USER_ID:
        await update.message.reply_text("❌ يجب دفع 25 نجمة لتتمكن من استخدام البوت (خطة مستقبلية).")
        return

    # بدء جلسة مؤقتة
    if user_id not in user_sessions:
        user_sessions[user_id] = []

    user_sessions[user_id].append(text)
    await update.message.reply_text("📌 تم حفظ وصفك، يمكنك الاستمرار أو إرسال /build لإنشاء الموقع.")

async def build_site(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id != FREE_USER_ID:
        await update.message.reply_text("❌ يجب دفع 25 نجمة لتتمكن من استخدام البوت (خطة مستقبلية).")
        return

    if user_id not in user_sessions or len(user_sessions[user_id]) == 0:
        await update.message.reply_text("⚠️ لم يتم إرسال أي وصف لإنشاء الموقع.")
        return

    prompt_text = "\n".join(user_sessions[user_id])
    full_prompt = FORGE_PROMPT + "\n\n" + prompt_text

    await update.message.reply_text("⏳ جاري إنشاء الموقع... يرجى الانتظار...")

    try:
        response = client.responses.create(
            input=full_prompt,
            model="openai/gpt-oss-20b"
        )
        result_text = response.output_text
    except Exception as e:
        result_text = f"حدث خطأ أثناء توليد الكود: {str(e)}"

    html_content = generate_html(result_text)
    file_path = f"forgeflow_{user_id}.html"
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    await update.message.reply_document(document=open(file_path, "rb"), filename="ForgeFlow_Result.html")
    await update.message.reply_text("✅ تم إنشاء الموقع وإرساله! ✨")

    # مسح الجلسة بعد الإرسال
    user_sessions[user_id] = []

# ==== تهيئة التطبيق ====
app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("build", build_site))
app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))

# ==== تشغيل البوت ====
print("🤖 ForgeFlow-Bot يعمل الآن...")
app.run_polling()
