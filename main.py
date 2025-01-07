import os
import logging
import re
import asyncio
import random
from telegram import Update, Poll
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    MessageHandler,
    CommandHandler,
    filters,
)

from allowed_users import ALLOWED_USER_IDS  # تأكد من وجوده وضبطه بقيم صحيحة

# ----------------------
# Configure Logging
# ----------------------
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO  # يمكنك تحويلها إلى DEBUG لرؤية رسائل أكثر تفصيلاً
)
logger = logging.getLogger(__name__)

# تقليل إزعاج مكتبة telegram
logging.getLogger('telegram').setLevel(logging.WARNING)
logging.getLogger('telegram.ext').setLevel(logging.WARNING)

# ----------------------
# Telegram Bot Setup
# ----------------------
TOKEN = os.environ.get('BOT_TOKEN')  # يجب أن تضبط متغير البيئة قبل التشغيل

if not TOKEN:
    logger.error("لم يتم ضبط متغير البيئة BOT_TOKEN.")
    exit(1)
else:
    logger.info("تم الحصول على BOT_TOKEN بنجاح.")

# ------------------------------------------------------------------------
# 1) التحقق من سماح الاستخدام (is_authorized)
# ------------------------------------------------------------------------
def is_authorized(user_id):
    """
    يتحقق إذا كان user_id موجودًا في قائمة المسموح لهم.
    عدّل allowed_users.py لتضمين معرفات المستخدمين المصرح لهم.
    """
    return user_id in ALLOWED_USER_IDS

# ------------------------------------------------------------------------
# 2) دوال المساعدة في تحليل الأسئلة
# ------------------------------------------------------------------------

def preprocess_text_for_questions(text):
    """
    يحاول إدراج سطر جديد قبل 'Question:' (أو 'question:') إذا كانت ملتصقة بكلمة سابقة.
    مثال: 
        "edema.Question: Which metal ..." 
    تتحوّل إلى:
        "edema.\nQuestion: Which metal ..."

    هذا يضمن أن parse_multiple_mcqs سيكتشف سطرًا يبدأ بـ 'Question:'.
    """
    pattern = re.compile(r'([^\n])Question:\s*', re.IGNORECASE)
    text = pattern.sub(r'\1\nQuestion: ', text)
    return text

def parse_single_mcq(text):
    """
    تحلل نص سؤال واحد (MCQ) وتعيد: (question, options, correct_option_index, explanation)
    أو تعيد (None, None, None, None) لو كان التنسيق خاطئ.

    الصيغة المتوقعة في كل سؤال:
    Question: نص السؤال
    A) خيار أول
    B) خيار ثاني
    ...
    Correct Answer: A
    Explanation: الشرح
    
    - يدعم حتى 10 خيارات (A-J).
    """
    try:
        lines = [line.strip() for line in text.strip().split('\n') if line.strip()]

        question = ''
        options = []
        correct_option_index = None
        explanation = ''

        # Regex Patterns
        question_pattern = re.compile(r'^Question:\s*(.+)$', re.IGNORECASE)
        option_pattern = re.compile(r'^([a-jA-J])\)\s*(.+)$')  # مثل A) نص أو a) نص
        correct_answer_pattern = re.compile(r'^Correct Answer:\s*([a-jA-J])\)?', re.IGNORECASE)
        explanation_pattern = re.compile(r'^Explanation:\s*(.+)$', re.IGNORECASE)

        for line in lines:
            # السؤال
            q_match = question_pattern.match(line)
            if q_match:
                question = q_match.group(1).strip()
                continue

            # الخيار
            opt_match = option_pattern.match(line)
            if opt_match:
                option_letter = opt_match.group(1).lower()  # a-j
                option_text = opt_match.group(2).strip()
                options.append(option_text)
                continue

            # الإجابة الصحيحة
            ca_match = correct_answer_pattern.match(line)
            if ca_match:
                correct_option_letter = ca_match.group(1).lower()
                correct_option_index = ord(correct_option_letter) - ord('a')
                continue

            # الشرح
            ex_match = explanation_pattern.match(line)
            if ex_match:
                explanation = ex_match.group(1).strip()
                continue

        # تحقق من سلامة البارسينغ
        if not question:
            logger.warning("لم يتم العثور على سؤال (Question:) في MCQ.")
            return None, None, None, None

        if len(options) < 2:
            logger.warning("يجب توفير خيارين على الأقل.")
            return None, None, None, None

        if len(options) > 10:
            logger.warning("تجاوز عدد الخيارات المسموح به (10).")
            return None, None, None, None

        if correct_option_index is None or correct_option_index >= len(options):
            logger.warning("الإجابة الصحيحة غير صحيحة أو خارج نطاق الخيارات.")
            return None, None, None, None

        return question, options, correct_option_index, explanation

    except Exception as e:
        logger.error(f"Error parsing single MCQ: {e}")
        return None, None, None, None

