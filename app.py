import os
import asyncio
import sqlite3
import datetime
import re
from groq import Groq
from telegram import Update, LabeledPrice, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, PreCheckoutQueryHandler
from fpdf import FPDF
from arabic_reshaper import reshape
from bidi.algorithm import get_display

# --- إعدادات الألوان الذكية بناءً على الموضوع ---
def get_theme_color(topic):
    topic = topic.lower()
    if any(word in topic for word in ['nature', 'forest', 'طبيعة', 'غابة', 'زراعة']):
        return (34, 139, 34) # أخضر غابة
    elif any(word in topic for word in ['tech', 'future', 'تقنية', 'ذكاء', 'فضاء']):
        return (0, 102, 204) # أزرق تقني
    elif any(word in topic for word in ['history', 'old', 'تاريخ', 'قديم', 'تراث']):
        return (139, 69, 19) # بني تاريخي
    elif any(word in topic for word in ['love', 'romance', 'حب', 'رومانسية']):
        return (180, 0, 0) # أحمر هادئ
    elif any(word in topic for word in ['horror', 'dark', 'رعب', 'ظلام']):
        return (40, 40, 40) # رمادي غامق جداً
    else:
        return (20, 40, 120) # الكحلي الملكي الافتراضي

# --- محرك الـ PDF الذكي ---
def create_smart_pdf(chapters, filename, topic, custom_decoration=None):
    try:
        pdf = FPDF()
        pdf.set_auto_page_break(auto=True, margin=15)
        
        font_path = os.path.join(os.getcwd(), "arial.ttf")
        if os.path.exists(font_path):
            pdf.add_font('ArabicFont', '', font_path, uni=True)
            font_main = 'ArabicFont'
        else:
            font_main = 'Arial'

        r, g, b = get_theme_color(topic)
        pages_count = 0

        for title, content in chapters:
            # فلتر المحتوى الضعيف (أقل من 100 حرف)
            if not content or len(content.strip()) < 100:
                continue
            
            pdf.add_page()
            pages_count += 1
            
            # ضبط زخرفة العنوان
            is_arabic = any(ord(c) > 128 for c in title)
            if custom_decoration:
                display_title = f"{custom_decoration} {title.strip()} {custom_decoration}"
            else:
                # إذا لم يطلب وزخرفة إنجليزية، تبقى سادة. العربية تلمسها لمسة خفيفة.
                display_title = title.strip() if not is_arabic else f" {title.strip()} "

            pdf.set_text_color(r, g, b)
            pdf.set_font(font_main, size=24)
            pdf.multi_cell(190, 20, txt=get_display(reshape(display_title)), align='C')
            
            pdf.ln(10)
            pdf.set_text_color(0, 0, 0)
            pdf.set_font(font_main, size=14)
            
            # تنظيف الماركداون
            clean_text = re.sub(r'[*_#`]', '', content)
            pdf.multi_cell(190, 10, txt=get_display(reshape(clean_text)), align='R' if is_arabic else 'L')

        if pages_count == 0: return False
        pdf.output(filename)
        return True
    except Exception as e:
        print(f"PDF Logic Error: {e}")
        return False

# --- الأوامر الرئيسية (مختصرة للدمج) ---

async def build(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    # جلب آخر موضوع من الذاكرة لتحديد اللون
    conn = sqlite3.connect('architect_pro.db')
    last_msg = conn.execute("SELECT content FROM chat_history WHERE user_id=? AND role='user' ORDER BY rowid DESC LIMIT 1", (user_id,)).fetchone()
    topic = last_msg[0] if last_msg else "General"
    
    # فحص إذا طلب المستخدم زخرفة في المحادثة (مثلاً قال: اجعل الزخرفة ورود)
    decor_match = re.search(r'(زخرفة|decoration)\s*[:=]\s*(\S+)', topic)
    custom_decor = decor_match.group(2) if decor_match else None

    # (هنا تكملة كود الـ build السابق للتأليف...)
    
    # عند التصدير النهائي:
    final_chapters = conn.execute("SELECT title, content FROM book_progress WHERE user_id=?", (user_id,)).fetchall()
    pdf_name = f"Masterpiece_{user_id}.pdf"
    
    if create_smart_pdf(final_chapters, pdf_name, topic, custom_decor):
        with open(pdf_name, "rb") as f:
            await context.bot.send_document(chat_id=user_id, document=f, caption="✨ تم تصميم كتابك وتنسيقه آلياً بناءً على موضوعك!")
    # ... بقية التنظيف
