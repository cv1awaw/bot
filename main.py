import os
import json
import re
import logging
from logging.handlers import TimedRotatingFileHandler
from datetime import time as dtime

from telegram import Update, Poll
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    MessageHandler,
    CommandHandler,
    PollHandler,
    PollAnswerHandler,
    filters,
)

# ----------------------
# 0) Configuration
# ----------------------
TOKEN = os.environ.get('BOT_TOKEN')
ADMIN_CHAT_ID = os.environ.get('ADMIN_CHAT_ID')  # for error alerts
ADMIN_ID = 6177929931

if not TOKEN:
    raise RuntimeError("Environment variable BOT_TOKEN is not set.")

# ----------------------
# 1) Rotating & Structured Logging
# ----------------------
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

console_h = logging.StreamHandler()
console_h.setLevel(logging.INFO)
console_fmt = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
console_h.setFormatter(console_fmt)
logger.addHandler(console_h)

file_h = TimedRotatingFileHandler(
    'bot.log', when='midnight', backupCount=7, encoding='utf-8'
)
file_fmt = logging.Formatter(
    '{"timestamp":"%(asctime)s","level":"%(levelname)s","module":"%(name)s","message":"%(message)s"}'
)
file_h.setFormatter(file_fmt)
logger.addHandler(file_h)

# ----------------------
# 2) Dynamic Authorization via JSON file
# ----------------------
ALLOWED_USERS_FILE = 'allowed_users.json'

def save_allowed_users(user_ids):
    with open(ALLOWED_USERS_FILE, 'w', encoding='utf-8') as f:
        json.dump(user_ids, f)

def load_allowed_users():
    users = []
    if os.path.exists(ALLOWED_USERS_FILE):
        with open(ALLOWED_USERS_FILE, 'r', encoding='utf-8') as f:
            users = json.load(f)
    else:
        try:
            from allowed_users import ALLOWED_USER_IDS
            users = ALLOWED_USER_IDS
        except ImportError:
            users = []
    # ensure admin is always authorized
    if ADMIN_ID not in users:
        users.append(ADMIN_ID)
        save_allowed_users(users)
    return users

ALLOWED_USER_IDS = load_allowed_users()

def is_authorized(user_id: int) -> bool:
    return user_id in ALLOWED_USER_IDS

# ----------------------
# 3) Authorization Commands: /adduser & /removeuser
# ----------------------
async def adduser(update: Update, context: ContextTypes.DEFAULT_TYPE):
    requester = update.effective_user.id
    if not is_authorized(requester):
        return await update.message.reply_text("🔒 You’re not allowed to add users.")

    if len(context.args) != 1 or not context.args[0].isdigit():
        return await update.message.reply_text("Usage: /adduser <user_id>")

    new_id = int(context.args[0])
    if new_id in ALLOWED_USER_IDS:
        await update.message.reply_text(f"User {new_id} is already authorized.")
    else:
        ALLOWED_USER_IDS.append(new_id)
        save_allowed_users(ALLOWED_USER_IDS)
        await update.message.reply_text(f"✅ Added user {new_id} to allowed list.")

async def removeuser(update: Update, context: ContextTypes.DEFAULT_TYPE):
    requester = update.effective_user.id
    if not is_authorized(requester):
        return await update.message.reply_text("🔒 You’re not allowed to remove users.")

    if len(context.args) != 1 or not context.args[0].isdigit():
        return await update.message.reply_text("Usage: /removeuser <user_id>")

    rem_id = int(context.args[0])
    if rem_id not in ALLOWED_USER_IDS:
        await update.message.reply_text(f"User {rem_id} is not in the allowed list.")
    else:
        ALLOWED_USER_IDS.remove(rem_id)
        save_allowed_users(ALLOWED_USER_IDS)
        await update.message.reply_text(f"❌ Removed user {rem_id} from allowed list.")

# ----------------------
# 4) List & Help Commands
# ----------------------
async def listusers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    caller = update.effective_user.id
    if not is_authorized(caller):
        return await update.message.reply_text("🚫 You’re not authorized.")
    text = "✅ *Allowed users:*\n" + "\n".join(f"- `{uid}`" for uid in ALLOWED_USER_IDS)
    await update.message.reply_markdown(text)

HELP_TEXT = """
*Admin commands*:
/adduser `<user_id>` — add someone  
/removeuser `<user_id>` — remove someone  
/listusers — list all allowed IDs  
/schedule_reminder `HH:MM` _text_ — daily reminder  
/start — restart the bot  
"""

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return await update.message.reply_text("🔒 This command is for the bot admin only.")
    await update.message.reply_markdown(HELP_TEXT)

# ----------------------
# 5) Global Error Handler
# ----------------------
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error("Exception while handling an update:", exc_info=context.error)
    if ADMIN_CHAT_ID:
        try:
            await context.bot.send_message(
                chat_id=int(ADMIN_CHAT_ID),
                text=f"🚨 Error: {context.error}"
            )
        except Exception as e:
            logger.error(f"Failed to send error alert: {e}")

# ----------------------
# 6) MCQ Parsing Helpers
# ----------------------
def preprocess_text_for_questions(text):
    pattern = re.compile(r'([^\n])Question:\s*', re.IGNORECASE)
    return pattern.sub(r'\1\nQuestion: ', text)

