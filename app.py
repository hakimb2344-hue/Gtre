import logging
import json
import os
from datetime import datetime
from typing import Dict, Optional
from enum import Enum

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

# ==================== الإعدادات الأساسية ====================

# إعداد التسجيل
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# التوكنات والمفاتيح (ضعها هنا مباشرة)
TELEGRAM_TOKEN = "8605364115:AAHUmg2qyAanzsjLBUEoc5dS9ECaipyRrZY"
GROQ_API_KEY = "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"
ADMIN_ID = 8443969410
BOOK_PRICE = 25  # سعر الكتاب بالنجوم

# حالات المحادثة
DISCUSSION = 1

# ==================== مجلدات التخزين ====================

DATA_DIR = "bot_data"
USERS_FILE = f"{DATA_DIR}/users.json"
BOOKS_DIR = f"{DATA_DIR}/books"

# إنشاء المجلدات
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(BOOKS_DIR, exist_ok=True)

# ==================== نماذج البيانات ====================

class UserRole(str, Enum):
    ADMIN = "admin"
    FREE_USER = "free_user"
    REGULAR = "regular"

class UserData:
    def __init__(self, user_id: int, username: str = "", first_name: str = ""):
        self.user_id = user_id
        self.username = username
        self.first_name = first_name
        self.role = UserRole.REGULAR
        self.balance = 0
        self.is_blocked = False
        self.created_at = datetime.now().isoformat()

# ==================== إدارة التخزين ====================

