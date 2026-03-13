import logging
import json
import os
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
MAX_RETRIES = 3

# مجلدات التخزين
DATA_DIR = "bot_data"
USERS_FILE = f"{DATA_DIR}/users.json"
BOOKS_DIR = f"{DATA_DIR}/books"
TEMP_DIR = f"{DATA_DIR}/temp"

# إنشاء المجلدات
for dir_path in [DATA_DIR, BOOKS_DIR, TEMP_DIR]:
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
    created_at: str = ""
    
    def to_dict(self):
        return {
            'user_id': self.user_id,
            'username': self.username,
            'first_name': self.first_name,
            'role': self.role.value,
            'balance': self.balance,
            'is_blocked': self.is_blocked,
            'total_books': self.total_books,
            'created_at': self.created_at
        }
    
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
            created_at=data.get('created_at', datetime.now().isoformat())
        )

@dataclass
class SessionData:
    user_id: int
    messages: List[Dict]
    topic: str
    created_at: float
    
    def __init__(self, user_id: int):
        self.user_id = user_id
        self.messages = []
        self.topic = ""
        self.created_at = time.time()

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
        return self.sessions.get(user_id)
    
    def delete_session(self, user_id: int):
        if user_id in self.sessions:
            del self.sessions[user_id]
    
    def cleanup_temp_files(self):
        """تنظيف الملفات المؤقتة القديمة"""
        try:
            now = time.time()
            for filename in os.listdir(TEMP_DIR):
                filepath = os.path.join(TEMP_DIR, filename)
                if os.path.getctime(filepath) < now - 3600:  # أقدم من ساعة
                    os.remove(filepath)
        except Exception as e:
            logger.error(f"خطأ في التنظيف: {e}")

# ==================== خدمات PDF المبسطة ====================

class PDFService:
    def create_pdf(self, content: str, title: str) -> str:
        """إنشاء ملف PDF بسيط"""
        
        filename = f"book_{int(time.time())}.pdf"
        filepath = os.path.join(BOOKS_DIR, filename)
        
        pdf = FPDF()
        pdf.add_page()
        
        # العنوان
        pdf.set_font('Arial', 'B', 16)
        pdf.cell(0, 10, title[:50], 0, 1, 'C')
        pdf.ln(10)
        
        # المحتوى
        pdf.set_font('Arial', '', 12)
        
        # تقسيم النص إلى أسطر
        lines = content.split('\n')
        for line in lines:
            if line.strip():
                # قص النص الطويل
                if len(line) > 80:
                    words = line.split()
                    current_line = ""
                    for word in words:
                        if len(current_line + word) < 80:
                            current_line += word + " "
                        else:
                            pdf.cell(0, 10, current_line, 0, 1)
                            current_line = word + " "
                    if current_line:
                        pdf.cell(0, 10, current_line, 0, 1)
                else:
                    pdf.cell(0, 10, line, 0, 1)
        
        pdf.output(filepath)
        return filepath

# ==================== خدمات الذكاء الاصطناعي ====================