def parse_multiple_mcqs(text):
    """
    تحلل نصاً كاملاً قد يحتوي على عدة أسئلة.
    - تقسمه إلى كتل مستقلة مبنية على سطر يبدأ بـ 'Question:' (بعد المعالجة المسبقة).
    - كل كتلة تمثل سؤالاً واحداً.
    - تعيد قائمة [(question, options, correct_idx, explanation), ...].
    """
    # مرحلة المعالجة المسبقة لفصل "Question:" إن كانت ملتصقة بنقطة أو كلمة
    text = preprocess_text_for_questions(text)

    lines = text.split('\n')
    mcq_blocks = []
    current_block = []

    # Regex لاكتشاف سطر يبدأ بـ "Question:"
    question_header_pattern = re.compile(r'^Question:\s*(.+)$', re.IGNORECASE)

    for line in lines:
        # إذا اكتشفنا سطرًا جديدًا يبدأ بـ Question: فهذا يعني بداية سؤال جديد
        if question_header_pattern.match(line.strip()):
            # لو لدينا بلوك سابق، نضيفه للقائمة
            if current_block:
                mcq_blocks.append('\n'.join(current_block))
                current_block = []
        current_block.append(line)

    # إضافة آخر بلوك إذا لم يكن فارغًا
    if current_block:
        mcq_blocks.append('\n'.join(current_block))

    parsed_questions = []
    for block in mcq_blocks:
        q, opts, correct_idx, expl = parse_single_mcq(block)
        if q and opts and correct_idx is not None:
            parsed_questions.append((q, opts, correct_idx, expl))
        else:
            # بلوك لم ينجح تحليله، قد يكون تنسيقه خاطئاً
            logger.warning("اكتُشِف بلوك غير صالح أو تنسيق خاطئ. سيتم تجاهله.")

    return parsed_questions

# ------------------------------------------------------------------------
# 3) النصوص الثابتة والرسائل
# ------------------------------------------------------------------------
UNAUTHORIZED_RESPONSES = [
    "@iwanna2die : leave my bot buddy",
    "@iwanna2die : I can see you here",
    "@iwanna2die : This is my bot, can you leave it?",
    "@iwanna2die : Leave my bot alone",
    "@iwanna2die : ابلع ما تكدر تستخدم البوت",
    "@iwanna2die : ما عندك وصول للبوت حبيبي",
]

# ملاحظة: تم تحديث رسالة التعليمات لتضمين قيود التنسيق بشكل أوضح
INSTRUCTION_MESSAGE = (
    "أرسل أسئلتك بالصيغة المتعددة (MCQs) كما هو موضح أدناه. يُرجى الانتباه للتفاصيل:\n\n"
    "1) يجب أن يبدأ كل سؤال بسطر يتضمن كلمة:  Question:\n"
    "   مثال:\n"
    "   Question: نص السؤال\n"
    "   A) خيار أول\n"
    "   B) خيار ثاني\n"
    "   C) خيار ثالث\n"
    "   Correct Answer: B\n"
    "   Explanation: شرح مختصر.\n\n"
    "2) لا تكتب 'Question 1:' أو 'Question 2:'. استخدم فقط 'Question:'.\n"
    "3) لا تضف الرمز ) أو أي نص إضافي بعد حرف الإجابة في 'Correct Answer:'.\n"
    "   فقط حرف واحد مثل: A أو B أو C...\n"
    "4) يجب ألا يتجاوز طول السؤال 300 حرف.\n"
    "5) يجب ألا يتجاوز طول أي خيار 100 حرف.\n"
    "6) يجب ألا يتجاوز طول الشرح 200 حرف.\n"
    "7) أقصى عدد للخيارات: 10 (A-J).\n\n"
    "إليك مثالًا جاهزًا لإرسال عدة أسئلة دفعة واحدة:\n\n"
    "Question: ما هي عاصمة فرنسا؟\n"
    "A) برلين\n"
    "B) باريس\n"
    "C) مدريد\n"
    "Correct Answer: B\n"
    "Explanation: باريس هي عاصمة فرنسا.\n\n"
    "يمكنك إضافة سؤال آخر بنفس التنسيق في نفس الرسالة.\n"
)

