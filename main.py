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

from allowed_users import ALLOWED_USER_IDS

# ----------------------
# Configure Logging
# ----------------------
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO  # يمكنك تغييرها إلى DEBUG لرؤية رسائل التصحيح
)
logger = logging.getLogger(__name__)

# تقليل إزعاج مكتبة telegram
logging.getLogger('telegram').setLevel(logging.WARNING)
logging.getLogger('telegram.ext').setLevel(logging.WARNING)

# ----------------------
# Telegram Bot Setup
# ----------------------
TOKEN = os.environ.get('BOT_TOKEN')  # تأكد من ضبط المتغير البيئي

if not TOKEN:
    logger.error("لم يتم ضبط متغير البيئة BOT_TOKEN.")
    exit(1)
else:
    logger.info("تم الحصول على BOT_TOKEN بنجاح.")

def is_authorized(user_id):
    """تحقق ما إذا كان user_id مصرحاً له باستعمال البوت."""
    return user_id in ALLOWED_USER_IDS

def parse_single_mcq(text):
    """
    تحلل نص سؤال واحد (MCQ) وتعيد:
        (question, options, correct_option_index, explanation)
    أو تعيد (None, None, None, None) لو كان التنسيق خاطئ.

    مثال تنسيق صحيح لسؤال واحد:
        Question: نص السؤال
        A) خيار أول
        B) خيار ثاني
        C) خيار ثالث
        Correct Answer: B
        Explanation: شرح مختصر

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

        # التحقق من صحة البارسينغ
        if not question:
            logger.warning("لم يتم العثور على سؤال (Question:) في MCQ.")
            return None, None, None, None

        if len(options) < 2:
            logger.warning("يجب توفير خيارين على الأقل.")
            return None, None, None, None

        if len(options) > 10:
            logger.warning("تجاوز عدد الخيارات 10 (هذا حد تيليجرام).")
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
    تحلل نصاً كاملاً يمكن أن يحوي عدّة أسئلة.

    الفاصل الأساسي هو سطر يبدأ بـ "Question:".
    كل الأسطر التالية لهذا العنوان تعتبر تابعة للسؤال
    إلى حين الوصول لسطر جديد يبدأ بـ "Question:" (سؤال جديد)،
    أو نهاية النص.

    تعيد قائمة من (question, options, correct_option_index, explanation).
    """
    lines = text.split('\n')

    mcq_blocks = []
    current_block = []

    # Regex لاكتشاف بداية سؤال
    question_header_pattern = re.compile(r'^Question:\s*(.+)$', re.IGNORECASE)

    for line in lines:
        # لو كان السطر يبدأ بـ "Question:"
        # فهذا يعني بداية سؤال جديد
        if question_header_pattern.match(line.strip()):
            # إذا لدينا بلوك سابق، نضيفه إلى القوائم
            if current_block:
                mcq_blocks.append('\n'.join(current_block))
                current_block = []
        current_block.append(line)

    # إضافة آخر بلوك إن وجد
    if current_block:
        mcq_blocks.append('\n'.join(current_block))

    parsed_questions = []
    for block in mcq_blocks:
        # نمرر كل بلوك (سؤال) للدالة parse_single_mcq
        q, opts, correct_idx, expl = parse_single_mcq(block)
        # إذا كان التنسيق صالحاً نضيفه للقائمة
        if q and opts and correct_idx is not None:
            parsed_questions.append((q, opts, correct_idx, expl))
        else:
            logger.warning("اكتُشِف بلوك غير صالح أو غير مكتمل (سيتم تجاهله).")

    return parsed_questions

UNAUTHORIZED_RESPONSES = [
    "@iwanna2die : leave my bot buddy",
    "@iwanna2die : I can see you here",
    "@iwanna2die : This is my bot, can you leave it?",
    "@iwanna2die : Leave my bot alone",
    "@iwanna2die : ابلع ما تكدر تستخدم البوت",
    "@iwanna2die : ما عندك وصول للبوت حبيبي",
]

