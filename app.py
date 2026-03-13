import logging
import json
import os
import random
import re
import time
import asyncio
from datetime import datetime
from typing import Dict, Optional, List
from enum import Enum
import hashlib
from dataclasses import dataclass, asdict

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters
)
from groq import Groq
from fpdf import FPDF
import arabic_reshaper
from bidi.algorithm import get_display

# ==================== الإعدادات الأساسية ====================

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# التوكنات والمفاتيح
TELEGRAM_TOKEN = "8605364115:AAHUmg2qyAanzsjLBUEoc5dS9ECaipyRrZY"
GROQ_API_KEY = "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"
ADMIN_ID = 8443969410
BOOK_PRICE = 25

# حالات المحادثة
DISCUSSION = 1

# إعدادات التبريد
COOLDOWN_BETWEEN_CHUNKS = 2
MAX_CHUNK_SIZE = 1500
MAX_RETRIES = 3

# مجلدات التخزين
DATA_DIR = "bot_data"
USERS_FILE = f"{DATA_DIR}/users.json"
BOOKS_DIR = f"{DATA_DIR}/books"
TEMP_DIR = f"{DATA_DIR}/temp"
CACHE_DIR = f"{DATA_DIR}/cache"

for dir_path in [DATA_DIR, BOOKS_DIR, TEMP_DIR, CACHE_DIR]:
    os.makedirs(dir_path, exist_ok=True)

# ==================== نماذج البيانات ====================

class UserRole(str, Enum):
    ADMIN = "admin"
    FREE_USER = "free_user"
    REGULAR = "regular"

@dataclass
class UserData:
    user_id: int
    username: str = ""
    first_name: str = ""
    role: UserRole = UserRole.REGULAR
    balance: int = 0
    is_blocked: bool = False
    total_books: int = 0
    total_pages: int = 0
    created_at: str = ""
    
    def to_dict(self):
        data = asdict(self)
        data['role'] = self.role.value
        return data
    
    @classmethod
    def from_dict(cls, data):
        return cls(
            user_id=data['user_id'],
            username=data.get('username', ''),
            first_name=data.get('first_name', ''),
            role=UserRole(data.get('role', 'regular')),
            balance=data.get('balance', 0),
            is_blocked=data.get('is_blocked', False),
            total_books=data.get('total_books', 0),
            total_pages=data.get('total_pages', 0),
            created_at=data.get('created_at', datetime.now().isoformat())
        )

@dataclass
class SessionData:
    user_id: int
    messages: List[Dict]
    topic: str
    created_at: float
    last_activity: float
    temp_files: List[str]
    
    def __init__(self, user_id: int):
        self.user_id = user_id
        self.messages = []
        self.topic = ""
        self.created_at = time.time()
        self.last_activity = time.time()
        self.temp_files = []

# ==================== إدارة التخزين ====================

