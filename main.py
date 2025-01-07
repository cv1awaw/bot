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
    level=logging.INFO  # Set to INFO, adjust as needed
)
logger = logging.getLogger(__name__)

# Suppress verbose logs from 'telegram' libraries
logging.getLogger('telegram').setLevel(logging.WARNING)
logging.getLogger('telegram.ext').setLevel(logging.WARNING)

# ----------------------
# Telegram Bot Setup
# ----------------------
TOKEN = os.environ.get('BOT_TOKEN')

if not TOKEN:
    logger.error("BOT_TOKEN environment variable not set.")
    exit(1)
else:
    logger.info("BOT_TOKEN successfully retrieved.")

def is_authorized(user_id):
    return user_id in ALLOWED_USER_IDS

def parse_single_mcq(text):
    """
    تحلل نص سؤال واحد (MCQ) وتعيد:
        (question, options, correct_option_index, explanation)
    أو تعيد (None, None, None, None) لو كان التنسيق خاطئ.

    الصيغة المتوقعة مثلاً:
        Question: [سؤال]
        a) [خيارات]
        b) [خيارات]
        ...
        Correct Answer: a
        Explanation: نص الشرح
    """
    try:
        # شطْر النص إلى أسطر
        lines = [line.strip() for line in text.strip().split('\n') if line.strip()]

        question = ''
        options = []
        correct_option_index = None
        explanation = ''

        # أنماط Regex للبحث
        question_pattern = re.compile(r'^Question:\s*(.+)$', re.IGNORECASE)
        # حتى 10 خيارات: a-j
        option_pattern = re.compile(r'^([a-jA-J])\)\s*(.+)$')
        correct_answer_pattern = re.compile(r'^Correct Answer:\s*([a-jA-J])\)?', re.IGNORECASE)
        explanation_pattern = re.compile(r'^Explanation:\s*(.+)$', re.IGNORECASE)

        for line in lines:
            # جملة السؤال
            q_match = question_pattern.match(line)
            if q_match:
                question = q_match.group(1).strip()
                continue

            # الخيارات
            opt_match = option_pattern.match(line)
            if opt_match:
                option_letter = opt_match.group(1).lower()
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

        # تحقق من صحة البيانات
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
    تحلل نصاً كاملاً يمكن أن يحوي عدّة أسئلة MCQ.

    - تعتبر بداية سؤال جديد هو أي سطر يشبه:
        ^\d+\.\s*Question:
      أو
        ^Question:
      (للمرونة في حال كتب المستخدم 1.Question أو كتب Question مباشرة)
    - بعد أخذ كتلة السؤال، نستدعي parse_single_mcq عليها.

    تعيد قائمة من (question, options, correct_option_index, explanation)
    """
    # قسّم النص إلى أسطر
    lines = text.split('\n')

    mcq_blocks = []
    current_block = []

    # نستخدم هذا النمط لاكتشاف بداية سؤال
    # مثال: "1.Question:" أو "12.Question:" أو "Question:"
    start_question_pattern = re.compile(r'^(\d+\.\s*)?Question:\s*(.+)$', re.IGNORECASE)

    for line in lines:
        # لو اكتشفنا بداية سؤال جديد
        if start_question_pattern.match(line.strip()):
            # إذا هناك كتلة سابقة، نحفظها
            if current_block:
                mcq_blocks.append('\n'.join(current_block))
                current_block = []
        current_block.append(line)

    # أضف آخر كتلة (إن وجدت)
    if current_block:
        mcq_blocks.append('\n'.join(current_block))

    # الآن نحلل كل كتلة على حدة باستخدام parse_single_mcq
    parsed_questions = []
    for block in mcq_blocks:
        q, opts, idx, expl = parse_single_mcq(block)
        if q and opts and idx is not None:
            parsed_questions.append((q, opts, idx, expl))
        else:
            logger.warning("اكتُشِف بلوك غير صالح (سيتم تجاهله).")

    return parsed_questions

# رسائل للمستخدمين غير المصرح لهم
UNAUTHORIZED_RESPONSES = [
    "@iwanna2die : leave my bot buddy",
    "@iwanna2die : I can see you here",
    "@iwanna2die : This is my bot, can you leave it?",
    "@iwanna2die : Leave my bot alone",
    "@iwanna2die : ابلع ما تكدر تستخدم البوت",
    "@iwanna2die : ما عندك وصول للبوت حبيبي",
]

# نص التعليمات للمستخدم المصرح
INSTRUCTION_MESSAGE = (
    "اكتب أسئلتك بالصيغة التالية (يمكنك وضع أكثر من سؤال في رسالة واحدة):\n\n"
    "1.Question: The sacral promontory contributes to the border of which pelvic structure?\n"
    "a) Pelvic outlet\n"
    "b) Pubic arch\n"
    "c) Pelvic inlet\n"
    "d) Iliac fossa\n"
    "Correct Answer: c\n"
    "Explanation: The sacral promontory forms part of the posterior border of the pelvic inlet.\n\n"
    "2.Question: The term saturnism refers to toxic symptoms produced by chronic ingestion of:\n"
    "a) Lead\n"
    "b) Arsenic\n"
    "c) Cadmium\n"
    "d) Zinc\n"
    "Correct Answer: a\n"
    "Explanation: Saturnism refers to lead poisoning.\n\n"
    "مع الانتباه للشروط:\n"
    " - أقصى عدد للخيارات 10.\n"
    " - أقصى طول للسؤال 300 حرف.\n"
    " - أقصى طول للخيار 100 حرف.\n"
    " - أقصى طول للشرح 200 حرف.\n"
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

        # أنشئ استفتاءً (Poll) لكل سؤال بنجاح
        for (question, options, correct_option_index, explanation) in mcqs:
            # التحقق من الأطوال
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
        "أرسل أسئلتك بالصيغة المتعددة كما هو موضّح في المثال أدناه.\n\n"
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