# ------------------------------------------------------------------------
# 4) الدوال التي تتعامل مع التليجرام
# ------------------------------------------------------------------------
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """التعامل مع أي رسالة نصية يرسلها المستخدم (باستثناء الأوامر)."""
    user_id = update.effective_user.id
    text = update.message.text.strip()

    if is_authorized(user_id):
        # تحليل الرسالة للبحث عن أسئلة متعددة
        mcqs = parse_multiple_mcqs(text)

        if not mcqs:
            # لم يتم التعرف على أي سؤال بصيغة صحيحة
            await update.message.reply_text(INSTRUCTION_MESSAGE)
            return

        # سننشئ استفتاء (Quiz Poll) لكل سؤال
        for (question, options, correct_option_index, explanation) in mcqs:
            # التحقق من أطوال النصوص
            if len(question) > 300:
                logger.warning(f"سؤال تجاوز 300 حرف: {question}")
                await update.message.reply_text(
                    "هناك سؤال تجاوز 300 حرف. يرجى اختصاره وإعادة الإرسال."
                )
                continue

            if any(len(option) > 100 for option in options):
                logger.warning(f"أحد الخيارات تجاوز 100 حرف: {options}")
                await update.message.reply_text(
                    "أحد الخيارات تجاوز 100 حرف. يرجى اختصاره."
                )
                continue

            if explanation and len(explanation) > 200:
                logger.warning(f"الشرح تجاوز 200 حرف: {explanation}")
                await update.message.reply_text(
                    "الشرح تجاوز 200 حرف. يرجى اختصاره."
                )
                continue

            # إنشاء الاستفتاء
            try:
                await update.message.reply_poll(
                    question=question,
                    options=options,
                    type=Poll.QUIZ,
                    correct_option_id=correct_option_index,
                    explanation=explanation or None
                )
                logger.info(f"تم إرسال الاستفتاء بنجاح بواسطة المستخدم {user_id}: {question}")
            except Exception as e:
                logger.error(f"خطأ أثناء إرسال الاستفتاء: {e}")
                await update.message.reply_text(f"فشل إرسال الاستفتاء. السبب: {e}")
    else:
        # مستخدم غير مصرح
        logger.warning(f"Unauthorized access attempt by user ID: {user_id}")
        response = random.choice(UNAUTHORIZED_RESPONSES)
        await update.message.reply_text(response)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """التعامل مع أمر /start."""
    user_id = update.effective_user.id

    if not is_authorized(user_id):
        logger.warning(f"محاولة وصول غير مصرح بها من user ID: {user_id}")
        response = random.choice(UNAUTHORIZED_RESPONSES)
        await update.message.reply_text(response)
        return

    logger.info(f"User {user_id} initiated /start")
    await update.message.reply_text(
        "مرحباً بك في بوت الأسئلة (MCQ Bot)!\n\n"
        "أرسل أسئلتك بالصيغة المتعددة كما هو موضّح في المثال أدناه.\n\n"
        f"{INSTRUCTION_MESSAGE}"
    )

# ------------------------------------------------------------------------
# 5) الدالة الرئيسية لتشغيل البوت
# ------------------------------------------------------------------------
def main():
    # بناء التطبيق (البوت) باستخدام التوكن
    application = ApplicationBuilder().token(TOKEN).build()

    # ربط المعالجات
    application.add_handler(CommandHandler('start', start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # تشغيل البوت
    logger.info("Bot started... Press Ctrl+C to stop.")
    application.run_polling()

if __name__ == '__main__':
    main()
