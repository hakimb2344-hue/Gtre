import asyncio
import logging
import json
import os
from datetime import datetime
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict
from enum import Enum

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
    filters
)
from groq import Groq

# ==================== التهيئة والإعدادات ====================

# إعداد التسجيل
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# التوكنات والمفاتيح
TELEGRAM_TOKEN = "8605364115:AAHUmg2qyAanzsjLBUEoc5dS9ECaipyRrZY"
GROQ_API_KEY = "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"
ADMIN_ID = 8443969410
BOOK_PRICE_STARS = 25

# حالات المحادثة
DISCUSSION, BUILDING = range(2)

# ==================== نماذج البيانات ====================

class UserRole(Enum):
    ADMIN = "admin"
    FREE_USER = "free_user"
    REGULAR = "regular"

@dataclass
class User:
    user_id: int
    username: str = ""
    first_name: str = ""
    role: UserRole = UserRole.REGULAR
    balance: int = 0
    is_blocked: bool = False
    created_at: str = ""

@dataclass
class Session:
    user_id: int
    discussion_history: List[Dict] = None
    current_book_title: str = ""
    created_at: str = ""
    
    def __post_init__(self):
        if self.discussion_history is None:
            self.discussion_history = []

@dataclass
class Book:
    id: str
    title: str
    content: str
    user_id: int
    created_at: str
    file_path: str = ""

# ==================== إدارة التخزين ====================

