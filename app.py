import os
import time
import json
import requests
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from fpdf import FPDF

# --- الإعدادات ---
API_KEY = "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"
TELEGRAM_TOKEN = "8605364115:AAHUmg2qyAanzsjLBUEoc5dS9ECaipyRrZY"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

# --- كلاس إنشاء الـ PDF ---
class AI_Book_PDF(FPDF):
    def __init__(self):
        super().__init__()
        self.set_auto_page_break(auto=True, margin=15)
        
    def header(self):
        self.set_font('Arial', 'B', 8)
        self.cell(0, 10, 'AI Digital Book - Auto Generated', 0, 1, 'C')

# --- دالة إرسال الطلب عبر Requests مع نظام التبريد ---
def call_groq_api(prompt):
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7
    }

    while True:
        try:
            response = requests.post(GROQ_URL, headers=headers, json=payload)
            
            if response.status_code == 200:
                return response.json()['choices'][0]['message']['content']
            
            elif response.status_code == 429: # خطأ التبريد (Too Many Requests)
                print("❄️ Cooldown: Rate limit reached. Waiting 10 seconds...")
                time.sleep(10)
            
            else:
                print(f"❌ Error {response.status_code}: {response.text}")
                return None
        except Exception as e:
            print(f"⚠️ Connection Error: {e}")
            time.sleep(5)

# --- معالجة طلب البوت ---
async def handle_book_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    topic = update.message.text
    status_msg = await update.message.reply_text(f"⏳ جاري تحضير كتابك: {topic}\nيتم الآن توليد الفهرس...")

    # 1. توليد الفهرس
    outline_prompt = f"أنشئ فهرس كتاب 'مارك داون' مزخرف عن {topic}. يتكون من 10 فصول. أجب بالعناوين فقط."
    outline = call_groq_api(outline_prompt)
    
    if not outline:
        await status_msg.edit_text("❌ فشل الاتصال بالسيرفر. تأكد من مفتاح الـ API.")
        return

    chapters = [c.strip() for c in outline.split('\n') if len(c.strip()) > 3]
    
    pdf = AI_Book_PDF()
    book_storage = []

    # 2. توليد الفصول مع التخزين المؤقت
    for i, title in enumerate(chapters):
        await status_msg.edit_text(f"✍️ جاري كتابة الفصل {i+1} من {len(chapters)}...\n(تم حفظ {len(book_storage)} فصول في الذاكرة)")
        
        chapter_prompt = f"اكتب فصلاً كاملاً ومفصلاً عن '{title}' ضمن كتاب '{topic}'. استخدم تنسيق Markdown وزخارف للعناوين. اجعل النص طويلاً جداً وقيمًا."
        content = call_groq_api(chapter_prompt)
        
        if content:
            book_storage.append({"title": title, "content": content})
            
            # إضافة للـ PDF
            pdf.add_page()
            pdf.set_font("Arial", 'B', 16)
            pdf.multi_cell(0, 10, txt=title.encode('latin-1', 'ignore').decode('latin-1'), align='C')
            pdf.ln(5)
            pdf.set_font("Arial", size=12)
            pdf.multi_cell(0, 10, txt=content.encode('latin-1', 'ignore').decode('latin-1'))

    # 3. حفظ وإرسال
    file_path = f"book_{update.message.chat_id}.pdf"
    pdf.output(file_path)
    
    await status_msg.edit_text("✅ اكتمل الكتاب! جاري الرفع...")
    await update.message.reply_document(document=open(file_path, 'rb'), caption=f"كتابك حول: {topic}")
    os.remove(file_path)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("أهلاً بك! أرسل لي أي موضوع وسأصنع لك كتاباً كاملاً بصيغة PDF.")

# --- تشغيل البوت ---
def main():
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_book_request))
    
    print("Bot is running via Requests...")
    application.run_polling()

if __name__ == "__main__":
    main()
