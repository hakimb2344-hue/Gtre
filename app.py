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
COOLDOWN_BETWEEN_CHUNKS = 2  # ثواني بين أجزاء الكتاب
MAX_CHUNK_SIZE = 1500  # حجم الجزء الواحد من الكتاب
MAX_RETRIES = 3  # عدد محاولات إعادة المحاولة عند الفشل

# مجلدات التخزين
DATA_DIR = "bot_data"
USERS_FILE = f"{DATA_DIR}/users.json"
BOOKS_DIR = f"{DATA_DIR}/books"
TEMP_DIR = f"{DATA_DIR}/temp"
CACHE_DIR = f"{DATA_DIR}/cache"

# إنشاء المجلدات
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
        user = cls(
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
        return user

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

@dataclass
class CacheData:
    key: str
    content: str
    created_at: float
    expires_at: float

# ==================== إدارة التخزين ====================

class StorageManager:
    def __init__(self):
        self.users = self._load_users()
        self.sessions: Dict[int, SessionData] = {}
        self.cache: Dict[str, CacheData] = {}
        self._cleanup_old_files()
    
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
            # حذف الملفات المؤقتة
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
    
    def get_cache(self, key: str) -> Optional[str]:
        cache = self.cache.get(key)
        if cache and time.time() < cache.expires_at:
            return cache.content
        return None
    
    def set_cache(self, key: str, content: str, ttl: int = 3600):
        self.cache[key] = CacheData(
            key=key,
            content=content,
            created_at=time.time(),
            expires_at=time.time() + ttl
        )
    
    def _cleanup_old_files(self):
        """تنظيف الملفات القديمة"""
        try:
            # تنظيف الملفات المؤقتة الأقدم من ساعة
            now = time.time()
            for filename in os.listdir(TEMP_DIR):
                filepath = os.path.join(TEMP_DIR, filename)
                if os.path.getctime(filepath) < now - 3600:
                    os.remove(filepath)
            
            # تنظيف الكاش الأقدم من 24 ساعة
            for filename in os.listdir(CACHE_DIR):
                filepath = os.path.join(CACHE_DIR, filename)
                if os.path.getctime(filepath) < now - 86400:
                    os.remove(filepath)
        except:
            pass

# ==================== خدمات PDF ====================

class PDFService:
    def __init__(self):
        self.font_path = None
    
    def prepare_arabic_text(self, text: str) -> str:
        """تجهيز النص العربي للعرض في PDF"""
        try:
            # إعادة تشكيل الحروف العربية
            reshaped_text = arabic_reshaper.reshape(text)
            # ضبط اتجاه النص
            bidi_text = get_display(reshaped_text)
            return bidi_text
        except:
            return text
    
    def create_pdf(self, content: str, title: str, author: str = "بوت الكتب الذكي") -> str:
        """إنشاء ملف PDF من النص"""
        
        class ArabicPDF(FPDF):
            def __init__(self):
                super().__init__()
                self.add_font('Arial', '', 'arial.ttf', uni=True)
            
            def header(self):
                self.set_font('Arial', 'B', 16)
                self.cell(0, 10, self.title, 0, 1, 'C')
                self.ln(10)
            
            def footer(self):
                self.set_y(-15)
                self.set_font('Arial', 'I', 8)
                self.cell(0, 10, f'الصفحة {self.page_no()}', 0, 0, 'C')
        
        # إنشاء اسم ملف فريد
        filename = f"book_{int(time.time())}_{hashlib.md5(title.encode()).hexdigest()[:8]}.pdf"
        filepath = os.path.join(BOOKS_DIR, filename)
        
        pdf = ArabicPDF()
        pdf.set_title(title)
        pdf.set_author(author)
        
        # إضافة صفحة الغلاف
        pdf.add_page()
        pdf.set_font('Arial', 'B', 20)
        pdf.cell(0, 40, '', 0, 1)
        pdf.cell(0, 20, self.prepare_arabic_text(title), 0, 1, 'C')
        pdf.set_font('Arial', 'I', 12)
        pdf.cell(0, 10, f"تأليف: {author}", 0, 1, 'C')
        pdf.cell(0, 10, datetime.now().strftime("%Y-%m-%d"), 0, 1, 'C')
        
        # تقسيم المحتوى إلى صفحات
        paragraphs = content.split('\n\n')
        current_page = 1
        current_chapter = ""
        
        for para in paragraphs:
            para = para.strip()
            if not para:
                continue
            
            # التحقق من بداية فصل جديد
            if para.startswith('#'):
                pdf.add_page()
                current_chapter = para.replace('#', '').strip()
                pdf.set_font('Arial', 'B', 14)
                pdf.cell(0, 10, self.prepare_arabic_text(current_chapter), 0, 1, 'R')
                pdf.ln(5)
                continue
            
            # كتابة النص العادي
            pdf.set_font('Arial', '', 12)
            
            # تقسيم النص الطويل إلى أسطر
            lines = para.split('\n')
            for line in lines:
                if line.strip():
                    # تجهيز النص العربي
                    text = self.prepare_arabic_text(line.strip())
                    pdf.multi_cell(0, 8, text, 0, 'R')
            
            pdf.ln(5)
        
        # حفظ الملف
        pdf.output(filepath)
        return filepath

# ==================== خدمات الذكاء الاصطناعي ====================

class AIService:
    def __init__(self, api_key: str, storage: StorageManager):
        self.client = Groq(api_key=api_key)
        self.storage = storage
    
    async def generate_book_chunk(self, prompt: str, chunk_number: int, total_chunks: int) -> str:
        """توليد جزء من الكتاب مع نظام التبريد"""
        
        system_prompt = f"""أنت كاتب محترف. هذا الجزء {chunk_number} من {total_chunks} من الكتاب.
اكتب محتوى غني ومفصل لهذا الجزء."""
        
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
    
    async def generate_full_book(self, discussion: str, topic: str, user_id: int) -> str:
        """توليد الكتاب كاملاً مع التقسيم والتبريد"""
        
        # التحقق من وجود الكتاب في الكاش
        cache_key = hashlib.md5(f"{user_id}_{topic}".encode()).hexdigest()
        cached = self.storage.get_cache(cache_key)
        if cached:
            return cached
        
        # تقسيم الكتاب إلى أجزاء
        chunks = []
        
        # الجزء الأول: الهيكل العام
        structure_prompt = f"""بناءً على المناقشة التالية حول "{topic}"،
أعطني هيكل الكتاب مع عناوين الفصول الرئيسية:

{discussion[:1000]}

المطلوب:
1. عنوان الكتاب
2. قائمة الفصول (3-5 فصول)
3. النقاط الرئيسية في كل فصل"""
        
        structure = await self.generate_book_chunk(structure_prompt, 1, 4)
        chunks.append(structure)
        
        await asyncio.sleep(COOLDOWN_BETWEEN_CHUNKS)
        
        # الجزء الثاني: المقدمة والفصل الأول
        intro_prompt = f"""اكتب المقدمة والفصل الأول من الكتاب "{topic}".
الهيكل المقترح:
{structure[:500]}

المقدمة: لماذا هذا الكتاب مهم؟
الفصل الأول: ابدأ بأهم المفاهيم مع أمثلة واقعية"""
        
        chunk2 = await self.generate_book_chunk(intro_prompt, 2, 4)
        chunks.append(chunk2)
        
        await asyncio.sleep(COOLDOWN_BETWEEN_CHUNKS)
        
        # الجزء الثالث: الفصول الوسطى
        middle_prompt = f"""اكمل الفصول الوسطى من الكتاب "{topic}".
تابع من حيث انتهينا:
{chunk2[-500:]}

أضف أمثلة عملية وحالات دراسية"""
        
        chunk3 = await self.generate_book_chunk(middle_prompt, 3, 4)
        chunks.append(chunk3)
        
        await aspońcio.sleep(COOLDOWN_BETWEEN_CHUNKS)
        
        # الجزء الرابع: الخاتمة والتوصيات
        conclusion_prompt = f"""اكتب الخاتمة والتوصيات النهائية للكتاب "{topic}".
الخاتمة: تلخيص لأهم النقاط
التوصيات: خطوات عملية للقارئ
المراجع: مصادر مقترحة"""
        
        chunk4 = await self.generate_book_chunk(conclusion_prompt, 4, 4)
        chunks.append(chunk4)
        
        # دمج الأجزاء
        full_book = "\n\n---\n\n".join(chunks)
        
        # حفظ في الكاش
        self.storage.set_cache(cache_key, full_book, ttl=3600)  # ساعة واحدة
        
        return full_book
    
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
        self.ai_service = AIService(groq_key, self.storage)
        self.pdf_service = PDFService()
        
        # إضافة المشرف الرئيسي
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
• نظام تبريد للمحرك للكتب الكبيرة
• تخزين مؤقت للجلسات
• دعم كامل للغة العربية في PDF

السعر: {BOOK_PRICE} نجمة للكتاب
المستخدمون المميزون: إنشاء مجاني

الأوامر:
/start - ترحيب
/help - مساعدة
/newbook - بدء كتاب جديد
/build - إنشاء الكتاب
/balance - رصيدي
/cancel - إلغاء
"""
        await update.message.reply_text(welcome)
    
    async def help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        help_text = f"""
طريقة الاستخدام:

1 اكتب /newbook لبدء كتاب جديد
2 ناقش فكرة كتابك مع البوت
3 اكتب /build لإنشاء الكتاب
4 استلم الكتاب كملف PDF

نظام التبريد:
• الكتب الكبيرة تقسم إلى أجزاء
• كل جزء ينشأ بفاصل زمني
• تخزين مؤقت للجلسة

السعر: {BOOK_PRICE} نجمة

أوامر المشرف:
/add_free id - إضافة مستخدم مميز
/remove_free id - إزالة مستخدم مميز
/users - قائمة المستخدمين
"""
        await update.message.reply_text(help_text)
    
    async def newbook(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        
        user = self.storage.get_user(user_id)
        if user and user.is_blocked:
            await update.message.reply_text("حسابك محظور.")
            return ConversationHandler.END
        
        # إنشاء جلسة جديدة
        self.storage.create_session(user_id)
        
        await update.message.reply_text(
            "بدأنا!\n\n"
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
        
        # حفظ الموضوع من أول رسالة
        if not session.topic and len(session.messages) == 0:
            session.topic = message[:50]
        
        # حفظ رسالة المستخدم
        session.messages.append({"role": "user", "content": message})
        
        # إرسال رد
        await update.message.chat.send_action(action="typing")
        
        response = await self.ai_service.chat_response(
            message, 
            session.messages[:-1]
        )
        
        # حفظ الرد
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
        
        # إعلام المستخدم
        status = await update.message.reply_text(
            "جاري إنشاء كتابك...\n"
            "قد تستغرق العملية دقيقتين للكتب الكبيرة.\n"
            "نظام التبريد يعمل لتجنب الضغط على المحرك."
        )
        
        temp_file = None
        
        try:
            # توليد الكتاب مع نظام التبريد
            book_content = await self.ai_service.generate_full_book(
                discussion, 
                topic,
                user_id
            )
            
            # إنشاء PDF
            pdf_file = self.pdf_service.create_pdf(
                book_content,
                topic,
                user_data.first_name or "مستخدم"
            )
            
            # حفظ المسار المؤقت
            self.storage.add_temp_file(user_id, pdf_file)
            
            # تحديث إحصائيات المستخدم
            user_data.total_books += 1
            # تقدير عدد الصفحات (تقريباً)
            pages_estimate = len(book_content) // 1500 + 10
            user_data.total_pages += pages_estimate
            self.storage.save_users()
            
            # إرسال الكتاب
            await status.delete()
            
            with open(pdf_file, 'rb') as f:
                await update.message.reply_document(
                    document=f,
                    filename=f"كتاب_{topic[:30]}.pdf",
                    caption=f"تم إنشاء كتابك بنجاح!\n"
                           f"الموضوع: {topic}\n"
                           f"عدد الصفحات التقديري: {pages_estimate}\n"
                           f"إجمالي كتبك: {user_data.total_books}"
                )
            
            # تنظيف الجلسة
            self.storage.delete_session(user_id)
            
        except Exception as e:
            logger.error(f"خطأ: {e}")
            await status.edit_text(
                "حدث خطأ أثناء إنشاء الكتاب.\n"
                "الرجاء المحاولة مرة أخرى لاحقاً."
            )
    
    async def balance(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        user_data = self.storage.get_user(user_id)
        
        if not user_data:
            await update.message.reply_text("مستخدم غير مسجل")
            return
        
        role_names = {
            UserRole.ADMIN: "مشرف",
            UserRole.FREE_USER: "مستخدم مميز (مجاني)",
            UserRole.REGULAR: "مستخدم عادي"
        }
        
        text = f"""
معلومات حسابك:

الرصيد: {user_data.balance} نجمة
الدور: {role_names[user_data.role]}
الكتب المنشأة: {user_data.total_books} كتاب
إجمالي الصفحات: {user_data.total_pages} صفحة
سعر الكتاب: {BOOK_PRICE} نجمة

{'' if user_data.role in [UserRole.ADMIN, UserRole.FREE_USER] else 'تحتاج لدفع مقابل كل كتاب'}
"""
        await update.message.reply_text(text)
    
    async def cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        
        self.storage.delete_session(user_id)
        
        await update.message.reply_text(
            "تم الإلغاء.\n"
            "يمكنك بدء كتاب جديد بـ /newbook"
        )
        return ConversationHandler.END
    
    # ========== أوامر المشرف ==========
    
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
            
            await update.message.reply_text(f"تمت إضافة {target} كمستخدم مميز")
            
        except (IndexError, ValueError):
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
                await update.message.reply_text(f"تمت إزالة الصلاحية عن {target}")
            else:
                await update.message.reply_text("مستخدم غير موجود")
                
        except (IndexError, ValueError):
            await update.message.reply_text("استخدم: /remove_free user_id")
    
    async def users_list(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        
        if user_id != ADMIN_ID:
            await update.message.reply_text("غير مصرح")
            return
        
        text = "قائمة المستخدمين:\n\n"
        
        for uid, user in list(self.storage.users.items())[:20]:
            role_icon = {
                UserRole.ADMIN: "👑",
                UserRole.FREE_USER: "⭐",
                UserRole.REGULAR: "👤"
            }[user.role]
            
            block = "🔴" if user.is_blocked else "🟢"
            
            text += f"{block} {role_icon} {uid}: {user.first_name}\n"
            text += f"   الرصيد: {user.balance} | الكتب: {user.total_books}\n"
            text += f"   المستخدم: @{user.username or 'لا يوجد'}\n\n"
        
        await update.message.reply_text(text)
    
    def run(self):
        """تشغيل البوت"""
        app = Application.builder().token(self.token).build()
        
        # الأوامر الأساسية
        app.add_handler(CommandHandler("start", self.start))
        app.add_handler(CommandHandler("help", self.help))
        app.add_handler(CommandHandler("balance", self.balance))
        app.add_handler(CommandHandler("build", self.build))
        app.add_handler(CommandHandler("cancel", self.cancel))
        
        # أوامر المشرف
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
        
        # تنظيف دوري كل ساعة
        async def periodic_cleanup():
            while True:
                await asyncio.sleep(3600)
                self.storage._cleanup_old_files()
        
        asyncio.create_task(periodic_cleanup())
        
        logger.info("البوت يعمل مع نظام PDF والتبريد...")
        app.run_polling()

# ==================== التشغيل ====================

if __name__ == "__main__":
    bot = EBookBot(TELEGRAM_TOKEN, GROQ_API_KEY)
    bot.run()