class StorageManager:
    def __init__(self):
        self.users = self._load_users()
        self.sessions: Dict[int, SessionData] = {}
        
    def _load_users(self) -> Dict[int, UserData]:
        users = {}
        if os.path.exists(USERS_FILE):
            try:
                with open(USERS_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for user_id, user_data in data.items():
                        users[int(user_id)] = UserData.from_dict(user_data)
            except Exception as e:
                logger.error(f"خطأ في تحميل المستخدمين: {e}")
        return users
    
    def save_users(self):
        data = {}
        for user_id, user in self.users.items():
            data[str(user_id)] = user.to_dict()
        
        with open(USERS_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    def get_user(self, user_id: int) -> Optional[UserData]:
        return self.users.get(user_id)
    
    def create_user(self, user_id: int, username: str = "", first_name: str = "") -> UserData:
        user = UserData(
            user_id=user_id,
            username=username,
            first_name=first_name,
            created_at=datetime.now().isoformat()
        )
        self.users[user_id] = user
        self.save_users()
        return user
    
    def create_session(self, user_id: int) -> SessionData:
        self.sessions[user_id] = SessionData(user_id)
        return self.sessions[user_id]
    
    def get_session(self, user_id: int) -> Optional[SessionData]:
        session = self.sessions.get(user_id)
        if session:
            session.last_activity = time.time()
        return session
    
    def delete_session(self, user_id: int):
        if user_id in self.sessions:
            for temp_file in self.sessions[user_id].temp_files:
                try:
                    if os.path.exists(temp_file):
                        os.remove(temp_file)
                except:
                    pass
            del self.sessions[user_id]
    
    def add_temp_file(self, user_id: int, filepath: str):
        if user_id in self.sessions:
            self.sessions[user_id].temp_files.append(filepath)
    
    def cleanup_old_files(self):
        """تنظيف الملفات القديمة (تُستدعى يدوياً)"""
        try:
            now = time.time()
            for filename in os.listdir(TEMP_DIR):
                filepath = os.path.join(TEMP_DIR, filename)
                if os.path.getctime(filepath) < now - 3600:
                    os.remove(filepath)
            
            for filename in os.listdir(CACHE_DIR):
                filepath = os.path.join(CACHE_DIR, filename)
                if os.path.getctime(filepath) < now - 86400:
                    os.remove(filepath)
        except Exception as e:
            logger.error(f"خطأ في التنظيف: {e}")

# ==================== خدمات PDF ====================

class PDFService:
    def __init__(self):
        pass
    
    def prepare_arabic_text(self, text: str) -> str:
        """تجهيز النص العربي للعرض في PDF"""
        try:
            reshaped_text = arabic_reshaper.reshape(text)
            bidi_text = get_display(reshaped_text)
            return bidi_text
        except:
            return text
    
    def create_pdf(self, content: str, title: str, author: str = "بوت الكتب الذكي") -> str:
        """إنشاء ملف PDF من النص"""
        
        class ArabicPDF(FPDF):
            def header(self):
                self.set_font('Arial', 'B', 16)
                self.cell(0, 10, self.title, 0, 1, 'C')
                self.ln(10)
            
            def footer(self):
                self.set_y(-15)
                self.set_font('Arial', 'I', 8)
                self.cell(0, 10, f'الصفحة {self.page_no()}', 0, 0, 'C')
        
        filename = f"book_{int(time.time())}_{hashlib.md5(title.encode()).hexdigest()[:8]}.pdf"
        filepath = os.path.join(BOOKS_DIR, filename)
        
        pdf = ArabicPDF()
        pdf.set_title(title)
        pdf.set_author(author)
        
        # الغلاف
        pdf.add_page()
        pdf.set_font('Arial', 'B', 20)
        pdf.cell(0, 40, '', 0, 1)
        pdf.cell(0, 20, self.prepare_arabic_text(title), 0, 1, 'C')
        pdf.set_font('Arial', 'I', 12)
        pdf.cell(0, 10, f"تأليف: {author}", 0, 1, 'C')
        pdf.cell(0, 10, datetime.now().strftime("%Y-%m-%d"), 0, 1, 'C')
        
        # المحتوى
        paragraphs = content.split('\n\n')
        
        for para in paragraphs:
            para = para.strip()
            if not para:
                continue
            
            if para.startswith('#'):
                pdf.add_page()
                chapter = para.replace('#', '').strip()
                pdf.set_font('Arial', 'B', 14)
                pdf.cell(0, 10, self.prepare_arabic_text(chapter), 0, 1, 'R')
                pdf.ln(5)
                continue
            
            pdf.set_font('Arial', '', 12)
            lines = para.split('\n')
            for line in lines:
                if line.strip():
                    text = self.prepare_arabic_text(line.strip())
                    pdf.multi_cell(0, 8, text, 0, 'R')
            pdf.ln(5)
        
        pdf.output(filepath)
        return filepath

# ==================== خدمات الذكاء الاصطناعي ====================

class AIService:
    def __init__(self, api_key: str):
        self.client = Groq(api_key=api_key)
    
    async def generate_book_chunk(self, prompt: str, chunk_number: int, total_chunks: int) -> str:
        """توليد جزء من الكتاب"""
        
        system_prompt = f"أنت كاتب محترف. هذا الجزء {chunk_number} من {total_chunks} من الكتاب."
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ]
        
        for attempt in range(MAX_RETRIES):
            try:
                completion = self.client.chat.completions.create(
                    model="openai/gpt-oss-120b",
                    messages=messages,
                    temperature=0.8,
                    max_tokens=2000,
                    top_p=1,
                    stream=False
                )
                return completion.choices[0].message.content
                
            except Exception as e:
                logger.error(f"محاولة {attempt + 1} فشلت: {e}")
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(COOLDOWN_BETWEEN_CHUNKS * (attempt + 1))
                else:
                    raise e
    
    async def generate_full_book(self, discussion: str, topic: str) -> str:
        """توليد الكتاب كاملاً"""
        
        chunks = []
        
        # الجزء الأول: الهيكل
        structure = await self.generate_book_chunk(
            f"أعطني هيكل الكتاب عن: {topic}\n{discussion[:1000]}", 1, 4
        )
        chunks.append(structure)
        await asyncio.sleep(COOLDOWN_BETWEEN_CHUNKS)
        
        # الجزء الثاني: المقدمة
        intro = await self.generate_book_chunk(
            f"اكتب المقدمة والفصل الأول بناءً على: {structure[:500]}", 2, 4
        )
        chunks.append(intro)
        await asyncio.sleep(COOLDOWN_BETWEEN_CHUNKS)
        
        # الجزء الثالث: الفصول الوسطى
        middle = await self.generate_book_chunk(
            f"اكمل الفصول الوسطى: {intro[-500:]}", 3, 4
        )
        chunks.append(middle)
        await asyncio.sleep(COOLDOWN_BETWEEN_CHUNKS)
        
        # الجزء الرابع: الخاتمة
        conclusion = await self.generate_book_chunk(
            f"اكتب الخاتمة للكتاب عن: {topic}", 4, 4
        )
        chunks.append(conclusion)
        
        return "\n\n---\n\n".join(chunks)
    
    async def chat_response(self, message: str, history: list) -> str:
        """الرد على المحادثة"""
        
        messages = [
            {"role": "system", "content": "أنت مساعد متخصص في تطوير أفكار الكتب."},
            *history[-5:],
            {"role": "user", "content": message}
        ]
        
        try:
            completion = self.client.chat.completions.create(
                model="openai/gpt-oss-120b",
                messages=messages,
                temperature=0.7,
                max_tokens=1000,
                top_p=1,
                stream=False
            )
            return completion.choices[0].message.content
        except Exception as e:
            logger.error(f"خطأ في الرد: {e}")
            return "عذراً، حدث خطأ. حاول مرة أخرى."

# ==================== بوت تلغرام ====================

class EBookBot:
    def __init__(self, token: str, groq_key: str):
        self.token = token
        self.storage = StorageManager()
        self.ai_service = AIService(groq_key)
        self.pdf_service = PDFService()
        
        # إضافة المشرف
        if ADMIN_ID not in self.storage.users:
            admin = UserData(
                user_id=ADMIN_ID,
                username="admin",
                first_name="Admin",
                role=UserRole.ADMIN
            )
            self.storage.users[ADMIN_ID] = admin
            self.storage.save_users()
    
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        
        if user.id not in self.storage.users:
            self.storage.create_user(user.id, user.username or "", user.first_name or "")
        
        welcome = f"""
مرحباً بك في بوت صناعة الكتب الإلكترونية {user.first_name}

الميزات:
• كتب بتنسيق PDF احترافي
• نظام تبريد للمحرك
• تخزين مؤقت للجلسات

السعر: {BOOK_PRICE} نجمة

الأوامر:
/newbook - بدء كتاب جديد
/build - إنشاء الكتاب
/balance - رصيدي
/cancel - إلغاء
"""
        await update.message.reply_text(welcome)
    
    async def newbook(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        
        user = self.storage.get_user(user_id)
        if user and user.is_blocked:
            await update.message.reply_text("حسابك محظور.")
            return ConversationHandler.END
        
        self.storage.create_session(user_id)
        
        await update.message.reply_text(
            "أخبرني عن فكرة كتابك:\n"
            "- الموضوع الرئيسي\n"
            "- الجمهور المستهدف\n"
            "- الأفكار الرئيسية\n\n"
            "عندما تجهز، اكتب /build"
        )
        
        return DISCUSSION
    
    async def discuss(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        message = update.message.text
        
        session = self.storage.get_session(user_id)
        if not session:
            await update.message.reply_text("ابدأ بـ /newbook أولاً")
            return ConversationHandler.END
        
        if not session.topic and len(session.messages) == 0:
            session.topic = message[:50]
        
        session.messages.append({"role": "user", "content": message})
        
        await update.message.chat.send_action(action="typing")
        
        response = await self.ai_service.chat_response(
            message, 
            session.messages[:-1]
        )
        
        session.messages.append({"role": "assistant", "content": response})
        await update.message.reply_text(response)
        
        return DISCUSSION
    
    async def build(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        
        session = self.storage.get_session(user_id)
        if not session or not session.messages:
            await update.message.reply_text("لا توجد مناقشة. ابدأ بـ /newbook")
            return
        
        user_data = self.storage.get_user(user_id)
        topic = session.topic or "كتاب جديد"
        
        # التحقق من الصلاحية
        can_proceed = False
        if user_data.role in [UserRole.ADMIN, UserRole.FREE_USER]:
            can_proceed = True
        elif user_data.balance >= BOOK_PRICE:
            can_proceed = True
            user_data.balance -= BOOK_PRICE
            self.storage.save_users()
        else:
            await update.message.reply_text(
                f"رصيدك غير كافٍ. تحتاج {BOOK_PRICE} نجمة.\n"
                f"رصيدك الحالي: {user_data.balance} نجمة"
            )
            return
        
        # جمع المناقشة
        discussion = "\n".join([
            f"{msg['role']}: {msg['content']}"
            for msg in session.messages
        ])
        
        status = await update.message.reply_text(
            "جاري إنشاء كتابك...\n"
            "قد تستغرق العملية دقيقتين."
        )
        
        try:
            # توليد الكتاب
            book_content = await self.ai_service.generate_full_book(discussion, topic)
            
            # إنشاء PDF
            pdf_file = self.pdf_service.create_pdf(
                book_content,
                topic,
                user_data.first_name or "مستخدم"
            )
            
            self.storage.add_temp_file(user_id, pdf_file)
            
            # تحديث الإحصائيات
            user_data.total_books += 1
            pages_estimate = len(book_content) // 1500 + 10
            user_data.total_pages += pages_estimate
            self.storage.save_users()
            
            await status.delete()
            
            with open(pdf_file, 'rb') as f:
                await update.message.reply_document(
                    document=f,
                    filename=f"كتاب_{topic[:30]}.pdf",
                    caption=f"تم إنشاء كتابك بنجاح!\n"
                           f"الموضوع: {topic}\n"
                           f"الصفحات: ~{pages_estimate}"
                )
            
            # تنظيف الملفات القديمة (مرة واحدة كل 10 كتب)
            if user_data.total_books % 10 == 0:
                self.storage.cleanup_old_files()
            
            self.storage.delete_session(user_id)
            
        except Exception as e:
            logger.error(f"خطأ: {e}")
            await status.edit_text("حدث خطأ. حاول مرة أخرى.")
    
    async def balance(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        user_data = self.storage.get_user(user_id)
        
        if not user_data:
            await update.message.reply_text("مستخدم غير مسجل")
            return
        
        role_names = {
            UserRole.ADMIN: "مشرف",
            UserRole.FREE_USER: "مميز (مجاني)",
            UserRole.REGULAR: "عادي"
        }
        
        text = f"""
الرصيد: {user_data.balance} نجمة
الدور: {role_names[user_data.role]}
الكتب: {user_data.total_books}
الصفحات: ~{user_data.total_pages}
السعر: {BOOK_PRICE} نجمة
"""
        await update.message.reply_text(text)
    
    async def cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        self.storage.delete_session(user_id)
        await update.message.reply_text("تم الإلغاء.")
        return ConversationHandler.END
    
    # أوامر المشرف
    async def add_free(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        
        if user_id != ADMIN_ID:
            await update.message.reply_text("غير مصرح")
            return
        
        try:
            target = int(context.args[0])
            if target not in self.storage.users:
                self.storage.create_user(target)
            
            self.storage.users[target].role = UserRole.FREE_USER
            self.storage.save_users()
            await update.message.reply_text(f"تمت إضافة {target}")
        except:
            await update.message.reply_text("استخدم: /add_free user_id")
    
    async def remove_free(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        
        if user_id != ADMIN_ID:
            await update.message.reply_text("غير مصرح")
            return
        
        try:
            target = int(context.args[0])
            if target in self.storage.users:
                self.storage.users[target].role = UserRole.REGULAR
                self.storage.save_users()
                await update.message.reply_text(f"تمت إزالة {target}")
        except:
            await update.message.reply_text("استخدم: /remove_free user_id")
    
    async def users_list(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        
        if user_id != ADMIN_ID:
            await update.message.reply_text("غير مصرح")
            return
        
        text = "المستخدمين:\n\n"
        for uid, user in list(self.storage.users.items())[:20]:
            role_icon = {
                UserRole.ADMIN: "👑",
                UserRole.FREE_USER: "⭐",
                UserRole.REGULAR: "👤"
            }[user.role]
            
            text += f"{role_icon} {uid}: {user.first_name}\n"
            text += f"   الرصيد: {user.balance} | الكتب: {user.total_books}\n\n"
        
        await update.message.reply_text(text)
    
    def run(self):
        """تشغيل البوت"""
        app = Application.builder().token(self.token).build()
        
        # الأوامر
        app.add_handler(CommandHandler("start", self.start))
        app.add_handler(CommandHandler("balance", self.balance))
        app.add_handler(CommandHandler("build", self.build))
        app.add_handler(CommandHandler("cancel", self.cancel))
        app.add_handler(CommandHandler("add_free", self.add_free))
        app.add_handler(CommandHandler("remove_free", self.remove_free))
        app.add_handler(CommandHandler("users", self.users_list))
        
        # محادثة الكتاب
        conv = ConversationHandler(
            entry_points=[CommandHandler("newbook", self.newbook)],
            states={
                DISCUSSION: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.discuss)
                ]
            },
            fallbacks=[CommandHandler("cancel", self.cancel)]
        )
        app.add_handler(conv)
        
        logger.info("✅ البوت يعمل...")
        app.run_polling()

# ==================== التشغيل ====================

if __name__ == "__main__":
    bot = EBookBot(TELEGRAM_TOKEN, GROQ_API_KEY)
    bot.run()
