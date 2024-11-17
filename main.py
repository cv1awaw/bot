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
    Parses the single-line MCQ text and returns question, options, correct option index, and explanation.
    
    Expected format:
    Question: [question text] a) [Option A] b) [Option B] c) [Option C] d) [Option D] Correct Answer: [option letter] Explanation: [Explanation text]
    
    Example:
    Question: The sacral promontory contributes to the border of which pelvic structure? a) Pelvic outlet b) Pubic arch c) Pelvic inlet d) Iliac fossa Correct Answer: c) Explanation: The sacral promontory forms part of the posterior border of the pelvic inlet.
    """
    try:
        question = ''
        options = []
        correct_option_index = None
        explanation = ''

        # Extract the question
        question_match = re.search(r'Question:\s*(.*?)\s*(?=a\))', text, re.IGNORECASE)
        if question_match:
            question = question_match.group(1).strip()

        # Extract the options
        options = re.findall(r'[a-dA-D]\)\s*([^a-dA-D\)]+)', text)
        options = [option.strip() for option in options]

        # Extract the correct answer letter
        correct_answer_match = re.search(r'Correct Answer:\s*([a-dA-D])\)?', text, re.IGNORECASE)
        if correct_answer_match:
            correct_option_letter = correct_answer_match.group(1).lower()
            correct_option_index = ord(correct_option_letter) - ord('a')

        # Extract the explanation
        explanation_match = re.search(r'Explanation:\s*(.*)', text, re.IGNORECASE)
        if explanation_match:
            explanation = explanation_match.group(1).strip()

        if not question or not options or correct_option_index is None:
            return None, None, None, None

        return question, options, correct_option_index, explanation
    except Exception as e:
        logger.error(f"Error parsing MCQ: {e}")
        return None, None, None, None

# Predefined messages for unauthorized users
UNAUTHORIZED_RESPONSES = [
    "@iwanna2die : leave my bot buddy",
    "@iwanna2die : i can see u here",
    "@iwanna2die : this is my bot can u leave it ?",
    "@iwanba2die : leave my bot alone"
]

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
            format_instructions = (
                "Please use the following single-line format to create an MCQ:\n"
                "Question: [Your question here] "
                "a) [Option A] b) [Option B] c) [Option C] d) [Option D] "
                "Correct Answer: [option letter] Explanation: [Your explanation here]"
            )
            logger.warning(f"Authorized user {user_id} sent an invalid MCQ format.")
            await update.message.reply_text(format_instructions)
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
    await update.message.reply_text("Welcome to the MCQ Bot! Send me your MCQs in the specified single-line format.")

def run_bot():
    """
    Runs the Telegram bot. Intended to run in the main thread.
    """
    try:
        application = ApplicationBuilder().token(TOKEN).build()

        # Add handlers
        application.add_handler(CommandHandler('start', start))
        application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))

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
