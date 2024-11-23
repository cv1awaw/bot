# main.py

import os
import logging
import re
import threading
import random
from flask import Flask
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
    level=logging.INFO  # Change to DEBUG for more detailed logs during troubleshooting
)
logger = logging.getLogger(__name__)

# ----------------------
# Flask App Setup
# ----------------------
app = Flask(__name__)

@app.route('/')
def hello_world():
    logger.info("Received request on '/' route")
    return 'unicornguardian'

def run_flask():
    """
    Runs the Flask app. Intended to run in a separate thread.
    """
    port = int(os.environ.get("PORT", 8000))
    logger.info(f"Starting Flask app on port {port}")
    app.run(host='0.0.0.0', port=port)

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
    [Parsing logic remains unchanged]
    """
    # [Parsing logic as in your original code]

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

def run_bot():
    """
    Runs the Telegram bot. Intended to run in the main thread.
    """
    try:
        application = ApplicationBuilder().token(TOKEN).build()

        # Add handlers
        application.add_handler(CommandHandler('start', start))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

        # Start the bot
        logger.info("Bot started...")
        application.run_polling()
    except Exception as e:
        logger.error(f"Error running bot: {e}")

# ----------------------
# Graceful Shutdown Handling
# ----------------------
def shutdown(signum, frame):
    logger.info("Received shutdown signal. Shutting down gracefully...")
    os._exit(0)

import signal
signal.signal(signal.SIGINT, shutdown)
signal.signal(signal.SIGTERM, shutdown)

# ----------------------
# Main Execution
# ----------------------
if __name__ == '__main__':
    # Start Flask app in a separate thread
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()

    # Run Telegram bot in the main thread
    run_bot()
