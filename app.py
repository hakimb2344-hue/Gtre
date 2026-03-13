import logging
import json
import os
import random
import re
from datetime import datetime
from typing import Dict, Optional, List
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

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = "8605364115:AAHUmg2qyAanzsjLBUEoc5dS9ECaipyRrZY"
GROQ_API_KEY = "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"
ADMIN_ID = 8443969410
BOOK_PRICE = 25

DISCUSSION = 1

# مجلدات التخزين
DATA_DIR = "bot_data"
USERS_FILE = f"{DATA_DIR}/users.json"
BOOKS_DIR = f"{DATA_DIR}/books"

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(BOOKS_DIR, exist_ok=True)

# ==================== أنماط الزخرفة ====================

class DecorationStyle:
    """أنماط زخرفة مختلفة للعناوين الإنجليزية"""
    
    STYLES = {
        'default': {
            'prefix': '📚 ',
            'suffix': ' 📚',
            'format': lambda x: x
        },
        'bold': {
            'prefix': '𝐁𝐨𝐨𝐤: ',
            'suffix': '',
            'format': lambda x: ''.join(chr(ord(c) + 119743) if 'A' <= c <= 'Z' or 'a' <= c <= 'z' else c for c in x)
        },
        'italic': {
            'prefix': '📖 ',
            'suffix': ' 📖',
            'format': lambda x: x.upper()
        },
        'fancy': {
            'prefix': '✨『',
            'suffix': '』✨',
            'format': lambda x: x.title()
        },
        'gothic': {
            'prefix': '𝕿𝖍𝖊 ',
            'suffix': ' 𝕭𝖔𝖔𝖐',
            'format': lambda x: ''.join(chr(ord(c) + 119795) if 'A' <= c <= 'Z' else chr(ord(c) + 119839) if 'a' <= c <= 'z' else c for c in x)
        },
        'double': {
            'prefix': '『',
            'suffix': '』',
            'format': lambda x: ''.join(chr(ord(c) + 65248) if '0' <= c <= '9' or 'A' <= c <= 'Z' or 'a' <= c <= 'z' else c for c in x)
        },
        'star': {
            'prefix': '⭐ ',
            'suffix': ' ⭐',
            'format': lambda x: x.upper()
        },
        'wavy': {
            'prefix': '〰️『',
            'suffix': '』〰️',
            'format': lambda x: x
        },
        'box': {
            'prefix': '┏━━━━━┓\n┃ ',
            'suffix': ' ┃\n┗━━━━━┛',
            'format': lambda x: x.center(15)
        },
        'arrow': {
            'prefix': '➡️ ',
            'suffix': ' ⬅️',
            'format': lambda x: x
        }
    }
    
    @classmethod
    def get_style_for_topic(cls, topic: str) -> str:
        """اختيار نمط زخرفة مناسب حسب موضوع الكتاب"""
        topic_lower = topic.lower()
        
        if any(word in topic_lower for word in ['ذكاء', 'تقنية', 'ai', 'technology', 'علم']):
            return random.choice(['bold', 'gothic', 'double'])
        elif any(word in topic_lower for word in ['حب', 'رومانسي', 'love', 'romance']):
            return random.choice(['fancy', 'italic', 'star'])
        elif any(word in topic_lower for word in ['عمل', 'نجاح', 'business', 'success']):
            return random.choice(['bold', 'box', 'arrow'])
        elif any(word in topic_lower for word in ['طفل', 'أطفال', 'kids', 'children']):
            return random.choice(['star', 'wavy', 'fancy'])
        else:
            return random.choice(list(cls.STYLES.keys()))
    
    @classmethod
    def decorate_title(cls, title: str, style_name: str = None) -> str:
        """تزيين العنوان حسب النمط المختار"""
        if not style_name:
            style_name = cls.get_style_for_topic(title)
        
        style = cls.STYLES.get(style_name, cls.STYLES['default'])
        
        # تطبيق التنسيق على النص الإنجليزي فقط
        words = title.split()
        decorated_words = []
        
        for word in words:
            if word.isascii() and word.isalpha():
                # كلمة إنجليزية - نطبق عليها الزخرفة
                decorated_words.append(style['format'](word))
            else:
                # كلمة عربية - تبقى كما هي
                decorated_words.append(word)
        
        decorated_text = ' '.join(decorated_words)
        return f"{style['prefix']}{decorated_text}{style['suffix']}"

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
        self.total_books = 0  # عدد الكتب المنشأة

