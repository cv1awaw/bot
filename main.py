# main.py

import os
import logging
import re
import threading
import random  # Added for random message selection
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
    Parses the MCQ text and returns question, options, correct option index, and explanation.
    Supports both Shape 1 (multi-line) and Shape 2 (single-line) formats.
    
    Shape 1:
    
    Question: [question text]
    a) [Option A]
    b) [Option B]
    c) [Option C]
    d) [Option D]
    Correct Answer: [option letter]
    Explanation: [Explanation text]
    
    Shape 2:
    
    Question: [question text] a) [Option A] b) [Option B] c) [Option C] d) [Option D] Correct Answer: [option letter] Explanation: [Explanation text]
    """
    try:
        # Determine if the text is multi-line or single-line
        if '\n' in text.strip():
            lines = [line.strip() for line in text.strip().split('\n') if line.strip()]
        else:
            # Split by space but keep option letters with their texts
            # Use regex to split at option letters
            pattern = r'(a\)|b\)|c\)|d\))'
            parts = re.split(pattern, text)
            # Reconstruct lines
            lines = []
            for i in range(0, len(parts)-1, 2):
                prefix = parts[i].strip()
                option = parts[i+1].strip()
                if prefix.lower() in ['a)', 'b)', 'c)', 'd)']:
                    lines.append(f"{prefix} {option}")
                else:
                    # Handle other lines like Question, Correct Answer, Explanation
                    # Split based on known prefixes
                    sub_parts = re.split(r'(Question:|Correct Answer:|Explanation:)', prefix)
                    # Remove empty strings
                    sub_parts = [sp for sp in sub_parts if sp]
                    for j in range(0, len(sub_parts)-1, 2):
                        key = sub_parts[j]
                        value = sub_parts[j+1].strip()
                        lines.append(f"{key} {value}")
            # Check if the last part is Explanation or similar
            if len(parts) % 2 != 0 and parts[-1].strip():
                lines.append(parts[-1].strip())
        
        question = ''
        options = []
        correct_option_index = None
        explanation = ''

        for line in lines:
            if line.lower().startswith('question:'):
                question = line[len('Question:'):].strip()
            elif re.match(r'^[a-dA-D]\)', line):
                option_text = line[2:].strip()
                options.append(option_text)
            elif line.lower().startswith('correct answer:'):
                correct_answer_text = line[len('Correct Answer:'):].strip()
                # Match the option letter, possibly followed by ')'
                match = re.match(r'^([a-dA-D])\)?', correct_answer_text)
                if match:
                    correct_option_letter = match.group(1).lower()
                    correct_option_index = ord(correct_option_letter) - ord('a')
            elif line.lower().startswith('explanation:'):
                explanation = line[len('Explanation:'):].strip()

        if not question or not options or correct_option_index is None:
            return None, None, None, None

        return question, options, correct_option_index, explanation
    except Exception as e:
        logger.error(f"Error parsing MCQ: {e}")
        return None, None, None, None

# Predefined messages for unauthorized users
UNAUTHORIZED_MESSAGES = [
    "@iwanna2die : i can see u , leave my bot",
    "@iwanna2die : u don't have access to my bot",
    "@iwanna2die : hey this is my bot leave it"
]

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
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

    # Ensure options do not exceed 100 characters
    for option in options:
        if len(option) > 100:
            logger.warning(f"Option exceeds 100 characters: {option}")
            await update.message.reply_text("Each option must be under 100 characters. Please shorten your options.")
            return

    # Ensure question does not exceed 300 characters
    if len(question) > 300:
        logger.warning(f"Question exceeds 300 characters: {question}")
        await update.message.reply_text("The question must be under 300 characters. Please shorten your question.")
        return

    # Ensure explanation does not exceed 200 characters
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

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if not is_authorized(user_id):
        logger.warning(f"Unauthorized access attempt by user ID: {user_id}")
        response = random.choice(UNAUTHORIZED_MESSAGES)
        await update.message.reply_text(response)
        return

    logger.info(f"User {user_id} initiated /start")
    await update.message.reply_text("Welcome to the MCQ Bot!")

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
