# main.py

import os
import logging
import re
import threading
import random
import json
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
    
    Supports multiple formats:
    
    1. Multi-line Format (with optional question numbers)
    2. Single-line Format
    3. Numbered Options Format
    4. JSON-Based MCQ
    5. Inline Options with Commas
    
    Returns:
        tuple: (question, options, correct_option_index, explanation) or (None, None, None, None) on failure
    """
    try:
        text = text.strip()
        
        # Check for JSON format
        if text.startswith('{') and text.endswith('}'):
            return parse_json_mcq(text)
        
        # Check for Single-line format
        if '|' in text and ('Q:' in text or 'Question:' in text):
            return parse_single_line_mcq(text)
        
        # Check for Numbered Options format
        if re.search(r'\d+\.', text):
            return parse_numbered_options_mcq(text)
        
        # Check for Inline Options with Commas
        if 'Options:' in text:
            return parse_inline_options_mcq(text)
        
        # Fallback to Multi-line format
        return parse_multi_line_mcq(text)
    
    except Exception as e:
        logger.error(f"Error parsing MCQ: {e}")
        return None, None, None, None

def parse_multi_line_mcq(text):
    """
    Parses the multi-line MCQ format, accommodating questions with numbers (e.g., "Question 1:").
    """
    lines = [line.strip() for line in text.strip().split('\n') if line.strip()]
    question = ''
    options = []
    correct_option_index = None
    explanation = ''

    # Define regex patterns
    # Updated to handle "Question" followed by an optional number (e.g., "Question 1:")
    question_pattern = re.compile(r'^Question(?:\s+\d+)?\s*:\s*(.+)$', re.IGNORECASE)
    option_pattern = re.compile(r'^([a-dA-D])\)\s*(.+)$')
    correct_answer_pattern = re.compile(r'^Correct Answer\s*:\s*([a-dA-D])\)?', re.IGNORECASE)
    explanation_pattern = re.compile(r'^Explanation\s*:\s*(.+)$', re.IGNORECASE)

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
        logger.error("Question not found in the provided MCQ.")
        return None, None, None, None
    if len(options) < 2:
        logger.error("Insufficient options provided in the MCQ.")
        return None, None, None, None
    if correct_option_index is None or correct_option_index >= len(options):
        logger.error("Correct answer index is invalid.")
        return None, None, None, None

    return question, options, correct_option_index, explanation

def parse_single_line_mcq(text):
    """
    Parses the single-line MCQ format.
    """
    try:
        # Split the text by '|'
        parts = [part.strip() for part in text.strip().split('|') if part.strip()]
        data = {}
        for part in parts:
            key, value = part.split(':', 1)
            data[key.strip().lower()] = value.strip()

        # Extract components
        question = data.get('q') or data.get('question')
        options = [
            data.get('a'),
            data.get('b'),
            data.get('c'),
            data.get('d')
        ]
        # Remove None values in case less than 4 options are provided
        options = [opt for opt in options if opt]

        answer = data.get('answer')
        explanation = data.get('explanation')

        if not question or not options or not answer:
            logger.error("Missing required fields in single-line MCQ.")
            return None, None, None, None

        # Determine the correct option index
        correct_option_letter = answer.lower().strip(')')
        if correct_option_letter not in ['a', 'b', 'c', 'd']:
            logger.error("Correct answer letter is invalid in single-line MCQ.")
            return None, None, None, None

        correct_option_index = ord(correct_option_letter) - ord('a')

        return question, options, correct_option_index, explanation
    except Exception as e:
        logger.error(f"Error parsing single-line MCQ: {e}")
        return None, None, None, None

def parse_numbered_options_mcq(text):
    """
    Parses MCQ with numbered options.
    """
    try:
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        question = ''
        options = []
        correct_option_index = None
        explanation = ''

        for line in lines:
            if line.lower().startswith('question:'):
                question = line.split(':', 1)[1].strip()
            elif re.match(r'^\d+\.\s', line):
                option = re.split(r'^\d+\.\s', line, maxsplit=1)[1].strip()
                options.append(option)
            elif line.lower().startswith('answer:'):
                answer = line.split(':', 1)[1].strip()
                if answer.isdigit():
                    correct_option_index = int(answer) - 1
            elif line.lower().startswith('explanation:'):
                explanation = line.split(':', 1)[1].strip()

        if not question or not options or correct_option_index is None:
            logger.error("Missing required fields in Numbered Options MCQ.")
            return None, None, None, None

        return question, options, correct_option_index, explanation

    except Exception as e:
        logger.error(f"Error parsing Numbered Options MCQ: {e}")
        return None, None, None, None

def parse_json_mcq(text):
    """
    Parses a JSON-formatted MCQ.
    """
    try:
        data = json.loads(text)
        question = data.get('question')
        options_dict = data.get('options', {})
        options = list(options_dict.values())
        answer_key = data.get('answer').upper()
        explanation = data.get('explanation', '')

        if not question or not options or not answer_key:
            logger.error("Missing required fields in JSON MCQ.")
            return None, None, None, None

        correct_option_index = ord(answer_key) - ord('A')
        return question, options, correct_option_index, explanation

    except json.JSONDecodeError as e:
        logger.error(f"JSON parsing error: {e}")
        return None, None, None, None
    except Exception as e:
        logger.error(f"Error parsing JSON MCQ: {e}")
        return None, None, None, None

def parse_inline_options_mcq(text):
    """
    Parses MCQ with inline options separated by commas.
    """
    try:
        question_match = re.search(r'Question:\s*(.+)', text, re.IGNORECASE)
        options_match = re.search(r'Options:\s*(.+)', text, re.IGNORECASE)
        answer_match = re.search(r'Answer:\s*(.+)', text, re.IGNORECASE)
        explanation_match = re.search(r'Explanation:\s*(.+)', text, re.IGNORECASE)

        if not question_match or not options_match or not answer_match:
            logger.error("Missing required fields in Inline Options MCQ.")
            return None, None, None, None

        question = question_match.group(1).strip()
        options = [opt.strip() for opt in options_match.group(1).split(',') if opt.strip()]
        answer = answer_match.group(1).strip()
        explanation = explanation_match.group(1).strip() if explanation_match else ''

        if not options:
            logger.error("No options found in Inline Options MCQ.")
            return None, None, None, None

        try:
            correct_option_index = options.index(answer)
        except ValueError:
            logger.error("Answer does not match any of the options.")
            return None, None, None, None

        return question, options, correct_option_index, explanation

    except Exception as e:
        logger.error(f"Error parsing Inline Options MCQ: {e}")
        return None, None, None, None

# Predefined messages for unauthorized users
UNAUTHORIZED_RESPONSES = [
    "@iwanna2die : leave my bot buddy",
    "@iwanna2die : if can see u here",
    "@iwanna2die : this is my bot can u leave it ?",
    "@iwanba2die : leave my bot alone"
]

# Predefined instruction message for authorized users
INSTRUCTION_MESSAGE = (
    "Please use one of the following formats to create an MCQ:\n\n"
    "1. **Multi-line Format (with optional question numbers):**\n"
    "```\n"
    "Question 1: What is the primary role of antigens in adaptive immunity?\n"
    "A) To destroy pathogens directly\n"
    "B) To activate immune cells by being recognized as foreign\n"
    "C) To produce antibodies themselves\n"
    "D) To inhibit immune responses\n"
    "Correct Answer: B) To activate immune cells by being recognized as foreign\n"
    "Explanation: Antigens are substances that elicit an immune response by being recognized as foreign by the immune system.\n"
    "``` \n\n"
    "2. **Single-line Format:**\n"
    "```\n"
    "Q: What is the capital of France? | A: Berlin | B: Madrid | C: Paris | D: Rome | Answer: C | Explanation: Paris is the capital and most populous city of France.\n"
    "``` \n\n"
    "3. **Numbered Options Format:**\n"
    "```\n"
    "Question: What is the largest planet in our Solar System?\n"
    "1. Earth\n"
    "2. Jupiter\n"
    "3. Mars\n"
    "4. Saturn\n"
    "Answer: 2\n"
    "Explanation: Jupiter is the largest planet in our Solar System.\n"
    "``` \n\n"
    "4. **JSON-Based MCQ:**\n"
    "```\n"
    "{\n"
    "    \"question\": \"What is the boiling point of water?\",\n"
    "    \"options\": {\n"
    "        \"A\": \"90°C\",\n"
    "        \"B\": \"100°C\",\n"
    "        \"C\": \"110°C\",\n"
    "        \"D\": \"120°C\"\n"
    "    },\n"
    "    \"answer\": \"B\",\n"
    "    \"explanation\": \"Water boils at 100°C under standard atmospheric conditions.\"\n"
    "}\n"
    "``` \n\n"
    "5. **Inline Options with Commas:**\n"
    "```\n"
    "Question: Which element has the chemical symbol 'O'?\n"
    "Options: Oxygen, Gold, Osmium, Iron\n"
    "Answer: Oxygen\n"
    "Explanation: 'O' stands for Oxygen in the periodic table.\n"
    "```"
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
    welcome_message = (
        "Welcome to the MCQ Bot! You can create MCQs using the following formats:\n\n"
        "1. **Multi-line Format (with optional question numbers):**\n"
        "```\n"
        "Question 1: What is the primary role of antigens in adaptive immunity?\n"
        "A) To destroy pathogens directly\n"
        "B) To activate immune cells by being recognized as foreign\n"
        "C) To produce antibodies themselves\n"
        "D) To inhibit immune responses\n"
        "Correct Answer: B) To activate immune cells by being recognized as foreign\n"
        "Explanation: Antigens are substances that elicit an immune response by being recognized as foreign by the immune system.\n"
        "``` \n\n"
        "2. **Single-line Format:**\n"
        "```\n"
        "Q: What is the capital of France? | A: Berlin | B: Madrid | C: Paris | D: Rome | Answer: C | Explanation: Paris is the capital and most populous city of France.\n"
        "``` \n\n"
        "3. **Numbered Options Format:**\n"
        "```\n"
        "Question: What is the largest planet in our Solar System?\n"
        "1. Earth\n"
        "2. Jupiter\n"
        "3. Mars\n"
        "4. Saturn\n"
        "Answer: 2\n"
        "Explanation: Jupiter is the largest planet in our Solar System.\n"
        "``` \n\n"
        "4. **JSON-Based MCQ:**\n"
        "```\n"
        "{\n"
        "    \"question\": \"What is the boiling point of water?\",\n"
        "    \"options\": {\n"
        "        \"A\": \"90°C\",\n"
        "        \"B\": \"100°C\",\n"
        "        \"C\": \"110°C\",\n"
        "        \"D\": \"120°C\"\n"
        "    },\n"
        "    \"answer\": \"B\",\n"
        "    \"explanation\": \"Water boils at 100°C under standard atmospheric conditions.\"\n"
        "}\n"
        "``` \n\n"
        "5. **Inline Options with Commas:**\n"
        "```\n"
        "Question: Which element has the chemical symbol 'O'?\n"
        "Options: Oxygen, Gold, Osmium, Iron\n"
        "Answer: Oxygen\n"
        "Explanation: 'O' stands for Oxygen in the periodic table.\n"
        "```"
    )
    await update.message.reply_text(welcome_message, parse_mode='Markdown')

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
