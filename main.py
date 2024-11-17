# main.py

import os
import logging
import re
import random
from flask import Flask, request, abort
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

# Initialize Flask App
app = Flask(__name__)

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
    try:
        question = ''
        options = []
        correct_option_index = None
        explanation = ''

        # Patterns for Shape 2 (single-line)
        shape2_pattern = re.compile(
            r'Question:\s*(.*?)\s*a\)\s*(.*?)\s*b\)\s*(.*?)\s*c\)\s*(.*?)\s*d\)\s*(.*?)\s*Correct Answer:\s*([a-dA-D])\)\s*Explanation:\s*(.*)',
            re.IGNORECASE
        )

        # Patterns for Shape 1 (multi-line)
        shape1_pattern = re.compile(
            r'Question:\s*(.*?)\s*\n*a\)\s*(.*?)\s*\n*b\)\s*(.*?)\s*\n*c\)\s*(.*?)\s*\n*d\)\s*(.*?)\s*\n*Correct Answer:\s*([a-dA-D])\)\s*\n*Explanation:\s*(.*)',
            re.IGNORECASE | re.DOTALL
        )

        # Try matching Shape 2
        match = shape2_pattern.match(text)
        if match:
            question = match.group(1).strip()
            options = [
                match.group(2).strip(),
                match.group(3).strip(),
                match.group(4).strip(),
                match.group(5).strip()
            ]
            correct_option_letter = match.group(6).lower()
            correct_option_index = ord(correct_option_letter) - ord('a')
            explanation = match.group(7).strip()
            return question, options, correct_option_index, explanation

        # Try matching Shape 1
        match = shape1_pattern.match(text)
        if match:
            question = match.group(1).strip()
            options = [
                match.group(2).strip(),
                match.group(3).strip(),
                match.group(4).strip(),
                match.group(5).strip()
            ]
            correct_option_letter = match.group(6).lower()
            correct_option_index = ord(correct_option_letter) - ord('a')
            explanation = match.group(7).strip()
            return question, options, correct_option_index, explanation

        return None, None, None, None

    except Exception as e:
        logger.error(f"Error parsing MCQ: {e}")
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
        logger.info(f"Poll sent successfully: {question}")
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

# Add Handlers to the Application
application.add_handler(CommandHandler('start', start_command))
application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))

# Define Flask Routes for Webhook
@app.route('/', methods=['GET'])
def hello_world():
    """Simple route to confirm the server is running."""
    logger.info("Received request on '/' route")
    return 'Bot is running!'

@app.route('/webhook', methods=['POST'])
def webhook():
    """Handle incoming webhook POST requests from Telegram."""
    if request.method == 'POST':
        update = Update.de_json(request.get_json(force=True), bot)
        application.update_queue.put_nowait(update)
        return 'OK', 200
    else:
        abort(403)

# Graceful Shutdown Handling
import signal

def shutdown(signum, frame):
    """Handle shutdown signals gracefully."""
    logger.info("Received shutdown signal. Shutting down gracefully...")
    os._exit(0)

signal.signal(signal.SIGINT, shutdown)
signal.signal(signal.SIGTERM, shutdown)

# Main Execution
if __name__ == '__main__':
    # Set the webhook URL from environment variables
    WEBHOOK_URL = os.environ.get('WEBHOOK_URL')  # e.g., https://yourservice.koyeb.app/webhook

    if not WEBHOOK_URL:
        logger.error("WEBHOOK_URL environment variable not set.")
        exit(1)

    # Remove any existing webhook to prevent conflicts
    bot.delete_webhook()

    # Set the new webhook
    success = bot.set_webhook(url=WEBHOOK_URL)
    if success:
        logger.info(f"Webhook set to {WEBHOOK_URL}")
    else:
        logger.error("Failed to set webhook.")
        exit(1)

    # Start the Flask app on the specified port
    port = int(os.environ.get("PORT", 8000))
    logger.info(f"Starting Flask app on port {port}")
    app.run(host='0.0.0.0', port=port)
