import telebot
import requests
import time
import os
from fpdf import FPDF
import arabic_reshaper
from bidi.algorithm import get_display

# --- إعدادات المحرك المركزي ---
BOT_TOKEN = "8605364115:AAHUmg2qyAanzsjLBUEoc5dS9ECaipyRrZY"
API_KEYS = [
    "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",
    "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",
    "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"
]

bot = telebot.TeleBot(BOT_TOKEN)

# --- دستور المحتوى (البرومبت المعماري) ---
SYSTEM_PROMPT = """أنت مؤلف خبير ومهندس محتوى متخصص في الكتب الرقمية الأكثر مبيعاً.
المهمة: بناء فصل كتاب غير روائي مكثف، فلسفي، وعميق.
الشروط: لغة عربية فصحى رصينة، لا تشكيل نهائياً، تقسيم منطقي للأفكار، سرد متواصل."""

# --- محرك إنشاء الـ PDF الاحترافي ---
class PublishingEngine(FPDF):
    def header(self):
        self.set_y(10)
        self.set_font("helvetica", 'I', 8)
        self.set_text_color(150, 150, 150)
        self.cell(0, 10, 'Digital Publishing House - Private Edition', 0, 1, 'L')

    def footer(self):
        self.set_y(-15)
        self.set_font("helvetica", 'I', 8)
        self.cell(0, 10, f'Page {self.page_no()}', 0, 0, 'C')

    def write_arabic_text(self, text, size=14, color=(0, 0, 0), align='R', is_title=False):
        if is_title:
            self.set_font("helvetica", 'B', 24)
            self.set_text_color(255, 45, 85) # لون الشركة (أحمر نيون)
        else:
            self.set_font("helvetica", size=size)
            self.set_text_color(*color)
            
        # معالجة النص العربي للـ PDF
        reshaped_text = arabic_reshaper.reshape(text)
        bidi_text = get_display(reshaped_text)
        
        self.multi_cell(0, 10, bidi_text, align=align)
        self.ln(5)

# --- وظيفة استرداد المحتوى من الذكاء الاصطناعي ---
def generate_chapter_content(api_key, topic, ch_number):
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    data = {
        "model": "openai/gpt-oss-20b",
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"اكتب الفصل رقم {ch_number} من كتاب بعنوان: {topic}. ركز على العمق المعرفي والتحليل الشامل."}
        ],
        "temperature": 0.85
    }
    try:
        response = requests.post(url, headers=headers, json=data, timeout=120)
        return response.json()['choices'][0]['message']['content']
    except Exception as e:
        print(f"Error: {e}")
        return None

# --- معالجة طلبات المستخدمين ---
@bot.message_handler(commands=['start'])
def start_command(message):
    welcome = (
        "🏢 **مرحباً بك في شركة النشر الإلكترونية الذكية**\n\n"
        "أنا المحرك المخصص لتشييد الكتب الرقمية. أرسل لي عنوان كتابك الآن، وسأقوم بـ:\n"
        "1️⃣ تخطيط الهيكل المعماري.\n"
        "2️⃣ كتابة المحتوى بعمق أكاديمي.\n"
        "3️⃣ تصدير ملف PDF احترافي.\n\n"
        "**ابدأ بإرسال العنوان الآن...**"
    )
    bot.reply_to(message, welcome, parse_mode="Markdown")

@bot.message_handler(func=lambda message: True)
def handle_publishing(message):
    topic = message.text
    chat_id = message.chat.id
    
    msg = bot.send_message(chat_id, "⚙️ **جاري فحص المفهوم وبدء التشييد...**")
    
    pdf = PublishingEngine()
    pdf.set_auto_page_break(auto=True, margin=20)
    
    total_chapters = 5
    successful_chapters = 0

    for i in range(1, total_chapters + 1):
        # تدوير المفاتيح الثلاثة تلقائياً
        active_key = API_KEYS[(i-1) % len(API_KEYS)]
        
        bot.edit_message_text(f"🖋️ جاري إنتاج الفصل {i} من {total_chapters}...\nاستخدام المحرك رقم {((i-1)%3)+1}", chat_id, msg.message_id)
        
        content = generate_chapter_content(active_key, topic, i)
        
        if content:
            pdf.add_page()
            pdf.write_arabic_text(f"الفصل {i}", is_title=True)
            pdf.write_arabic_text(content)
            successful_chapters += 1
            time.sleep(7) # حماية لثبات الاتصال
        else:
            bot.send_message(chat_id, f"⚠️ حدث تعثر في الفصل {i}، سيتم المحاولة في الفصل التالي.")

    if successful_chapters > 0:
        file_name = f"Manuscript_{chat_id}.pdf"
        pdf.output(file_name)
        
        bot.edit_message_text("🚀 **اكتملت المخطوطة!** جاري التصدير النهائي...", chat_id, msg.message_id)
        
        with open(file_name, 'rb') as document:
            bot.send_document(
                chat_id, 
                document, 
                caption=f"✅ تم إنتاج كتابك: **{topic}**\n\nالمحتوى جاهز للمراجعة والنشر الرقمي.",
                parse_mode="Markdown"
            )
        os.remove(file_name)
    else:
        bot.send_message(chat_id, "❌ عذراً، واجه المحرك مشكلة فنية في جميع المفاتيح. يرجى المحاولة لاحقاً.")

# --- تشغيل المحرك ---
if __name__ == "__main__":
    print("Publishing House is Online...")
    bot.infinity_polling()
