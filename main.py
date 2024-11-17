# main.py

import os
import logging
import re
import threading
import random
import json
from flask import Flask, request
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

@app.route(f'/{TOKEN}', methods=['POST'])
async def webhook():
    update = Update.de_json(await request.get_json(force=True), application.bot)
    await application.process_update(update)
    return 'OK'

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

# ... [Include your parse_mcq and other related functions here] ...

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # [Your existing handle_message logic]
    pass

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # [Your existing start command logic]
    pass

async def run_bot():
    """
    Runs the Telegram bot. Intended to run in the main thread.
    """
    try:
        application = ApplicationBuilder().token(TOKEN).build()

        # Add handlers
        application.add_handler(CommandHandler('start', start))
        application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))

        # Set the webhook URL
        await application.bot.set_webhook(f"https://<your-koyeb-app-url>/{TOKEN}")

        # Start the webhook
        await application.run_webhook(
            listen="0.0.0.0",
            port=int(os.environ.get('PORT', 8000)),
            url_path=TOKEN,
            webhook_url=f"https://<your-koyeb-app-url>/{TOKEN}"
        )
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
    import asyncio
    asyncio.run(run_bot())