# ==================== إدارة التخزين ====================

def load_users() -> Dict[int, UserData]:
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
                    user.total_books = user_data.get('total_books', 0)
                    user.created_at = user_data.get('created_at', datetime.now().isoformat())
                    users[int(user_id)] = user
                return users
        except Exception as e:
            logger.error(f"خطأ في تحميل المستخدمين: {e}")
    return {}

def save_users(users: Dict[int, UserData]):
    data = {}
    for user_id, user in users.items():
        data[str(user_id)] = {
            'username': user.username,
            'first_name': user.first_name,
            'role': user.role.value,
            'balance': user.balance,
            'is_blocked': user.is_blocked,
            'total_books': user.total_books,
            'created_at': user.created_at
        }
    
    with open(USERS_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ==================== خدمات الذكاء الاصطناعي ====================

class AIService:
    def __init__(self, api_key: str):
        self.client = Groq(api_key=api_key)
    
    async def generate_book_with_markdown(self, discussion: str, topic: str) -> str:
        """توليد الكتاب مع تنسيق Markdown"""
        
        prompt = f"""أنت كاتب محترف. بناءً على المناقشة التالية حول "{topic}"، قم بإنشاء كتاب كامل ومنظم مع استخدام تنسيق Markdown:

{discussion}

**مطلوب استخدام تنسيق Markdown كالتالي:**

# العنوان الرئيسي للكتاب (H1)
## عناوين الفصول (H2)
### عناوين الأقسام الفرعية (H3)

**للتنسيق:**
- **نص عريض** للنقاط المهمة
- *نص مائل* للمصطلحات الأجنبية
- `كود` للأمثلة التقنية
- قوائم نقطية للنقاط الرئيسية
- قوائم رقمية للخطوات
- > اقتباسات للأقوال المأثورة
- --- فواصل بين الأقسام

**هيكل الكتاب المطلوب:**
1. # عنوان جذاب للكتاب
2. ## المقدمة
3. ## الفصل الأول: [العنوان]
   - ### [عنوان القسم]
   - **نقاط مهمة** مع تنسيق
4. ## الفصل الثاني: [العنوان]
   - ### [عنوان القسم]
   - أمثلة عملية مع تنسيق
5. ## الخاتمة
6. ---
7. ## كلمات مفتاحية

الرجاء إنشاء كتاب غني بالمحتوى مع تنسيق Markdown جميل."""
        
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
        self.sessions = {}  # {user_id: {"messages": [], "topic": ""}}
        
        # إضافة المشرف الرئيسي
        if ADMIN_ID not in self.users:
            admin = UserData(ADMIN_ID, "admin", "Admin")
            admin.role = UserRole.ADMIN
            self.users[ADMIN_ID] = admin
            save_users(self.users)
    
    def extract_topic(self, messages: List[Dict]) -> str:
        """استخراج موضوع الكتاب من أول رسالة للمستخدم"""
        for msg in messages:
            if msg['role'] == 'user':
                return msg['content'][:50]  # أول 50 حرف كموضوع
        return "كتاب جديد"
    
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        
        if user.id not in self.users:
            self.users[user.id] = UserData(
                user.id, 
                user.username or "", 
                user.first_name or ""
            )
            save_users(self.users)
        
        welcome = f"""
🎉 **مرحباً بك في بوت صناعة الكتب الإلكترونية** {user.first_name}!

📚 **الميزات المتطورة:**
• ✨ **تنسيق Markdown** للكتب (عناوين، تنسيق، ألوان)
• 🎨 **زخرفة العناوين الإنجليزية** حسب موضوع الكتاب
• 💬 مناقشة تفاعلية لفكرة كتابك
• 🤖 ذكاء اصطناعي متطور لكتابة محتوى احترافي

💰 **السعر:** `{BOOK_PRICE} نجمة` للكتاب
⭐ المستخدمون المميزون: إنشاء مجاني

**الأوامر المتاحة:**
/start - ترحيب
/help - مساعدة مفصلة
/newbook - ✨ **بدء كتاب جديد** ✨
/build - إنشاء الكتاب
/balance - رصيدي
/cancel - إلغاء
"""
        await update.message.reply_text(welcome, parse_mode='Markdown')
    
    async def help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        help_text = f"""
📚 **دليل استخدام البوت المتقدم:**

**✨ الميزات الجديدة:**
• **تنسيق Markdown:** الكتب تأتي بعناوين وتنسيق احترافي
• **زخرفة إنجليزية:** العناوين الإنجليزية تُزخرف حسب الموضوع
• **معاينة فورية:** يمكنك رؤية التنسيق مباشرة

**💰 نظام الدفع:**
• سعر الكتاب: `{BOOK_PRICE} نجمة`
• المستخدمون المميزون: إنشاء مجاني ⭐
• المشرفون: صلاحية كاملة 👑

**📝 طريقة الاستخدام:**
1️⃣ اكتب `/newbook` لبدء كتاب جديد
2️⃣ ناقش فكرة كتابك بالتفصيل
3️⃣ اكتب `/build` لإنشاء الكتاب
4️⃣ استلم الكتاب بتنسيق Markdown جميل

**🎨 أمثلة على الزخرفة:**
• مواضيع تقنية: `𝐁𝐨𝐨𝐤: 𝐀𝐈 𝐆𝐮𝐢𝐝𝐞`
• مواضيع أدبية: `✨『Love Story』✨`
• مواضيع علمية: `𝕿𝖍𝖊 𝕾𝖈𝖎𝖊𝖓𝖈𝖊 𝕭𝖔𝖔𝖐`

**👑 أوامر المشرف:**
/add_free id - إضافة مستخدم مميز
/remove_free id - إزالة مستخدم مميز
/users - قائمة المستخدمين
"""
        await update.message.reply_text(help_text, parse_mode='Markdown')
    
    async def newbook(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        
        if user_id in self.users and self.users[user_id].is_blocked:
            await update.message.reply_text("❌ **عذراً، حسابك محظور.**", parse_mode='Markdown')
            return ConversationHandler.END
        
        # بدء جلسة جديدة
        self.sessions[user_id] = {"messages": [], "topic": ""}
        
        await update.message.reply_text(
            "📝 **✨ بدأنا رحلة كتاب جديد! ✨**\n\n"
            "أخبرني عن فكرة كتابك:\n"
            "• **الموضوع الرئيسي**\n"
            "• **الجمهور المستهدف**\n"
            "• **الأفكار الرئيسية**\n\n"
            "_عندما تجهز، اكتب /build_\n\n"
            "💡 **نصيحة:** كلما كانت المناقشة أعمق، كان الكتاب أفضل!",
            parse_mode='Markdown'
        )
        
        return DISCUSSION
    
    async def discuss(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        message = update.message.text
        
        if user_id not in self.sessions:
            await update.message.reply_text("❌ **ابدأ بـ /newbook أولاً**", parse_mode='Markdown')
            return ConversationHandler.END
        
        # حفظ الموضوع من أول رسالة
        if not self.sessions[user_id]["topic"] and len(self.sessions[user_id]["messages"]) == 0:
            self.sessions[user_id]["topic"] = message[:50]
        
        # حفظ رسالة المستخدم
        self.sessions[user_id]["messages"].append({"role": "user", "content": message})
        
        # إرسال رد
        await update.message.chat.send_action(action="typing")
        
        response = await self.ai_service.chat_response(
            message, 
            self.sessions[user_id]["messages"][:-1]
        )
        
        # حفظ الرد
        self.sessions[user_id]["messages"].append({"role": "assistant", "content": response})
        
        await update.message.reply_text(response)
        
        return DISCUSSION
    
    async def build(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        
        if user_id not in self.sessions or not self.sessions[user_id]["messages"]:
            await update.message.reply_text("❌ **لا توجد مناقشة. ابدأ بـ /newbook**", parse_mode='Markdown')
            return
        
        user_data = self.users.get(user_id)
        topic = self.sessions[user_id]["topic"] or "كتاب جديد"
        
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
                f"❌ **رصيدك غير كافٍ.**\n\n"
                f"تحتاج `{BOOK_PRICE} نجمة` لإنشاء كتاب.\n"
                f"رصيدك الحالي: `{user_data.balance} نجمة`\n\n"
                "تواصل مع المشرف لشحن الرصيد.",
                parse_mode='Markdown'
            )
            return
        
        # جمع المناقشة
        discussion = "\n".join([
            f"**{msg['role']}**: {msg['content']}"
            for msg in self.sessions[user_id]["messages"]
        ])
        
        # إعلام المستخدم
        status = await update.message.reply_text(
            "🔄 **✨ جاري إنشاء كتابك بتقنية Markdown... ✨**\n\n"
            "• تحليل المناقشة\n"
            "• تطبيق تنسيق Markdown\n"
            "• زخرفة العناوين الإنجليزية\n"
            "• تجهيز الملف\n\n"
            "_قد تستغرق العملية دقيقة._",
            parse_mode='Markdown'
        )
        
        try:
            # توليد الكتاب مع Markdown
            book_content = await self.ai_service.generate_book_with_markdown(discussion, topic)
            
            # زخرفة العنوان الرئيسي إذا كان إنجليزياً
            lines = book_content.split('\n')
            if lines and lines[0].startswith('# '):
                title = lines[0][2:].strip()
                # التحقق إذا كان العنوان يحتوي على إنجليزية
                if any(c.isascii() and c.isalpha() for c in title):
                    style = DecorationStyle.get_style_for_topic(topic)
                    decorated_title = DecorationStyle.decorate_title(title, style)
                    lines[0] = f'# {decorated_title}'
                    book_content = '\n'.join(lines)
            
            # إضافة تذييل مع تنسيق
            book_content += f"\n\n---\n"
            book_content += f"**📚 تم إنشاء هذا الكتاب باستخدام بوت الكتب الذكي**\n"
            book_content += f"*تاريخ الإنشاء: {datetime.now().strftime('%Y-%m-%d %H:%M')}*\n"
            book_content += f"*الموضوع: {topic}*\n"
            
            # حفظ الكتاب
            filename = f"book_{user_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
            filepath = os.path.join(BOOKS_DIR, filename)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(book_content)
            
            # تحديث عدد الكتب
            user_data.total_books += 1
            save_users(self.users)
            
            # إرسال الكتاب
            await status.delete()
            
            with open(filepath, 'rb') as f:
                await update.message.reply_document(
                    document=f,
                    filename=filename.replace('.md', '.txt'),  # تلغرام يقبل txt
                    caption=f"✅ **✨ تم إنشاء كتابك بنجاح! ✨**\n\n"
                           f"**الموضوع:** {topic}\n"
                           f"**التنسيق:** Markdown (عناوين، تنسيق)\n"
                           f"**عدد الكتب المنشأة:** {user_data.total_books}\n\n"
                           f"_ملف الكتاب بتنسيق Markdown - يمكنك فتحه بأي محرر نصوص_",
                    parse_mode='Markdown'
                )
            
            # إرسال معاينة سريعة
            preview = book_content[:500] + "..."
            await update.message.reply_text(
                f"📖 **معاينة سريعة:**\n\n{preview}",
                parse_mode='Markdown'
            )
            
            # تنظيف
            os.remove(filepath)
            del self.sessions[user_id]
            
        except Exception as e:
            logger.error(f"خطأ: {e}")
            await status.edit_text(
                "❌ **حدث خطأ أثناء إنشاء الكتاب.**\n"
                "الرجاء المحاولة مرة أخرى لاحقاً.",
                parse_mode='Markdown'
            )
    
    async def balance(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        user_data = self.users.get(user_id)
        
        if not user_data:
            await update.message.reply_text("❌ **مستخدم غير مسجل**", parse_mode='Markdown')
            return
        
        role_names = {
            UserRole.ADMIN: "👑 **مشرف**",
            UserRole.FREE_USER: "⭐ **مستخدم مميز** (إنشاء مجاني)",
            UserRole.REGULAR: "👤 **مستخدم عادي**"
        }
        
        text = f"""
💰 **معلومات حسابك:**

**الرصيد:** `{user_data.balance} نجمة`
**الدور:** {role_names[user_data.role]}
**الكتب المنشأة:** `{user_data.total_books} كتاب`
**سعر الكتاب:** `{BOOK_PRICE} نجمة`

{'✨ **لديك صلاحية إنشاء مجاني!**' if user_data.role in [UserRole.ADMIN, UserRole.FREE_USER] else ''}
"""
        await update.message.reply_text(text, parse_mode='Markdown')
    
    async def cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        
        if user_id in self.sessions:
            del self.sessions[user_id]
        
        await update.message.reply_text(
            "✅ **تم إلغاء العملية.**\n"
            "يمكنك بدء كتاب جديد بـ /newbook",
            parse_mode='Markdown'
        )
        return ConversationHandler.END
    
    # ========== أوامر المشرف ==========
    
    async def add_free(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        
        if user_id != ADMIN_ID:
            await update.message.reply_text("❌ **غير مصرح**", parse_mode='Markdown')
            return
        
        try:
            target = int(context.args[0])
            
            if target not in self.users:
                self.users[target] = UserData(target)
            
            self.users[target].role = UserRole.FREE_USER
            save_users(self.users)
            
            await update.message.reply_text(
                f"✅ **تمت إضافة المستخدم `{target}` كمستخدم مميز** ⭐",
                parse_mode='Markdown'
            )
            
        except (IndexError, ValueError):
            await update.message.reply_text(
                "❌ **استخدم:** `/add_free user_id`",
                parse_mode='Markdown'
            )
    
    async def remove_free(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        
        if user_id != ADMIN_ID:
            await update.message.reply_text("❌ **غير مصرح**", parse_mode='Markdown')
            return
        
        try:
            target = int(context.args[0])
            
            if target in self.users:
                self.users[target].role = UserRole.REGULAR
                save_users(self.users)
                await update.message.reply_text(
                    f"✅ **تمت إزالة الصلاحية عن المستخدم `{target}`**",
                    parse_mode='Markdown'
                )
            else:
                await update.message.reply_text(
                    "❌ **مستخدم غير موجود**",
                    parse_mode='Markdown'
                )
                
        except (IndexError, ValueError):
            await update.message.reply_text(
                "❌ **استخدم:** `/remove_free user_id`",
                parse_mode='Markdown'
            )
    
    async def users_list(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        
        if user_id != ADMIN_ID:
            await update.message.reply_text("❌ **غير مصرح**", parse_mode='Markdown')
            return
        
        text = "📋 **📊 قائمة المستخدمين:**\n\n"
        
        for uid, user in list(self.users.items())[:20]:
            role_icon = {
                UserRole.ADMIN: "👑",
                UserRole.FREE_USER: "⭐",
                UserRole.REGULAR: "👤"
            }[user.role]
            
            block = "🔴" if user.is_blocked else "🟢"
            
            text += f"{block} {role_icon} **`{uid}`**: {user.first_name}\n"
            text += f"   ├ الرصيد: `{user.balance}` ⭐\n"
            text += f"   ├ الكتب: `{user.total_books}` 📚\n"
            text += f"   └ المستخدم: @{user.username or 'لا يوجد'}\n\n"
        
        if len(self.users) > 20:
            text += f"_...و {len(self.users) - 20} مستخدم آخر_"
        
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
        
        logger.info("✅ البوت يعمل مع ميزات Markdown والزخرفة...")
        app.run_polling()

# ==================== التشغيل ====================

if __name__ == "__main__":
    bot = EBookBot(TELEGRAM_TOKEN, GROQ_API_KEY)
    bot.run()
