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

# Import your allowed users from a separate module
from allowed_users import ALLOWED_USER_IDS

# ----------------------
# Configure Logging
# ----------------------
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO  # Use DEBUG for detailed logs during troubleshooting
)
logger = logging.getLogger(__name__)

# ----------------------
# Flask App Setup
# ----------------------
app = Flask(__name__)

# ----------------------
# Initialize Telegram Bot
# ----------------------
TOKEN = os.environ.get('BOT_TOKEN')

if not TOKEN:
    logger.error("BOT_TOKEN environment variable not set.")
    exit(1)
else:
    logger.info("BOT_TOKEN successfully retrieved.")

bot = Bot(token=TOKEN)

# ----------------------
# Initialize Telegram Application
# ----------------------
application = ApplicationBuilder().token(TOKEN).build()

# ----------------------
# Predefined Messages for Unauthorized Users
# ----------------------
UNAUTHORIZED_MESSAGES = [
    "@iwanna2die : I can see you, leave my bot.",
    "@iwanna2die : You don't have access to my bot.",
    "@iwanna2die : Hey, this is my bot, please leave it."
]

def is_authorized(user_id):
    """Check if the user is authorized to interact with the bot."""
    return user_id in ALLOWED_USER_IDS

def parse_mcq(text):
    """
    Parses the MCQ text and returns question, options, correct option index, and explanation.
    Supports both Shape 1 (multi-line) and Shape 2 (single-line) formats.
    """
    try:
        # Initialize variables
        question = ''
        options = []
        correct_option_index = None
        explanation = ''

        # Regular expression patterns
        question_pattern = r'Question:\s*(.*?)\s*(?=(?:a\)|Correct Answer:|Explanation:|$))'
        option_pattern = r'([a-dA-D])\)\s*(.*?)\s*(?=[a-dA-D]\)|Correct Answer:|Explanation:|$)'
        correct_answer_pattern = r'Correct Answer:\s*([a-dA-D])\)'
        explanation_pattern = r'Explanation:\s*(.*)'

        # Extract Question
        question_match = re.search(question_pattern, text, re.IGNORECASE | re.DOTALL)
        if question_match:
            question = question_match.group(1).strip()
            logger.debug(f"Extracted Question: {question}")
        else:
            logger.warning("Question not found in the MCQ.")
            return None, None, None, None

        # Extract Options
        options_matches = re.findall(option_pattern, text, re.IGNORECASE | re.DOTALL)
        if options_matches:
            for match in options_matches:
                option_letter = match[0].lower()
                option_text = match[1].strip()
                options.append(option_text)
                logger.debug(f"Extracted Option {option_letter.upper()}: {option_text}")
        else:
            logger.warning("Options not found in the MCQ.")
            return None, None, None, None

        # Extract Correct Answer
        correct_answer_match = re.search(correct_answer_pattern, text, re.IGNORECASE)
        if correct_answer_match:
            correct_option_letter = correct_answer_match.group(1).lower()
            correct_option_index = ord(correct_option_letter) - ord('a')
            logger.debug(f"Extracted Correct Answer: {correct_option_letter.upper()}")
        else:
            logger.warning("Correct Answer not found in the MCQ.")
            return None, None, None, None

        # Extract Explanation
        explanation_match = re.search(explanation_pattern, text, re.IGNORECASE | re.DOTALL)
        if explanation_match:
            explanation = explanation_match.group(1).strip()
            logger.debug(f"Extracted Explanation: {explanation}")
        else:
            logger.info("Explanation not found in the MCQ.")

        return question, options, correct_option_index, explanation

    except Exception as e:
        logger.error(f"Error parsing MCQ: {e}")
        return None, None, None, None

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle incoming messages and create polls based on MCQ format."""
    user_id = update.effective_user.id

    if not is_authorized(user_id):
        logger.warning(f"Unauthorized access attempt by user ID: {user_id}")
        response = random.choice(UNAUTHORIZED_MESSAGES)
        await update.message.reply_text(response)
        return

    text = update.message.text

    logger.debug(f"Received message from user {user_id}: {text}")

    # Parse the MCQ
    question, options, correct_option_index, explanation = parse_mcq(text)

    if not question or not options or correct_option_index is None:
        logger.warning(f"Invalid MCQ format from user {user_id}")
        # Respond with Shape 1 format as a reference
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

    # Validate Options Length
    for option in options:
        if len(option) > 100:
            logger.warning(f"Option exceeds 100 characters: {option}")
            await update.message.reply_text("Each option must be under 100 characters. Please shorten your options.")
            return

    # Validate Question Length
    if len(question) > 300:
        logger.warning(f"Question exceeds 300 characters: {question}")
        await update.message.reply_text("The question must be under 300 characters. Please shorten your question.")
        return

    # Validate Explanation Length
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
        logger.info(f"Poll sent successfully: {question}")
    except Exception as e:
        logger.error(f"Error sending poll: {e}")
        await update.message.reply_text(f"Failed to send the poll. Error: {e}")

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /start command."""
    user_id = update.effective_user.id

    if not is_authorized(user_id):
        logger.warning(f"Unauthorized access attempt by user ID: {user_id}")
        response = random.choice(UNAUTHORIZED_MESSAGES)
        await update.message.reply_text(response)
        return

    logger.info(f"User {user_id} initiated /start")
    await update.message.reply_text("Welcome to the MCQ Bot! Send me an MCQ in the specified format to create a poll.")

# ----------------------
# Add Handlers to the Application
# ----------------------
application.add_handler(CommandHandler('start', start_command))
application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))

# ----------------------
# Define Flask Routes for Webhook
# ----------------------
@app.route('/', methods=['GET'])
def hello_world():
    """Simple route to confirm the server is running."""
    logger.info("Received request on '/' route")
    return 'unicornguardian'

@app.route('/webhook', methods=['POST'])
def webhook():
    """Handle incoming webhook POST requests from Telegram."""
    if request.method == 'POST':
        update = Update.de_json(request.get_json(force=True), bot)
        application.update_queue.put_nowait(update)
        return 'OK', 200
    else:
        abort(403)

# ----------------------
# Graceful Shutdown Handling
# ----------------------
import signal

def shutdown(signum, frame):
    """Handle shutdown signals gracefully."""
    logger.info("Received shutdown signal. Shutting down gracefully...")
    os._exit(0)

signal.signal(signal.SIGINT, shutdown)
signal.signal(signal.SIGTERM, shutdown)

# ----------------------
# Main Execution
# ----------------------
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