def load_users() -> Dict[int, UserData]:
    """تحميل المستخدمين من الملف"""
    if os.path.exists(USERS_FILE):
        try:
            with open(USERS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                users = {}
                for user_id, user_data in data.items():
                    user = UserData(int(user_id))
                    user.username = user_data.get('username', '')
                    user.first_name = user_data.get('first_name', '')
                    user.role = UserRole(user_data.get('role', 'regular'))
                    user.balance = user_data.get('balance', 0)
                    user.is_blocked = user_data.get('is_blocked', False)
                    user.created_at = user_data.get('created_at', datetime.now().isoformat())
                    users[int(user_id)] = user
                return users
        except Exception as e:
            logger.error(f"خطأ في تحميل المستخدمين: {e}")
    return {}

def save_users(users: Dict[int, UserData]):
    """حفظ المستخدمين في الملف"""
    data = {}
    for user_id, user in users.items():
        data[str(user_id)] = {
            'username': user.username,
            'first_name': user.first_name,
            'role': user.role.value,
            'balance': user.balance,
            'is_blocked': user.is_blocked,
            'created_at': user.created_at
        }
    
    with open(USERS_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ==================== خدمات الذكاء الاصطناعي ====================

class AIService:
    def __init__(self, api_key: str):
        self.client = Groq(api_key=api_key)
    
    async def generate_book(self, discussion: str) -> str:
        """توليد الكتاب بناءً على المناقشة"""
        
        prompt = f"""أنت كاتب محترف. بناءً على المناقشة التالية، قم بإنشاء كتاب كامل ومنظم:

{discussion}

المتطلبات:
- ابدأ بعنوان جذاب
- أضف مقدمة شاملة
- قسم الكتاب إلى 3-5 فصول
- كل فصل مقسم إلى أقسام فرعية
- أضف خاتمة تلخص الكتاب
- استخدم لغة عربية فصحى سلسة

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
            return f"حدث خطأ في توليد الكتاب: {str(e)}"
    
    async def chat_response(self, message: str, history: list) -> str:
        """الرد على المحادثة"""
        
        messages = [
            {"role": "system", "content": "أنت مساعد متخصص في تطوير أفكار الكتب. ناقش المستخدم بلطف وساعد في تطوير فكرته."},
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
        self.ai_service = AIService(groq_key)
        self.users = load_users()
        self.sessions = {}  # {user_id: [messages]}
        
        # إضافة المشرف الرئيسي
        if ADMIN_ID not in self.users:
            admin = UserData(ADMIN_ID, "admin", "Admin")
            admin.role = UserRole.ADMIN
            self.users[ADMIN_ID] = admin
            save_users(self.users)
    
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """أمر البدء"""
        user = update.effective_user
        
        # تسجيل المستخدم الجديد
        if user.id not in self.users:
            self.users[user.id] = UserData(
                user.id, 
                user.username or "", 
                user.first_name or ""
            )
            save_users(self.users)
        
        welcome = f"""
🎉 مرحباً بك في بوت صناعة الكتب الإلكترونية {user.first_name}!

📚 **الميزات:**
• مناقشة تفاعلية لفكرة كتابك
• إنشاء كتب متكاملة بالذكاء الاصطناعي
• حفظ الكتب بصيغة نصية

💰 **السعر:** {BOOK_PRICE} نجمة للكتاب
✨ المستخدمون المميزون: إنشاء مجاني

**الأوامر:**
/start - ترحيب
/help - مساعدة
/newbook - بدء كتاب جديد
/build - إنشاء الكتاب
/balance - رصيدي
/cancel - إلغاء
"""
        await update.message.reply_text(welcome, parse_mode='Markdown')
    
    async def help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """أمر المساعدة"""
        help_text = f"""
📚 **كيفية الاستخدام:**

1️⃣ اكتب /newbook لبدء كتاب جديد
2️⃣ ناقش فكرة كتابك مع البوت
3️⃣ اكتب /build لإنشاء الكتاب
4️⃣ استلم الكتاب كملف نصي

💰 **الدفع:** {BOOK_PRICE} نجمة لكل كتاب
✅ المستخدمون المميزون: إنشاء مجاني

**للمشرف فقط:**
/add_free id - إضافة مستخدم مميز
/remove_free id - إزالة مستخدم مميز
/users - قائمة المستخدمين
"""
        await update.message.reply_text(help_text, parse_mode='Markdown')
    
    async def newbook(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """بدء كتاب جديد"""
        user_id = update.effective_user.id
        
        # التحقق من الحظر
        if user_id in self.users and self.users[user_id].is_blocked:
            await update.message.reply_text("❌ حسابك محظور.")
            return ConversationHandler.END
        
        # بدء جلسة جديدة
        self.sessions[user_id] = []
        
        await update.message.reply_text(
            "📝 **بدأنا!**\n\n"
            "أخبرني عن فكرة كتابك:\n"
            "- الموضوع الرئيسي\n"
            "- الجمهور المستهدف\n"
            "- الأفكار الرئيسية\n\n"
            "عندما تجهز، اكتب /build",
            parse_mode='Markdown'
        )
        
        return DISCUSSION
    
    async def discuss(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالج المناقشة"""
        user_id = update.effective_user.id
        message = update.message.text
        
        # التأكد من وجود جلسة
        if user_id not in self.sessions:
            await update.message.reply_text("❌ ابدأ بـ /newbook أولاً")
            return ConversationHandler.END
        
        # حفظ الرسالة
        self.sessions[user_id].append({"role": "user", "content": message})
        
        # إرسال رد
        await update.message.chat.send_action(action="typing")
        
        response = await self.ai_service.chat_response(
            message, 
            self.sessions[user_id][:-1]
        )
        
        # حفظ الرد
        self.sessions[user_id].append({"role": "assistant", "content": response})
        
        await update.message.reply_text(response)
        
        return DISCUSSION
    
    async def build(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """بناء الكتاب"""
        user_id = update.effective_user.id
        
        # التحقق من الجلسة
        if user_id not in self.sessions or not self.sessions[user_id]:
            await update.message.reply_text("❌ لا توجد مناقشة. ابدأ بـ /newbook")
            return
        
        user_data = self.users.get(user_id)
        
        # التحقق من الصلاحية
        can_proceed = False
        if user_data.role in [UserRole.ADMIN, UserRole.FREE_USER]:
            can_proceed = True
        elif user_data.balance >= BOOK_PRICE:
            can_proceed = True
            user_data.balance -= BOOK_PRICE
            save_users(self.users)
        else:
            await update.message.reply_text(
                f"❌ رصيدك غير كافٍ. تحتاج {BOOK_PRICE} نجمة.\n"
                "تواصل مع المشرف لشحن الرصيد."
            )
            return
        
        # جمع المناقشة
        discussion = "\n".join([
            f"{'مستخدم' if msg['role'] == 'user' else 'مساعد'}: {msg['content']}"
            for msg in self.sessions[user_id]
        ])
        
        # إعلام المستخدم
        status = await update.message.reply_text(
            "🔄 **جاري إنشاء كتابك...**\n"
            "قد تستغرق العملية دقيقة.",
            parse_mode='Markdown'
        )
        
        try:
            # توليد الكتاب
            book_content = await self.ai_service.generate_book(discussion)
            
            # حفظ الكتاب
            filename = f"book_{user_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            filepath = os.path.join(BOOKS_DIR, filename)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(book_content)
            
            # إرسال الكتاب
            await status.delete()
            
            with open(filepath, 'rb') as f:
                await update.message.reply_document(
                    document=f,
                    filename=filename,
                    caption="✅ **تم إنشاء كتابك بنجاح!**",
                    parse_mode='Markdown'
                )
            
            # تنظيف
            os.remove(filepath)
            del self.sessions[user_id]
            
        except Exception as e:
            logger.error(f"خطأ: {e}")
            await status.edit_text("❌ حدث خطأ. حاول مرة أخرى.")
    
    async def balance(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """عرض الرصيد"""
        user_id = update.effective_user.id
        user_data = self.users.get(user_id)
        
        if not user_data:
            await update.message.reply_text("❌ مستخدم غير مسجل")
            return
        
        role_names = {
            UserRole.ADMIN: "👑 مشرف",
            UserRole.FREE_USER: "⭐ مميز",
            UserRole.REGULAR: "👤 عادي"
        }
        
        text = f"""
💰 **رصيدك:** {user_data.balance} نجمة
👤 **دورك:** {role_names[user_data.role]}
📚 **سعر الكتاب:** {BOOK_PRICE} نجمة
"""
        await update.message.reply_text(text, parse_mode='Markdown')
    
    async def cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """إلغاء العملية"""
        user_id = update.effective_user.id
        
        if user_id in self.sessions:
            del self.sessions[user_id]
        
        await update.message.reply_text("✅ تم الإلغاء.")
        return ConversationHandler.END
    
    # ========== أوامر المشرف ==========
    
    async def add_free(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """إضافة مستخدم مميز"""
        user_id = update.effective_user.id
        
        if user_id != ADMIN_ID:
            await update.message.reply_text("❌ غير مصرح")
            return
        
        try:
            target = int(context.args[0])
            
            if target not in self.users:
                self.users[target] = UserData(target)
            
            self.users[target].role = UserRole.FREE_USER
            save_users(self.users)
            
            await update.message.reply_text(f"✅ تمت إضافة {target} كمستخدم مميز")
            
        except (IndexError, ValueError):
            await update.message.reply_text("❌ استخدم: /add_free user_id")
    
    async def remove_free(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """إزالة مستخدم مميز"""
        user_id = update.effective_user.id
        
        if user_id != ADMIN_ID:
            await update.message.reply_text("❌ غير مصرح")
            return
        
        try:
            target = int(context.args[0])
            
            if target in self.users:
                self.users[target].role = UserRole.REGULAR
                save_users(self.users)
                await update.message.reply_text(f"✅ تمت إزالة الصلاحية عن {target}")
            else:
                await update.message.reply_text("❌ مستخدم غير موجود")
                
        except (IndexError, ValueError):
            await update.message.reply_text("❌ استخدم: /remove_free user_id")
    
    async def users_list(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """عرض المستخدمين"""
        user_id = update.effective_user.id
        
        if user_id != ADMIN_ID:
            await update.message.reply_text("❌ غير مصرح")
            return
        
        text = "📋 **المستخدمين:**\n\n"
        
        for uid, user in list(self.users.items())[:20]:
            role_icon = {
                UserRole.ADMIN: "👑",
                UserRole.FREE_USER: "⭐",
                UserRole.REGULAR: "👤"
            }[user.role]
            
            block = "🔴" if user.is_blocked else "🟢"
            
            text += f"{block} {role_icon} `{uid}`: {user.first_name}\n"
            text += f"   الرصيد: {user.balance} | @{user.username}\n\n"
        
        await update.message.reply_text(text, parse_mode='Markdown')
    
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
        
        # تشغيل البوت
        logger.info("البوت يعمل...")
        app.run_polling()

# ==================== التشغيل ====================

if __name__ == "__main__":
    bot = EBookBot(TELEGRAM_TOKEN, GROQ_API_KEY)
    bot.run()
