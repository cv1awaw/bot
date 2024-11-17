# main.py

import os
import logging
import re
import random
from telegram import Update, Poll, Bot
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    MessageHandler,
    filters,
)

from allowed_users import ALLOWED_USER_IDS

# Configure Logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Initialize Telegram Bot
TOKEN = os.environ.get('BOT_TOKEN')

if not TOKEN:
    logger.error("BOT_TOKEN environment variable not set.")
    exit(1)

bot = Bot(token=TOKEN)
application = ApplicationBuilder().token(TOKEN).build()

# Predefined Messages for Unauthorized Users
UNAUTHORIZED_MESSAGES = [
    "@iwanna2die : I can see you, leave my bot.",
    "@iwanna2die : You don't have access to my bot.",
    "@iwanna2die : Hey, this is my bot, please leave it."
]

def is_authorized(user_id):
    return user_id in ALLOWED_USER_IDS

def parse_mcq(text):
    question = ''
    options = []
    correct_option_index = None
    explanation = ''

    # Patterns for Shape 1 and Shape 2
    shape1_pattern = re.compile(
        r'Question:\s*(.*?)\s*a\)\s*(.*?)\s*b\)\s*(.*?)\s*c\)\s*(.*?)\s*d\)\s*(.*?)\s*Correct Answer:\s*([a-dA-D])\)\s*Explanation:\s*(.*)',
        re.IGNORECASE | re.DOTALL
    )
    shape2_pattern = re.compile(
        r'Question:\s*(.*?)\s*a\)\s*(.*?)\s*b\)\s*(.*?)\s*c\)\s*(.*?)\s*d\)\s*(.*?)\s*Correct Answer:\s*([a-dA-D])\)\s*Explanation:\s*(.*)',
        re.IGNORECASE | re.DOTALL
    )

    match = shape1_pattern.match(text)
    if match:
        question = match.group(1).strip()
        options = [match.group(2).strip(), match.group(3).strip(), match.group(4).strip(), match.group(5).strip()]
        correct_option_letter = match.group(6).lower()
        correct_option_index = ord(correct_option_letter) - ord('a')
        explanation = match.group(7).strip()
        return question, options, correct_option_index, explanation

    match = shape2_pattern.match(text)
    if match:
        question = match.group(1).strip()
        options = [match.group(2).strip(), match.group(3).strip(), match.group(4).strip(), match.group(5).strip()]
        correct_option_letter = match.group(6).lower()
        correct_option_index = ord(correct_option_letter) - ord('a')
        explanation = match.group(7).strip()
        return question, options, correct_option_index, explanation

    return None, None, None, None

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if not is_authorized(user_id):
        response = random.choice(UNAUTHORIZED_MESSAGES)
        await update.message.reply_text(response)
        return

    text = update.message.text
    question, options, correct_option_index, explanation = parse_mcq(text)

    if not all([question, options, correct_option_index is not None, explanation]):
        shape1_example = (
            "Please use the following MCQ format:\n\n"
            "Question: [Your question here]\n"
            "a) [Option A]\n"
            "b) [Option B]\n"
            "c) [Option C]\n"
            "d) [Option D]\n"
            "Correct Answer: [option letter]\n"
            "Explanation: [Your explanation here]"
        )
        await update.message.reply_text(shape1_example)
        return

    # Validate lengths
    if len(question) > 300:
        await update.message.reply_text("The question must be under 300 characters. Please shorten your question.")
        return
    for option in options:
        if len(option) > 100:
            await update.message.reply_text("Each option must be under 100 characters. Please shorten your options.")
            return
    if len(explanation) > 200:
        await update.message.reply_text("The explanation must be under 200 characters. Please shorten your explanation.")
        return

    try:
        await update.message.reply_poll(
            question=question,
            options=options,
            type=Poll.QUIZ,
            correct_option_id=correct_option_index,
            explanation=explanation
        )
    except Exception as e:
        logger.error(f"Error sending poll: {e}")
        await update.message.reply_text(f"Failed to send the poll. Error: {e}")

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if not is_authorized(user_id):
        response = random.choice(UNAUTHORIZED_MESSAGES)
        await update.message.reply_text(response)
        return

    await update.message.reply_text("Welcome to the MCQ Bot! Send me an MCQ in the specified format to create a poll.")

application.add_handler(CommandHandler('start', start_command))
application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))

if __name__ == '__main__':
    logger.info("Starting bot with long polling...")
    application.run_polling()