class AIService:
    def __init__(self, api_key: str):
        self.client = Groq(api_key=api_key)
    
    async def generate_full_book(self, discussion: str, topic: str) -> str:
        """توليد الكتاب كاملاً"""
        
        prompt = f"""اكتب كتاباً كاملاً عن "{topic}" بناءً على هذه المناقشة:

{discussion}

المطلوب:
1. عنوان جذاب
2. مقدمة شاملة
3. 3-5 فصول
4. خاتمة

الكتاب:"""
        
        try:
            completion = self.client.chat.completions.create(
                model="openai/gpt-oss-120b",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.8,
                max_tokens=4000,
                top_p=1,
                stream=False
            )
            return completion.choices[0].message.content
            
        except Exception as e:
            logger.error(f"خطأ في توليد الكتاب: {e}")
            raise e
    
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
        
        # تسجيل المستخدم
        if user.id not in self.storage.users:
            self.storage.create_user(user.id, user.username or "", user.first_name or "")
        
        welcome = f"""
مرحباً بك في بوت صناعة الكتب الإلكترونية يا {user.first_name}

📚 الميزات:
• كتب بتنسيق PDF
• نظام تبريد للكتب الكبيرة
• تخزين مؤقت للجلسات

💰 السعر: {BOOK_PRICE} نجمة للكتاب
⭐ المستخدمون المميزون: مجاناً

📝 الأوامر:
/newbook - بدء كتاب جديد
/build - إنشاء الكتاب
/balance - رصيدي
/cancel - إلغاء
"""
        await update.message.reply_text(welcome)
    
    async def newbook(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        
        # التحقق من الحظر
        user = self.storage.get_user(user_id)
        if user and user.is_blocked:
            await update.message.reply_text("❌ حسابك محظور")
            return ConversationHandler.END
        
        # إنشاء جلسة جديدة
        self.storage.create_session(user_id)
        
        await update.message.reply_text(
            "📝 أخبرني عن فكرة كتابك:\n\n"
            "• الموضوع الرئيسي\n"
            "• الأفكار التي تريد تغطيتها\n"
            "• الجمهور المستهدف\n\n"
            "✍️ اكتب الآن، وعندما تجهز اكتب /build"
        )
        
        return DISCUSSION
    
    async def discuss(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        message = update.message.text
        
        session = self.storage.get_session(user_id)
        if not session:
            await update.message.reply_text("❌ ابدأ بـ /newbook أولاً")
            return ConversationHandler.END
        
        # حفظ الموضوع من أول رسالة
        if not session.topic and len(session.messages) == 0:
            session.topic = message[:50]
        
        # حفظ رسالة المستخدم
        session.messages.append({"role": "user", "content": message})
        
        # إرسال مؤشر الكتابة
        await update.message.chat.send_action(action="typing")
        
        # الحصول على رد
        response = await self.ai_service.chat_response(
            message, 
            session.messages[:-1]
        )
        
        # حفظ الرد
        session.messages.append({"role": "assistant", "content": response})
        
        # إرسال الرد
        await update.message.reply_text(response)
        
        return DISCUSSION
    
    async def build(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        
        # التحقق من الجلسة
        session = self.storage.get_session(user_id)
        if not session or not session.messages:
            await update.message.reply_text("❌ لا توجد مناقشة. ابدأ بـ /newbook")
            return
        
        user_data = self.storage.get_user(user_id)
        if not user_data:
            await update.message.reply_text("❌ مستخدم غير مسجل")
            return
        
        topic = session.topic or "كتاب جديد"
        
        # التحقق من الصلاحية والرصيد
        can_proceed = False
        if user_data.role in [UserRole.ADMIN, UserRole.FREE_USER]:
            can_proceed = True
        elif user_data.balance >= BOOK_PRICE:
            can_proceed = True
            user_data.balance -= BOOK_PRICE
            self.storage.save_users()
        else:
            await update.message.reply_text(
                f"❌ رصيدك غير كافٍ\n"
                f"تحتاج: {BOOK_PRICE} نجمة\n"
                f"رصيدك: {user_data.balance} نجمة"
            )
            return
        
        # تجهيز المناقشة
        discussion = "\n".join([
            f"{msg['role']}: {msg['content']}"
            for msg in session.messages
        ])
        
        # إرسال رسالة الانتظار
        status_msg = await update.message.reply_text(
            "⏳ جاري إنشاء كتابك...\n"
            "قد تستغرق العملية دقيقة أو اثنتين"
        )
        
        try:
            # توليد الكتاب
            book_content = await self.ai_service.generate_full_book(discussion, topic)
            
            # تطبيق نظام التبريد (محاكاة)
            await asyncio.sleep(COOLDOWN_BETWEEN_CHUNKS)
            
            # إنشاء PDF
            pdf_file = self.pdf_service.create_pdf(book_content, topic)
            
            # تحديث إحصائيات المستخدم
            user_data.total_books += 1
            self.storage.save_users()
            
            # حذف رسالة الانتظار
            await status_msg.delete()
            
            # إرسال الملف
            with open(pdf_file, 'rb') as f:
                await update.message.reply_document(
                    document=f,
                    filename=f"كتاب_{topic[:30].replace(' ', '_')}.pdf",
                    caption=f"✅ تم إنشاء كتابك بنجاح!\n\n"
                           f"الموضوع: {topic}\n"
                           f"عدد الكتب المنشأة: {user_data.total_books}"
                )
            
            # تنظيف الملف المؤقت
            try:
                os.remove(pdf_file)
            except:
                pass
            
            # حذف الجلسة
            self.storage.delete_session(user_id)
            
            # تنظيف الملفات القديمة (مرة واحدة كل 5 كتب)
            if user_data.total_books % 5 == 0:
                self.storage.cleanup_temp_files()
            
        except Exception as e:
            logger.error(f"خطأ في إنشاء الكتاب: {e}")
            await status_msg.edit_text(
                "❌ حدث خطأ أثناء إنشاء الكتاب\n"
                "الرجاء المحاولة مرة أخرى"
            )
    
    async def balance(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        user_data = self.storage.get_user(user_id)
        
        if not user_data:
            await update.message.reply_text("❌ مستخدم غير مسجل")
            return
        
        # تحديد الدور
        role_text = {
            UserRole.ADMIN: "👑 مشرف",
            UserRole.FREE_USER: "⭐ مستخدم مميز",
            UserRole.REGULAR: "👤 مستخدم عادي"
        }.get(user_data.role, "👤 مستخدم عادي")
        
        # رسالة الرصيد
        text = f"""
💰 رصيدك: {user_data.balance} نجمة
👤 دورك: {role_text}
📚 كتبك: {user_data.total_books} كتاب
💵 سعر الكتاب: {BOOK_PRICE} نجمة
"""
        await update.message.reply_text(text)
    
    async def cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        self.storage.delete_session(user_id)
        await update.message.reply_text("✅ تم الإلغاء")
        return ConversationHandler.END
    
    # ========== أوامر المشرف ==========
    
    async def add_free(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        
        # التحقق من الصلاحية
        if user_id != ADMIN_ID:
            await update.message.reply_text("❌ غير مصرح")
            return
        
        try:
            target_id = int(context.args[0])
            
            # إنشاء المستخدم إذا لم يكن موجوداً
            if target_id not in self.storage.users:
                self.storage.create_user(target_id)
            
            # ترقية المستخدم
            self.storage.users[target_id].role = UserRole.FREE_USER
            self.storage.save_users()
            
            await update.message.reply_text(f"✅ تمت إضافة {target_id} كمستخدم مميز")
            
        except (IndexError, ValueError):
            await update.message.reply_text("❌ استخدم: /add_free user_id")
        except Exception as e:
            await update.message.reply_text(f"❌ خطأ: {e}")
    
    async def remove_free(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        
        if user_id != ADMIN_ID:
            await update.message.reply_text("❌ غير مصرح")
            return
        
        try:
            target_id = int(context.args[0])
            
            if target_id in self.storage.users:
                self.storage.users[target_id].role = UserRole.REGULAR
                self.storage.save_users()
                await update.message.reply_text(f"✅ تمت إزالة الصلاحية عن {target_id}")
            else:
                await update.message.reply_text("❌ مستخدم غير موجود")
                
        except (IndexError, ValueError):
            await update.message.reply_text("❌ استخدم: /remove_free user_id")
    
    async def users_list(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        
        if user_id != ADMIN_ID:
            await update.message.reply_text("❌ غير مصرح")
            return
        
        if not self.storage.users:
            await update.message.reply_text("📭 لا يوجد مستخدمين")
            return
        
        text = "📋 قائمة المستخدمين:\n\n"
        for uid, user in list(self.storage.users.items())[:20]:
            # أيقونة الدور
            role_icon = {
                UserRole.ADMIN: "👑",
                UserRole.FREE_USER: "⭐",
                UserRole.REGULAR: "👤"
            }.get(user.role, "👤")
            
            text += f"{role_icon} {uid}: {user.first_name}\n"
            text += f"   الرصيد: {user.balance} | الكتب: {user.total_books}\n\n"
        
        await update.message.reply_text(text)
    
    def run(self):
        """تشغيل البوت"""
        try:
            # إنشاء التطبيق
            app = Application.builder().token(self.token).build()
            
            # الأوامر الأساسية
            app.add_handler(CommandHandler("start", self.start))
            app.add_handler(CommandHandler("balance", self.balance))
            app.add_handler(CommandHandler("build", self.build))
            app.add_handler(CommandHandler("cancel", self.cancel))
            
            # أوامر المشرف
            app.add_handler(CommandHandler("add_free", self.add_free))
            app.add_handler(CommandHandler("remove_free", self.remove_free))
            app.add_handler(CommandHandler("users", self.users_list))
            
            # محادثة الكتاب
            conv_handler = ConversationHandler(
                entry_points=[CommandHandler("newbook", self.newbook)],
                states={
                    DISCUSSION: [
                        MessageHandler(filters.TEXT & ~filters.COMMAND, self.discuss)
                    ]
                },
                fallbacks=[CommandHandler("cancel", self.cancel)]
            )
            app.add_handler(conv_handler)
            
            logger.info("✅ البوت يعمل بنجاح")
            
            # تشغيل البوت
            app.run_polling()
            
        except Exception as e:
            logger.error(f"خطأ في تشغيل البوت: {e}")

# ==================== التشغيل ====================

if __name__ == "__main__":
    try:
        bot = EBookBot(TELEGRAM_TOKEN, GROQ_API_KEY)
        bot.run()
    except KeyboardInterrupt:
        logger.info("❌ تم إيقاف البوت يدوياً")
    except Exception as e:
        logger.error(f"❌ خطأ غير متوقع: {e}")
