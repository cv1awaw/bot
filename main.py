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
# Retrieve the bot token from environment variables
TOKEN = os.environ.get('BOT_TOKEN')

if not TOKEN:
    logger.error("BOT_TOKEN environment variable not set.")
    exit(1)
else:
    logger.info("BOT_TOKEN successfully retrieved.")

def is_authorized(user_id):
    return user_id in ALLOWED_USER_IDS

def parse_mcq(text):
    """
    Parses the multi-line MCQ text and returns question, options, correct option index, and explanation.

    Expected multi-line format:
        Question: [question text]
        a) [Option A]
        b) [Option B]
        c) [Option C]
        d) [Option D]
        Correct Answer: [option letter]
        Explanation: [Explanation text]

    Example:
        Question: The sacral promontory contributes to the border of which pelvic structure?
        a) Pelvic outlet
        b) Pubic arch
        c) Pelvic inlet
        d) Iliac fossa
        Correct Answer: c)
        Explanation: The sacral promontory forms part of the posterior border of the pelvic inlet.
    """
    try:
        # Split the text into lines and strip whitespace
        lines = [line.strip() for line in text.strip().split('\n') if line.strip()]
        question = ''
        options = []
        correct_option_index = None
        explanation = ''

        # Define regex patterns
        question_pattern = re.compile(r'^Question:\s*(.+)$', re.IGNORECASE)
        option_pattern = re.compile(r'^([a-dA-D])\)\s*(.+)$')
        correct_answer_pattern = re.compile(r'^Correct Answer:\s*([a-dA-D])\)?', re.IGNORECASE)
        explanation_pattern = re.compile(r'^Explanation:\s*(.+)$', re.IGNORECASE)

        for line in lines:
            # Match question
            q_match = question_pattern.match(line)
            if q_match:
                question = q_match.group(1).strip()
                continue

            # Match options
            opt_match = option_pattern.match(line)
            if opt_match:
                option_letter = opt_match.group(1).lower()
                option_text = opt_match.group(2).strip()
                options.append(option_text)
                continue

            # Match correct answer
            ca_match = correct_answer_pattern.match(line)
            if ca_match:
                correct_option_letter = ca_match.group(1).lower()
                correct_option_index = ord(correct_option_letter) - ord('a')
                continue

            # Match explanation
            ex_match = explanation_pattern.match(line)
            if ex_match:
                explanation = ex_match.group(1).strip()
                continue

        # Validate parsed data
        if not question:
            logger.warning("Question not found in the provided MCQ.")
        elif len(options) < 2:
            logger.warning("Insufficient options provided in the MCQ.")
        elif correct_option_index is None or correct_option_index >= len(options):
            logger.warning("Correct answer index is invalid.")
        else:
            # If validation passes, return the parsed components
            return question, options, correct_option_index, explanation

    except Exception as e:
        logger.error(f"Error parsing MCQ: {e}")

    # Ensure the function always returns four values
    return None, None, None, None

# Predefined messages for unauthorized users
UNAUTHORIZED_RESPONSES = [
    "@iwanna2die : leave my bot buddy",
    "@iwanna2die : I can see you here",
    "@iwanna2die : This is my bot, can you leave it?",
    "@iwanna2die : Leave my bot alone",
    "@iwanna2die : ابلع ما تكدر تستخدم البوت",
    "@iwanna2die : ما عندك وصول للبوت حبيبي",
]

# Predefined instruction message for authorized users
INSTRUCTION_MESSAGE = (
    "Please use the following multi-line format to create an MCQ:\n\n"
    "Question: The sacral promontory contributes to the border of which pelvic structure?\n"
    "a) Pelvic outlet\n"
    "b) Pubic arch\n"
    "c) Pelvic inlet\n"
    "d) Iliac fossa\n"
    "Correct Answer: c)\n"
    "Explanation: The sacral promontory forms part of the posterior border of the pelvic inlet."
)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()

    if is_authorized(user_id):
        logger.debug(f"Authorized user {user_id} sent message: {text}")
        # Parse the MCQ
        question, options, correct_option_index, explanation = parse_mcq(text)

        if question and options and correct_option_index is not None:
            # Validate lengths
            if len(question) > 300:
                logger.warning(f"Question exceeds 300 characters: {question}")
                await update.message.reply_text("The question must be under 300 characters. Please shorten your question.")
                return

            if any(len(option) > 100 for option in options):
                logger.warning(f"One or more options exceed 100 characters: {options}")
                await update.message.reply_text("Each option must be under 100 characters. Please shorten your options.")
                return

            if explanation and len(explanation) > 200:
                logger.warning(f"Explanation exceeds 200 characters: {explanation}")
                await update.message.reply_text("The explanation must be under 200 characters. Please shorten your explanation.")
                return

            # Send the poll
            try:
                await update.message.reply_poll(
                    question=question,
                    options=options,
                    type=Poll.QUIZ,
                    correct_option_id=correct_option_index,
                    explanation=explanation or None
                )
                logger.info(f"Poll sent successfully by user {user_id}: {question}")
            except Exception as e:
                logger.error(f"Error sending poll: {e}")
                await update.message.reply_text(f"Failed to send the poll. Error: {e}")
        else:
            # Invalid MCQ format; send the required format instructions
            logger.warning(f"Authorized user {user_id} sent an invalid MCQ format.")
            await update.message.reply_text(INSTRUCTION_MESSAGE)
    else:
        logger.warning(f"Unauthorized access attempt by user ID: {user_id}")
        # Select a random response from the predefined list
        response = random.choice(UNAUTHORIZED_RESPONSES)
        await update.message.reply_text(response)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if not is_authorized(user_id):
        logger.warning(f"Unauthorized access attempt by user ID: {user_id}")
        # Select a random response from the predefined list
        response = random.choice(UNAUTHORIZED_RESPONSES)
        await update.message.reply_text(response)
        return

    logger.info(f"User {user_id} initiated /start")
    await update.message.reply_text("Welcome to the MCQ Bot! Send me your MCQs in the specified multi-line format.")

def main():
    # Build the application
    application = ApplicationBuilder().token(TOKEN).build()

    # Add handlers
    application.add_handler(CommandHandler('start', start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Start the bot
    logger.info("Bot started...")
    application.run_polling()

if __name__ == '__main__':
    main()
