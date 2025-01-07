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

from allowed_users import ALLOWED_USER_IDS  # Make sure it's set up properly

# ----------------------
# Configure Logging
# ----------------------
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO  # Switch to DEBUG for more detailed logs
)
logger = logging.getLogger(__name__)

# Reduce verbosity of telegram library
logging.getLogger('telegram').setLevel(logging.WARNING)
logging.getLogger('telegram.ext').setLevel(logging.WARNING)

# ----------------------
# Telegram Bot Setup
# ----------------------
TOKEN = os.environ.get('BOT_TOKEN')  # Must be set as an environment variable

if not TOKEN:
    logger.error("Environment variable BOT_TOKEN is not set.")
    exit(1)
else:
    logger.info("BOT_TOKEN acquired successfully.")

# ------------------------------------------------------------------------
# 1) Authorization Check (is_authorized)
# ------------------------------------------------------------------------
def is_authorized(user_id):
    """
    Checks whether user_id is in the list of allowed users.
    Make sure 'allowed_users.py' contains the authorized user IDs.
    """
    return user_id in ALLOWED_USER_IDS

# ------------------------------------------------------------------------
# 2) Helper Functions for Parsing Questions
# ------------------------------------------------------------------------

def preprocess_text_for_questions(text):
    """
    Inserts a newline before 'Question:' if it's stuck to a previous word.
    For example:
        "edema.Question: Which metal ..."
    becomes:
        "edema.\nQuestion: Which metal ..."

    This helps parse_multiple_mcqs detect a line starting with 'Question:'.
    """
    pattern = re.compile(r'([^\n])Question:\s*', re.IGNORECASE)
    text = pattern.sub(r'\1\nQuestion: ', text)
    return text

def parse_single_mcq(text):
    """
    Parses a single MCQ block and returns: (question, options, correct_option_index, explanation),
    or (None, None, None, None) if there's a formatting issue.

    Expected format in each question block:
    Question: <question text>
    A) first option
    B) second option
    ...
    Correct Answer: A
    Explanation: <some explanation>

    - Up to 10 options (A-J) are supported.
    """
    try:
        lines = [line.strip() for line in text.strip().split('\n') if line.strip()]

        question = ''
        options = []
        correct_option_index = None
        explanation = ''

        # Regex Patterns
        question_pattern = re.compile(r'^Question:\s*(.+)$', re.IGNORECASE)
        option_pattern = re.compile(r'^([a-jA-J])\)\s*(.+)$')  # e.g. A) text or a) text
        correct_answer_pattern = re.compile(r'^Correct Answer:\s*([a-jA-J])\)?', re.IGNORECASE)
        explanation_pattern = re.compile(r'^Explanation:\s*(.+)$', re.IGNORECASE)

        for line in lines:
            # Question
            q_match = question_pattern.match(line)
            if q_match:
                question = q_match.group(1).strip()
                continue

            # Option
            opt_match = option_pattern.match(line)
            if opt_match:
                option_letter = opt_match.group(1).lower()  # a-j
                option_text = opt_match.group(2).strip()
                options.append(option_text)
                continue

            # Correct Answer
            ca_match = correct_answer_pattern.match(line)
            if ca_match:
                correct_option_letter = ca_match.group(1).lower()
                correct_option_index = ord(correct_option_letter) - ord('a')
                continue

            # Explanation
            ex_match = explanation_pattern.match(line)
            if ex_match:
                explanation = ex_match.group(1).strip()
                continue

        # Validity checks
        if not question:
            logger.warning("No question found (missing 'Question:' line).")
            return None, None, None, None

        if len(options) < 2:
            logger.warning("At least two options are required.")
            return None, None, None, None

        if len(options) > 10:
            logger.warning("Exceeded the maximum allowed options (10).")
            return None, None, None, None

        if correct_option_index is None or correct_option_index >= len(options):
            logger.warning("Invalid or out-of-range correct answer index.")
            return None, None, None, None

        return question, options, correct_option_index, explanation

    except Exception as e:
        logger.error(f"Error parsing single MCQ: {e}")
        return None, None, None, None