def parse_single_mcq(text):
    try:
        lines = [l.strip() for l in text.strip().split('\n') if l.strip()]
        question, options, correct_idx, explanation = '', [], None, ''
        q_pat = re.compile(r'^Question:\s*(.+)$', re.IGNORECASE)
        o_pat = re.compile(r'^([A-Ja-j])\)\s*(.+)$')
        ca_pat = re.compile(r'^Correct Answer:\s*([A-Ja-j])', re.IGNORECASE)
        ex_pat = re.compile(r'^Explanation:\s*(.+)$', re.IGNORECASE)

        for line in lines:
            if m := q_pat.match(line):
                question = m.group(1).strip()
            elif m := o_pat.match(line):
                options.append(m.group(2).strip())
            elif m := ca_pat.match(line):
                correct_idx = ord(m.group(1).lower()) - ord('a')
            elif m := ex_pat.match(line):
                explanation = m.group(1).strip()

        if not question or len(options) < 2 or correct_idx is None or correct_idx >= len(options):
            return None, None, None, None
        return question, options, correct_idx, explanation
    except Exception as e:
        logger.error(f"parse_single_mcq error: {e}")
        return None, None, None, None

def parse_multiple_mcqs(text):
    text = preprocess_text_for_questions(text)
    header_re = re.compile(
        r'^\s*(?:Question(?:\s*(?:No\.?|#)\s*\d+|\s*\d+)?|Q\s*\d+|Q)\s*:\s*',
        re.IGNORECASE
    )
    blocks, current = [], []
    for line in text.split('\n'):
        if header_re.match(line.strip()) and current:
            blocks.append('\n'.join(current))
            current = []
        current.append(line)
    if current:
        blocks.append('\n'.join(current))

    parsed = []
    for blk in blocks:
        q, opts, idx, exp = parse_single_mcq(blk)
        if q:
            parsed.append((q, opts, idx, exp))
        else:
            logger.warning("Ignoring malformed question block.")
    return parsed

INSTRUCTION_MESSAGE = (
    "Send questions in this format:\n\n"
    "Question: Your question text\n"
    "A) Option 1\n"
    "B) Option 2\n"
    "...\n"
    "Correct Answer: B\n"
    "Explanation: Your explanation\n\n"
    "• Max 10 options (A–J)\n"
    "• Question ≤ 300 chars\n"
    "• Each option ≤ 100 chars\n"
    "• Explanation ≤ 200 chars"
)

# ----------------------
# 7) MCQ Handler
# ----------------------
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        return await update.message.reply_text("🚫 You are not authorized to use this bot.")

    mcqs = parse_multiple_mcqs(update.message.text)
    if not mcqs:
        return await update.message.reply_text(INSTRUCTION_MESSAGE)

    for question, options, correct_idx, explanation in mcqs:
        if len(question) > 300:
            await update.message.reply_text("One question exceeds 300 characters. Please shorten it.")
            continue
        if any(len(opt) > 100 for opt in options):
            await update.message.reply_text("One of the options exceeds 100 characters. Please shorten it.")
            continue
        if explanation and len(explanation) > 200:
            await update.message.reply_text("Your explanation exceeds 200 characters. Please shorten it.")
            continue

        try:
            await update.message.reply_poll(
                question=question,
                options=options,
                type=Poll.QUIZ,
                correct_option_id=correct_idx,
                explanation=explanation or None
            )
            logger.info(f"Poll sent: {question}")
        except Exception as e:
            logger.error(f"Failed to send poll: {e}")
            await update.message.reply_text(f"❌ Failed to send poll: {e}")

# ----------------------
# 8) Poll Tracking Handlers
# ----------------------
async def handle_poll_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    poll: Poll = update.poll
    logger.info(
        f"Poll updated: id={poll.id!r}, question={poll.question!r}, "
        f"total_voters={poll.total_voter_count}"
    )

async def handle_poll_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    answer = update.poll_answer
    logger.info(
        f"User {answer.user.id} answered poll {answer.poll_id!r}: options={answer.option_ids}"
    )

# ----------------------
# 9) Scheduling with JobQueue
# ----------------------
async def reminder_callback(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    await context.bot.send_message(chat_id=job.chat_id, text=job.data)

async def schedule_reminder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        return await update.message.reply_text("🚫 You are not authorized.")

    if len(context.args) < 2:
        return await update.message.reply_text("Usage: /schedule_reminder HH:MM your reminder text")

    timestr = context.args[0]
    try:
        hh, mm = map(int, timestr.split(':'))
        remind_time = dtime(hour=hh, minute=mm)
    except:
        return await update.message.reply_text("Invalid time format. Use HH:MM (24h).")

    text = ' '.join(context.args[1:])
    context.job_queue.run_daily(
        reminder_callback,
        time=remind_time,
        chat_id=update.effective_chat.id,
        data=text,
        name=f"reminder_{update.effective_chat.id}_{timestr}"
    )
    await update.message.reply_text(f"⏰ Reminder scheduled every day at {timestr}.")

# ----------------------
# 10) /start & Main
# ----------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_user.id):
        return await update.message.reply_text("🚫 You are not authorized.")
    await update.message.reply_text(
        "🤖 Welcome to the enhanced MCQ Bot!\n\n" + INSTRUCTION_MESSAGE
    )

def main():
    app = ApplicationBuilder().token(TOKEN).build()

    # Command handlers
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('adduser', adduser))
    app.add_handler(CommandHandler('removeuser', removeuser))
    app.add_handler(CommandHandler('listusers', listusers))
    app.add_handler(CommandHandler('help', help_command))
    app.add_handler(CommandHandler('schedule_reminder', schedule_reminder))

    # Message & Poll handlers
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(PollHandler(handle_poll_update))
    app.add_handler(PollAnswerHandler(handle_poll_answer))

    # Error handler
    app.add_error_handler(error_handler)

    logger.info("Starting bot...")
    app.run_polling()

if __name__ == '__main__':
    main()