class Storage:
    def __init__(self):
        self.data_dir = "bot_data"
        self.users_file = f"{self.data_dir}/users.json"
        self.sessions_dir = f"{self.data_dir}/sessions"
        self.books_dir = f"{self.data_dir}/books"
        self._ensure_directories()
        self.users: Dict[int, User] = self._load_users()
        self.active_sessions: Dict[int, Session] = {}
    
    def _ensure_directories(self):
        """إنشاء المجلدات اللازمة"""
        for dir_path in [self.data_dir, self.sessions_dir, self.books_dir]:
            if not os.path.exists(dir_path):
                os.makedirs(dir_path)
    
    def _load_users(self) -> Dict[int, User]:
        """تحميل المستخدمين من الملف"""
        if os.path.exists(self.users_file):
            try:
                with open(self.users_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    users = {}
                    for user_id, user_data in data.items():
                        user = User(**user_data)
                        user.role = UserRole(user_data.get('role', 'regular'))
                        users[int(user_id)] = user
                    return users
            except:
                return {}
        return {}
    
    def save_users(self):
        """حفظ المستخدمين في الملف"""
        data = {}
        for user_id, user in self.users.items():
            user_dict = asdict(user)
            user_dict['role'] = user.role.value
            data[str(user_id)] = user_dict
        
        with open(self.users_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    def get_or_create_user(self, user_id: int, username: str = "", first_name: str = "") -> User:
        """الحصول على مستخدم أو إنشاء جديد"""
        if user_id not in self.users:
            self.users[user_id] = User(
                user_id=user_id,
                username=username,
                first_name=first_name,
                created_at=datetime.now().isoformat()
            )
            self.save_users()
        return self.users[user_id]
    
    def create_session(self, user_id: int) -> Session:
        """إنشاء جلسة جديدة لمستخدم"""
        session = Session(
            user_id=user_id,
            created_at=datetime.now().isoformat()
        )
        self.active_sessions[user_id] = session
        return session
    
    def get_session(self, user_id: int) -> Optional[Session]:
        """الحصول على جلسة المستخدم النشطة"""
        return self.active_sessions.get(user_id)
    
    def clear_session(self, user_id: int):
        """مسح جلسة المستخدم"""
        if user_id in self.active_sessions:
            del self.active_sessions[user_id]
    
    def save_book(self, book: Book):
        """حفظ كتاب في ملف"""
        file_path = f"{self.books_dir}/{book.id}.json"
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(asdict(book), f, ensure_ascii=False, indent=2)
        return file_path

# ==================== خدمات الذكاء الاصطناعي ====================

class AIService:
    def __init__(self, api_key: str):
        self.client = Groq(api_key=api_key)
    
    async def generate_book(self, discussion_history: List[Dict], user_request: str) -> str:
        """توليد الكتاب بناءً على المناقشة السابقة"""
        
        system_prompt = """أنت كاتب محترف متخصص في إنشاء الكتب الإلكترونية. 
        بناءً على المناقشة السابقة مع المستخدم، قم بإنشاء كتاب إلكتروني كامل ومنظم.
        
        متطلبات الكتاب:
        1. ابدأ بعنوان جذاب للكتاب
        2. أضف مقدمة شاملة
        3. قسم الكتاب إلى فصول (3-5 فصول)
        4. كل فصل مقسم إلى أقسام فرعية
        5. أضف خاتمة تلخص الكتاب
        6. استخدم لغة عربية فصحى سلسة
        7. اجعل المحتوى غنياً بالمعلومات والأمثلة
        8. أضف اقتباسات ملهمة إذا كان مناسباً
        
        يجب أن يكون الكتاب احترافياً وجاهزاً للنشر مباشرة."""
        
        messages = [
            {"role": "system", "content": system_prompt},
            *discussion_history[-10:],  # آخر 10 رسائل للمناقشة
            {"role": "user", "content": f"الآن قم بإنشاء الكتاب كاملاً بناءً على مناقشتنا حول: {user_request}"}
        ]
        
        try:
            completion = self.client.chat.completions.create(
                model="openai/gpt-oss-120b",
                messages=messages,
                temperature=1,
                max_tokens=8192,
                top_p=1,
                reasoning_effort="medium",
                stream=True
            )
            
            full_response = ""
            for chunk in completion:
                if chunk.choices[0].delta.content:
                    full_response += chunk.choices[0].delta.content
            
            return full_response
            
        except Exception as e:
            logger.error(f"خطأ في توليد الكتاب: {e}")
            return f"حدث خطأ في توليد الكتاب: {str(e)}"
    
    async def chat_response(self, messages: List[Dict]) -> str:
        """الرد على المحادثة العادية"""
        try:
            completion = self.client.chat.completions.create(
                model="openai/gpt-oss-120b",
                messages=messages,
                temperature=0.7,
                max_tokens=1024,
                top_p=1,
                reasoning_effort="medium",
                stream=True
            )
            
            full_response = ""
            for chunk in completion:
                if chunk.choices[0].delta.content:
                    full_response += chunk.choices[0].delta.content
            
            return full_response
            
        except Exception as e:
            logger.error(f"خطأ في الرد: {e}")
            return f"عذراً، حدث خطأ: {str(e)}"

# ==================== بوت تلغرام ====================

class EBookBot:
    def __init__(self, token: str, groq_key: str):
        self.storage = Storage()
        self.ai_service = AIService(groq_key)
        self.application = Application.builder().token(token).build()
        self._setup_handlers()
    
    def _setup_handlers(self):
        """إعداد معالجات الأوامر"""
        
        # الأوامر الأساسية
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(CommandHandler("balance", self.balance_command))
        self.application.add_handler(CommandHandler("build", self.build_command))
        self.application.add_handler(CommandHandler("cancel", self.cancel_command))
        
        # أوامر المشرف
        self.application.add_handler(CommandHandler("admin", self.admin_panel_command))
        self.application.add_handler(CommandHandler("add_free", self.add_free_user_command))
        self.application.add_handler(CommandHandler("remove_free", self.remove_free_user_command))
        self.application.add_handler(CommandHandler("users", self.list_users_command))
        
        # معالجات المحادثة
        conv_handler = ConversationHandler(
            entry_points=[CommandHandler("newbook", self.new_book_command)],
            states={
                DISCUSSION: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.discussion_handler),
                    CallbackQueryHandler(self.build_callback, pattern="^build$")
                ],
                BUILDING: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.building_handler)
                ],
            },
            fallbacks=[CommandHandler("cancel", self.cancel_command)]
        )
        self.application.add_handler(conv_handler)
        
        # معالج callback queries
        self.application.add_handler(CallbackQueryHandler(self.callback_handler))
        
        # معالج الأخطاء
        self.application.add_error_handler(self.error_handler)
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """أمر البدء"""
        user = update.effective_user
        db_user = self.storage.get_or_create_user(
            user.id, 
            user.username or "", 
            user.first_name or ""
        )
        
        welcome_message = f"""
🎉 مرحباً بك في بوت صناعة الكتب الإلكترونية! {user.first_name}

📚 هذا البوت يساعدك في إنشاء كتب إلكترونية احترافية باستخدام الذكاء الاصطناعي.

🔹 **الميزات:**
• مناقشة تفاعلية حول فكرة كتابك
• إنشاء كتب متكاملة (مقدمة، فصول، خاتمة)
• حفظ الكتب بتنسيق احترافي
• لوحة تحكم للمشرفين

🔸 **الأوامر المتاحة:**
/start - عرض هذه الرسالة
/help - مساعدة مفصلة
/newbook - بدء كتاب جديد
/build - إنشاء الكتاب (أثناء المناقشة)
/balance - عرض رصيدك
/cancel - إلغاء العملية الحالية

💰 **سعر الكتاب:** {BOOK_PRICE_STARS} نجمة
✅ المستخدمون المميزون يمكنهم إنشاء كتب مجاناً

ابدأ الآن بكتابة /newbook
"""
        await update.message.reply_text(welcome_message, parse_mode='Markdown')
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """أمر المساعدة"""
        help_text = """
📚 **دليل استخدام البوت**

**كيفية إنشاء كتاب:**
1️⃣ اكتب /newbook لبدء كتاب جديد
2️⃣ ناقش فكرة كتابك مع البوت
3️⃣ عندما تكون جاهزاً، اكتب /build
4️⃣ انتظر حتى يتم إنشاء الكتاب
5️⃣ استلم الكتاب كملف نصي

**نظام الدفع:**
• كل كتاب يكلف {BOOK_PRICE_STARS} نجمة
• يمكن شحن الرصيد عبر المشرف
• المستخدمون المميزون لديهم إنشاء مجاني

**أوامر المشرف:**
/admin - لوحة تحكم المشرف
/add_free <user_id> - إضافة مستخدم مميز
/remove_free <user_id> - إزالة مستخدم مميز
/users - عرض قائمة المستخدمين

للاستفسارات والدعم، تواصل مع المشرف.
""".format(BOOK_PRICE_STARS=BOOK_PRICE_STARS)
        
        await update.message.reply_text(help_text, parse_mode='Markdown')
    
    async def new_book_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """بدء كتاب جديد"""
        user_id = update.effective_user.id
        db_user = self.storage.get_or_create_user(user_id)
        
        # التحقق إذا كان المستخدم محظوراً
        if db_user.is_blocked:
            await update.message.reply_text("❌ عذراً، حسابك محظور من استخدام البوت.")
            return ConversationHandler.END
        
        # إنشاء جلسة جديدة
        self.storage.create_session(user_id)
        
        await update.message.reply_text(
            "📝 **بدأنا رحلة كتاب جديد!**\n\n"
            "أخبرني عن فكرة كتابك الذي ترغب في كتابته.\n"
            "يمكنك مناقشة التفاصيل: الموضوع، الفصول، الجمهور المستهدف، إلخ.\n\n"
            "عندما تكون مستعداً لإنشاء الكتاب، اكتب /build",
            parse_mode='Markdown'
        )
        
        return DISCUSSION
    
    async def discussion_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالج المناقشة"""
        user_id = update.effective_user.id
        user_message = update.message.text
        
        session = self.storage.get_session(user_id)
        if not session:
            await update.message.reply_text("❌ يرجى بدء جلسة جديدة باستخدام /newbook")
            return ConversationHandler.END
        
        # حفظ رسالة المستخدم في التاريخ
        session.discussion_history.append({
            "role": "user",
            "content": user_message
        })
        
        # إرسال مؤشر الكتابة
        await update.message.chat.send_action(action="typing")
        
        # تحضير الرسائل للذكاء الاصطناعي
        messages = [
            {"role": "system", "content": "أنت مساعد متخصص في تطوير أفكار الكتب. ناقش المستخدم حول فكرة كتابه واسأله أسئلة توضيحية لمساعدته في تطوير الفكرة."},
            *session.discussion_history[-5:]  # آخر 5 رسائل فقط للسياق
        ]
        
        # الحصول على رد من الذكاء الاصطناعي
        response = await self.ai_service.chat_response(messages)
        
        # حفظ رد المساعد
        session.discussion_history.append({
            "role": "assistant",
            "content": response
        })
        
        await update.message.reply_text(response)
        
        return DISCUSSION
    
    async def build_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """أمر بناء الكتاب"""
        user_id = update.effective_user.id
        db_user = self.storage.get_or_create_user(user_id)
        session = self.storage.get_session(user_id)
        
        if not session:
            await update.message.reply_text("❌ لا توجد جلسة نشطة. ابدأ بـ /newbook أولاً")
            return
        
        # التحقق من الصلاحية والرصيد
        can_proceed = False
        message = ""
        
        if db_user.role in [UserRole.ADMIN, UserRole.FREE_USER]:
            can_proceed = True
            message = "✅ لديك صلاحية إنشاء كتاب مجاني. جاري البدء..."
        elif db_user.balance >= BOOK_PRICE_STARS:
            can_proceed = True
            db_user.balance -= BOOK_PRICE_STARS
            self.storage.save_users()
            message = f"💰 تم خصم {BOOK_PRICE_STARS} نجمة. جاري إنشاء كتابك..."
        else:
            message = f"❌ رصيدك غير كافٍ. تحتاج {BOOK_PRICE_STARS} نجمة لإنشاء كتاب.\n"
            message += "تواصل مع المشرف لشحن رصيدك."
        
        if not can_proceed:
            await update.message.reply_text(message)
            return
        
        # إعلام المستخدم بالبدء
        status_msg = await update.message.reply_text(
            "🔄 **جاري إنشاء كتابك...**\n"
            "قد تستغرق العملية دقيقة أو اثنتين. انتظر من فضلك.",
            parse_mode='Markdown'
        )
        
        try:
            # استخراج موضوع الكتاب من المناقشة
            topic = session.discussion_history[0]['content'] if session.discussion_history else "موضوع عام"
            
            # توليد الكتاب
            book_content = await self.ai_service.generate_book(
                session.discussion_history,
                topic
            )
            
            # إنشاء كائن الكتاب
            book = Book(
                id=f"book_{user_id}_{datetime.now().timestamp()}",
                title=f"كتاب {topic[:50]}",
                content=book_content,
                user_id=user_id,
                created_at=datetime.now().isoformat()
            )
            
            # حفظ الكتاب
            file_path = self.storage.save_book(book)
            
            # إنشاء ملف نصي للإرسال
            txt_file = f"{self.storage.books_dir}/{book.id}.txt"
            with open(txt_file, 'w', encoding='utf-8') as f:
                f.write(book_content)
            
            # إرسال الكتاب للمستخدم
            await status_msg.delete()
            
            with open(txt_file, 'rb') as f:
                await update.message.reply_document(
                    document=f,
                    filename=f"{book.title}.txt",
                    caption=f"📚 **تم إنشاء كتابك بنجاح!**\n\n"
                           f"العنوان: {book.title}\n"
                           f"التاريخ: {datetime.fromisoformat(book.created_at).strftime('%Y-%m-%d %H:%M')}\n\n"
                           f"شكراً لاستخدامك بوت الكتب الإلكترونية!",
                    parse_mode='Markdown'
                )
            
            # تنظيف الملف المؤقت
            os.remove(txt_file)
            
            # مسح الجلسة المؤقتة
            self.storage.clear_session(user_id)
            
        except Exception as e:
            logger.error(f"خطأ في إنشاء الكتاب: {e}")
            await status_msg.edit_text(
                f"❌ حدث خطأ أثناء إنشاء الكتاب: {str(e)}\n"
                "يرجى المحاولة مرة أخرى لاحقاً."
            )
    
    async def build_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالج الضغط على زر البناء"""
        query = update.callback_query
        await query.answer()
        
        # استدعاء أمر البناء
        await self.build_command(update, context)
    
    async def cancel_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """إلغاء العملية الحالية"""
        user_id = update.effective_user.id
        self.storage.clear_session(user_id)
        
        await update.message.reply_text(
            "✅ تم إلغاء العملية الحالية.\n"
            "يمكنك بدء كتاب جديد بـ /newbook"
        )
        
        return ConversationHandler.END
    
    async def balance_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """عرض الرصيد"""
        user_id = update.effective_user.id
        db_user = self.storage.get_or_create_user(user_id)
        
        role_text = {
            UserRole.ADMIN: "👑 مشرف",
            UserRole.FREE_USER: "⭐ مستخدم مميز (إنشاء مجاني)",
            UserRole.REGULAR: "👤 مستخدم عادي"
        }.get(db_user.role, "👤 مستخدم عادي")
        
        balance_text = f"""
💰 **معلومات حسابك:**

**الرصيد:** {db_user.balance} نجمة
**الدور:** {role_text}
**حالة الحساب:** {'✅ نشط' if not db_user.is_blocked else '❌ محظور'}

**سعر الكتاب:** {BOOK_PRICE_STARS} نجمة
"""
        if db_user.role in [UserRole.ADMIN, UserRole.FREE_USER]:
            balance_text += "\n✨ لديك صلاحية إنشاء كتب مجانية!"
        
        await update.message.reply_text(balance_text, parse_mode='Markdown')
    
    # ========== أوامر المشرف ==========
    
    async def admin_panel_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """لوحة تحكم المشرف"""
        user_id = update.effective_user.id
        db_user = self.storage.get_or_create_user(user_id)
        
        if db_user.role != UserRole.ADMIN:
            await update.message.reply_text("❌ هذا الأمر متاح فقط للمشرفين.")
            return
        
        # إحصائيات سريعة
        total_users = len(self.storage.users)
        free_users = sum(1 for u in self.storage.users.values() if u.role == UserRole.FREE_USER)
        active_sessions = len(self.storage.active_sessions)
        
        admin_text = f"""
👑 **لوحة تحكم المشرف**

📊 **إحصائيات:**
• إجمالي المستخدمين: {total_users}
• المستخدمون المميزون: {free_users}
• الجلسات النشطة: {active_sessions}

🔧 **الأوامر:**
/add_free <user_id> - إضافة مستخدم مميز
/remove_free <user_id> - إزالة مستخدم مميز
/users - عرض قائمة المستخدمين
/block <user_id> - حظر مستخدم
/unblock <user_id> - إلغاء حظر مستخدم
/add_balance <user_id> <amount> - إضافة رصيد

💰 **سعر الكتاب الحالي:** {BOOK_PRICE_STARS} نجمة
"""
        await update.message.reply_text(admin_text, parse_mode='Markdown')
    
    async def add_free_user_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """إضافة مستخدم مميز"""
        user_id = update.effective_user.id
        db_user = self.storage.get_or_create_user(user_id)
        
        if db_user.role != UserRole.ADMIN:
            await update.message.reply_text("❌ هذا الأمر متاح فقط للمشرفين.")
            return
        
        try:
            target_id = int(context.args[0])
            if target_id in self.storage.users:
                self.storage.users[target_id].role = UserRole.FREE_USER
                self.storage.save_users()
                await update.message.reply_text(f"✅ تم تحويل المستخدم {target_id} إلى مستخدم مميز.")
            else:
                # إنشاء مستخدم جديد
                new_user = User(
                    user_id=target_id,
                    role=UserRole.FREE_USER,
                    created_at=datetime.now().isoformat()
                )
                self.storage.users[target_id] = new_user
                self.storage.save_users()
                await update.message.reply_text(f"✅ تم إنشاء مستخدم جديد {target_id} كمستخدم مميز.")
        except (IndexError, ValueError):
            await update.message.reply_text("❌ الرجاء استخدام: /add_free <user_id>")
    
    async def remove_free_user_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """إزالة مستخدم مميز"""
        user_id = update.effective_user.id
        db_user = self.storage.get_or_create_user(user_id)
        
        if db_user.role != UserRole.ADMIN:
            await update.message.reply_text("❌ هذا الأمر متاح فقط للمشرفين.")
            return
        
        try:
            target_id = int(context.args[0])
            if target_id in self.storage.users:
                if self.storage.users[target_id].role == UserRole.FREE_USER:
                    self.storage.users[target_id].role = UserRole.REGULAR
                    self.storage.save_users()
                    await update.message.reply_text(f"✅ تم إزالة الصلاحية المميزة من المستخدم {target_id}.")
                else:
                    await update.message.reply_text(f"❌ المستخدم {target_id} ليس لديه صلاحية مميزة.")
            else:
                await update.message.reply_text(f"❌ المستخدم {target_id} غير موجود.")
        except (IndexError, ValueError):
            await update.message.reply_text("❌ الرجاء استخدام: /remove_free <user_id>")
    
    async def list_users_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """عرض قائمة المستخدمين"""
        user_id = update.effective_user.id
        db_user = self.storage.get_or_create_user(user_id)
        
        if db_user.role != UserRole.ADMIN:
            await update.message.reply_text("❌ هذا الأمر متاح فقط للمشرفين.")
            return
        
        users_text = "📋 **قائمة المستخدمين:**\n\n"
        
        for uid, user in list(self.storage.users.items())[:20]:  # عرض أول 20 مستخدم فقط
            role_icon = {
                UserRole.ADMIN: "👑",
                UserRole.FREE_USER: "⭐",
                UserRole.REGULAR: "👤"
            }.get(user.role, "👤")
            
            blocked = "🔴" if user.is_blocked else "🟢"
            
            users_text += f"{blocked} {role_icon} **{user.first_name or 'بدون اسم'}** (ID: `{uid}`)\n"
            users_text += f"   الرصيد: {user.balance} ⭐ | المستخدم: @{user.username or 'لا يوجد'}\n\n"
        
        if len(self.storage.users) > 20:
            users_text += f"...و {len(self.storage.users) - 20} مستخدم آخر"
        
        await update.message.reply_text(users_text, parse_mode='Markdown')
    
    async def callback_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالج الأزرار"""
        query = update.callback_query
        await query.answer()
        
        data = query.data
        
        if data == "build":
            await self.build_command(update, context)
    
    async def error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالج الأخطاء"""
        logger.error(f"حدث خطأ: {context.error}")
        
        if update and update.effective_message:
            await update.effective_message.reply_text(
                "❌ عذراً، حدث خطأ غير متوقع. الرجاء المحاولة مرة أخرى لاحقاً."
            )
    
    def run(self):
        """تشغيل البوت"""
        logger.info("بدء تشغيل البوت...")
        
        # إضافة المشرف الرئيسي
        admin_user = self.storage.get_or_create_user(ADMIN_ID)
        admin_user.role = UserRole.ADMIN
        self.storage.save_users()
        
        self.application.run_polling(allowed_updates=Update.ALL_TYPES)

# ==================== تشغيل البوت ====================

if __name__ == "__main__":
    bot = EBookBot(TELEGRAM_TOKEN, GROQ_API_KEY)
    bot.run()
