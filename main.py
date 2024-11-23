# main.py

import os
import logging
import re
import threading
import random
import asyncio
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
    Runs the Flask app.
    """
    port = int(os.environ.get("PORT", 8080))
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
    [Your existing parse_mcq function]
    """
    # [Parsing logic remains unchanged]

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
    """
    [Your existing handle_message function]
    """
    # [Function implementation remains unchanged]

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    [Your existing start function]
    """
    # [Function implementation remains unchanged]

def main():
    # Start Flask app in a separate thread
    flask_thread = threading.Thread(target=run_flask, name="FlaskThread")
    flask_thread.start()

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
