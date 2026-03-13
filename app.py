import os
import time
import asyncio
from groq import Groq, RateLimitError
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from fpdf import FPDF

# --- الإعدادات ---
GROQ_API_KEY = "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"
TELEGRAM_TOKEN = "8605364115:AAHUmg2qyAanzsjLBUEoc5dS9ECaipyRrZY"

client = Groq(api_key=GROQ_API_KEY)

# --- كلاس إنشاء الـ PDF يدعم العربية ---
class AI_Book_PDF(FPDF):
    def __init__(self):
        super().__init__()
        # ملاحظة: ليدعم العربية يجب تحميل خط وتفعيله هنا
        # self.add_font('ArabicFont', '', 'arial.ttf', unicode=True) 
        self.set_auto_page_break(auto=True, margin=15)
        
    def header(self):
        self.set_font('Helvetica', 'B', 8)
        self.cell(0, 10, 'AI Generated Masterpiece', 0, 1, 'C')

    def footer(self):
        self.set_y(-15)
        self.set_font('Helvetica', 'I', 8)
        self.cell(0, 10, f'Page {self.page_no()}', 0, 0, 'C')

# --- دالة التوليد مع نظام التبريد والتخزين ---
async def generate_chapter_with_retry(prompt, retries=5):
    """دالة تحاول التوليد وإذا واجهت زحمة (Rate Limit) تنتظر 10 ثوانٍ"""
    for i in range(retries):
        try:
            completion = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_completion_tokens=4000 # زيادة عدد الكلمات للفصل الواحد
            )
            return completion.choices[0].message.content
        except RateLimitError:
            print(f"Rate limit hit, sleeping 10s... (Attempt {i+1})")
            time.sleep(10)
        except Exception as e:
            print(f"Error: {e}")
            time.sleep(5)
    return None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("مرحباً بك في بوت صناعة الكتب الذكي! 📚\nأرسل لي عنوان الكتاب وسأقوم بإنتاجه في 20 صفحة PDF.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    topic = update.message.text
    status_msg = await update.message.reply_text(f"🚀 بدأت العمل على كتاب: {topic}\nجاري التخطيط للفصول...")

    # 1. إنشاء الفهرس (15 - 20 فصل لضمان طول الكتاب)
    outline_prompt = f"قم بإنشاء فهرس كتاب مفصل جداً عن '{topic}'. أريد 15 عنواناً للفصول. اجعل العناوين جذابة ومزخرفة بمارك داون. أجب بالعناوين فقط."
    outline_text = await generate_chapter_with_retry(outline_prompt)
    
    if not outline_text:
        await status_msg.edit_text("عذراً، واجهت مشكلة في الاتصال بـ Groq. حاول لاحقاً.")
        return

    chapters = [line.strip() for line in outline_text.split('\n') if len(line.strip()) > 5][:15]
    
    # 2. نظام التخزين المؤقت (المصفوفة)
    book_storage = []
    pdf = AI_Book_PDF()
    
    # 3. توليد المحتوى فصلاً فصلاً
    for index, title in enumerate(chapters):
        current_step = f"📝 جاري كتابة الفصل {index+1} من {len(chapters)}:\n{title}"
        await status_msg.edit_text(f"{current_step}\n(يتم الحفظ في التخزين المؤقت...)")

        chapter_prompt = f"""
        اكتب محتوى الفصل التالي لكتاب عن '{topic}'.
        العنوان: {title}.
        المطلوب: كتابة محتوى طويل جداً ممتد (شرح مفصل، أمثلة، نصائح).
        استخدم لغة عربية فصحى وتنسيق مارك داون (عناوين فرعية، نقاط، زخرفة).
        اجعل الفصل يملأ صفحتين على الأقل من المعلومات القيمة.
        """
        
        content = await generate_chapter_with_retry(chapter_prompt)
        
        if content:
            # تخزين في الذاكرة المؤقتة
            book_storage.append({"title": title, "content": content})
            
            # إضافة للفصل في ملف الـ PDF فوراً
            pdf.add_page()
            pdf.set_font('Helvetica', 'B', 16)
            # ملاحظة: تم استخدام Helvetica للإنجليزية، للعربية استخدم الخط الذي ستحمله
            pdf.multi_cell(0, 10, txt=title.encode('latin-1', 'ignore').decode('latin-1'), align='C')
            pdf.ln(10)
            pdf.set_font('Helvetica', '', 12)
            pdf.multi_cell(0, 10, txt=content.encode('latin-1', 'ignore').decode('latin-1'))
        
        # تبريد بسيط بين كل فصل وفصل لتجنب الحظر
        await asyncio.sleep(2)

    # 4. إنهاء الملف وإرساله
    file_name = f"Book_{int(time.time())}.pdf"
    pdf.output(file_name)
    
    await status_msg.edit_text("✅ اكتمل الكتاب بنجاح! جاري إرسال الملف...")
    await update.message.reply_document(document=open(file_name, 'rb'), caption=f"إليك كتابك حول: {topic}")
    
    # تنظيف الملفات
    os.remove(file_name)

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("البوت يعمل الآن...")
    app.run_polling()

if __name__ == '__main__':
    main()