INSTRUCTION_MESSAGE = (
    "أرسل أسئلتك بالصيغة التالية (يمكنك وضع أكثر من سؤال في رسالة واحدة):\n\n"
    "Question: نص السؤال الأول\n"
    "A) خيار أول\n"
    "B) خيار ثاني\n"
    "C) خيار ثالث\n"
    "Correct Answer: B\n"
    "Explanation: شرح مختصر حول الإجابة الصحيحة.\n\n"
    "Question: نص السؤال الثاني\n"
    "A) خيار أول\n"
    "B) خيار ثاني\n"
    "C) خيار ثالث\n"
    "D) خيار رابع\n"
    "Correct Answer: D\n"
    "Explanation: الشرح.\n\n"
    "• يجب الانتباه للآتي:\n"
    "  - أقصى عدد للخيارات هو 10 (A-J).\n"
    "  - يجب ألا يتجاوز طول السؤال 300 حرف.\n"
    "  - كل خيار تحت 100 حرف.\n"
    "  - الشرح تحت 200 حرف.\n"
)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()

    if is_authorized(user_id):
        # حلّل النص للبحث عن أسئلة متعددة
        mcqs = parse_multiple_mcqs(text)

        if not mcqs:
            # لم يتم التعرف على أي سؤال بصيغة صحيحة
            await update.message.reply_text(INSTRUCTION_MESSAGE)
            return

        # لكل سؤال مستقل، نرسل استفتاء (Poll)
        for (question, options, correct_option_index, explanation) in mcqs:
            # التحقق من أطوال النصوص
            if len(question) > 300:
                logger.warning(f"سؤال تجاوز 300 حرف: {question}")
                await update.message.reply_text("السؤال يجب أن يكون أقل من 300 حرف.")
                continue

            if any(len(option) > 100 for option in options):
                logger.warning(f"أحد الخيارات تجاوز 100 حرف: {options}")
                await update.message.reply_text("كل خيار يجب أن يكون أقل من 100 حرف.")
                continue

            if explanation and len(explanation) > 200:
                logger.warning(f"الشرح تجاوز 200 حرف: {explanation}")
                await update.message.reply_text("الشرح يجب أن يكون أقل من 200 حرف.")
                continue

            # نرسل الاستفتاء
            try:
                await update.message.reply_poll(
                    question=question,
                    options=options,
                    type=Poll.QUIZ,
                    correct_option_id=correct_option_index,
                    explanation=explanation or None
                )
                logger.info(f"تم إرسال الاستفتاء بنجاح بواسطة {user_id}: {question}")
            except Exception as e:
                logger.error(f"خطأ أثناء إرسال الاستفتاء: {e}")
                await update.message.reply_text(f"فشل إرسال الاستفتاء. السبب: {e}")

    else:
        # مستخدم غير مصرح
        logger.warning(f"Unauthorized access attempt by user ID: {user_id}")
        response = random.choice(UNAUTHORIZED_RESPONSES)
        await update.message.reply_text(response)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if not is_authorized(user_id):
        logger.warning(f"Unauthorized access attempt by user ID: {user_id}")
        response = random.choice(UNAUTHORIZED_RESPONSES)
        await update.message.reply_text(response)
        return

    logger.info(f"User {user_id} initiated /start")
    await update.message.reply_text(
        "مرحباً بك في بوت الأسئلة (MCQ Bot)!\n\n"
        "أرسل أسئلتك بالصيغة المتعددة كما هو موضّح في المثال.\n\n"
        f"{INSTRUCTION_MESSAGE}"
    )

def main():
    application = ApplicationBuilder().token(TOKEN).build()

    # الأوامر والمعالجات
    application.add_handler(CommandHandler('start', start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Bot started...")
    application.run_polling()

if __name__ == '__main__':
    main()
