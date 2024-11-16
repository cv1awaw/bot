# bot.py

import logging
import re
from telegram import Update, Poll
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    MessageHandler,
    CommandHandler,
    filters,
)
from allowed_users import ALLOWED_USER_IDS

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO  # Set to INFO or DEBUG for detailed logs
)

logger = logging.getLogger(__name__)

# Your bot token from BotFather
TOKEN = "7253743900:AAFZi1boPE6wMdk0J2aYSKyae-dRNEai0ok"

def is_authorized(user_id):
    return user_id in ALLOWED_USER_IDS

def parse_mcq(text):
    """
    Parses the MCQ text and returns question, options, correct option index, and explanation.
    Assumes that the MCQ is in the following format with line breaks:

    Question: [question text]
    a) [Option A]
    b) [Option B]
    c) [Option C]
    d) [Option D]
    Correct Answer: [option letter])
    Explanation: [Explanation text]
    """
    try:
        # Split the text into lines and strip whitespace
        lines = [line.strip() for line in text.strip().split('\n') if line.strip()]
        question = ''
        options = []
        correct_option_index = None
        explanation = ''

        for line in lines:
            if line.startswith('Question:'):
                question = line[len('Question:'):].strip()
            elif re.match(r'^[a-dA-D]\)', line):
                option_text = line[2:].strip()
                options.append(option_text)
            elif line.startswith('Correct Answer:'):
                correct_answer_text = line[len('Correct Answer:'):].strip()
                # Match the option letter, possibly followed by ')'
                match = re.match(r'^([a-dA-D])\)?', correct_answer_text)
                if match:
                    correct_option_letter = match.group(1).lower()
                    correct_option_index = ord(correct_option_letter) - ord('a')
            elif line.startswith('Explanation:'):
                explanation = line[len('Explanation:'):].strip()

        if not question or not options or correct_option_index is None:
            return None, None, None, None

        return question, options, correct_option_index, explanation
    except Exception as e:
        logger.error(f"Error parsing MCQ: {e}")
        return None, None, None, None

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if not is_authorized(user_id):
        await update.message.reply_text("@iwanna2die : hey leave my bot alone")
        return

    text = update.message.text

    # Parse the MCQ
    question, options, correct_option_index, explanation = parse_mcq(text)

    if not question or not options or correct_option_index is None:
        await update.message.reply_text("Invalid MCQ format. Please check and try again.")
        return

    # Ensure options do not exceed 100 characters
    for option in options:
        if len(option) > 100:
            await update.message.reply_text("Each option must be under 100 characters. Please shorten your options.")
            return

    # Ensure question does not exceed 300 characters
    if len(question) > 300:
        await update.message.reply_text("The question must be under 300 characters. Please shorten your question.")
        return

    # Ensure explanation does not exceed 200 characters
    if explanation and len(explanation) > 200:
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
        logger.info(f"Poll sent successfully: {question}")
    except Exception as e:
        logger.error(f"Error sending poll: {e}")
        await update.message.reply_text(f"Failed to send the poll. Error: {e}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if not is_authorized(user_id):
        await update.message.reply_text("@iwanna2die : hey leave my bot alone")
        return

    await update.message.reply_text("Welcome to the MCQ Bot!")

def main():
    application = ApplicationBuilder().token(TOKEN).build()

    # Add handlers
    application.add_handler(CommandHandler('start', start))
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))

    # Start the bot
    logger.info("Bot started...")
    application.run_polling()

if __name__ == '__main__':
    main()