def parse_multiple_mcqs(text):
    """
    Parses a text that may contain multiple questions.
    - Splits it into blocks based on a line that looks like "Question: ..." or
      "Question 1: ...", "Question #2: ...", "Q2:", "Q No. 2:", etc.
    - Each block is treated as a single question.
    - Returns a list of tuples (question, options, correct_idx, explanation).
    """

    # Preprocess "Question:" to be on its own line if previously stuck to a word
    text = preprocess_text_for_questions(text)

    lines = text.split('\n')
    mcq_blocks = []
    current_block = []

    # This pattern tries to catch multiple forms:
    # - "Question: ...", "Question 1: ...", "Question #1: ...",
    # - "Question No. 2: ...", "Q 3: ...", "Q: ..." etc.
    # We end with ":" to separate the question text.
    question_header_pattern = re.compile(
        r'^\s*(?:Question(?:\s*(?:No\.?|#)\s*\d+|\s*\d+)?|Q\s*\d+|Q)\s*:\s*(.+)$',
        re.IGNORECASE
    )

    for line in lines:
        stripped_line = line.strip()
        if question_header_pattern.match(stripped_line):
            # If there's a previous block, finalize it
            if current_block:
                mcq_blocks.append('\n'.join(current_block))
                current_block = []
        current_block.append(line)

    # Add the last block if not empty
    if current_block:
        mcq_blocks.append('\n'.join(current_block))

    parsed_questions = []
    for block in mcq_blocks:
        q, opts, correct_idx, expl = parse_single_mcq(block)
        if q and opts and correct_idx is not None:
            parsed_questions.append((q, opts, correct_idx, expl))
        else:
            # Invalid block or formatting issue
            logger.warning("Invalid block or formatting error encountered. Ignoring this block.")

    return parsed_questions

# ------------------------------------------------------------------------
# 3) Texts / Messages
# ------------------------------------------------------------------------
UNAUTHORIZED_RESPONSES = [
    "You are not authorized to use this bot.",
    "Sorry, you do not have access rights for this bot.",
    "This bot is restricted. You cannot use it.",
    "Access denied.",
    "You are not in the allowed list of users."
]

INSTRUCTION_MESSAGE = (
    "Please send your questions in the following format (multiple questions allowed in one message):\n\n"
    "Question: Your first question text\n"
    "A) First option\n"
    "B) Second option\n"
    "C) Third option\n"
    "Correct Answer: B\n"
    "Explanation: Brief explanation.\n\n"
    "Question: Your second question text\n"
    "A) First option\n"
    "B) Second option\n"
    "C) Third option\n"
    "D) Fourth option\n"
    "Correct Answer: D\n"
    "Explanation: Brief explanation.\n\n"
    "-- Important Notes --\n"
    "• Maximum number of options: 10 (A-J).\n"
    "• A question cannot exceed 300 characters.\n"
    "• Any option cannot exceed 100 characters.\n"
    "• The explanation cannot exceed 200 characters.\n"
)

# ------------------------------------------------------------------------
# 4) Telegram Handlers
# ------------------------------------------------------------------------
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles any text message (except commands)."""
    user_id = update.effective_user.id
    text = update.message.text.strip()

    if is_authorized(user_id):
        # Parse the message for multiple MCQs
        mcqs = parse_multiple_mcqs(text)

        if not mcqs:
            # Could not detect any properly formatted questions
            await update.message.reply_text(INSTRUCTION_MESSAGE)
            return

        # Create a poll for each question
        for (question, options, correct_option_index, explanation) in mcqs:
            # Check text lengths
            if len(question) > 300:
                logger.warning(f"Question exceeds 300 characters: {question}")
                await update.message.reply_text(
                    "One of your questions exceeds 300 characters. Please shorten it."
                )
                continue

            if any(len(option) > 100 for option in options):
                logger.warning(f"One of the options exceeds 100 characters: {options}")
                await update.message.reply_text(
                    "One of the options exceeds 100 characters. Please shorten it."
                )
                continue

            if explanation and len(explanation) > 200:
                logger.warning(f"Explanation exceeds 200 characters: {explanation}")
                await update.message.reply_text(
                    "Your explanation exceeds 200 characters. Please shorten it."
                )
                continue

            # Send the poll
            try:
                await update.message.reply_poll(
                    question=question,
                    options=options,
                    type=Poll.QUIZ,
                    correct_option_id=correct_option_index,
                    explanation=explanation or None
                )
                logger.info(f"Poll created successfully by user {user_id}: {question}")
            except Exception as e:
                logger.error(f"Error sending poll: {e}")
                await update.message.reply_text(f"Failed to send poll. Reason: {e}")
    else:
        # Unauthorized user
        logger.warning(f"Unauthorized access attempt by user ID: {user_id}")
        response = random.choice(UNAUTHORIZED_RESPONSES)
        await update.message.reply_text(response)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /start command."""
    user_id = update.effective_user.id

    if not is_authorized(user_id):
        logger.warning(f"Unauthorized access attempt by user ID: {user_id}")
        response = random.choice(UNAUTHORIZED_RESPONSES)
        await update.message.reply_text(response)
        return

    logger.info(f"User {user_id} issued /start")
    await update.message.reply_text(
        "Welcome to the MCQ Bot!\n\n"
        "Send your questions in multiple format as shown below.\n\n"
        f"{INSTRUCTION_MESSAGE}"
    )

# ------------------------------------------------------------------------
# 5) Main function to run the bot
# ------------------------------------------------------------------------
def main():
    # Build the application (bot) using the token
    application = ApplicationBuilder().token(TOKEN).build()

    # Register handlers
    application.add_handler(CommandHandler('start', start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Run the bot
    logger.info("Bot started... Press Ctrl+C to stop.")
    application.run_polling()

if __name__ == '__main__':
    main()
