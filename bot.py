"""
RemindMeBot — a simple personal reminder / to-do Telegram bot.

Commands:
  /start            Welcome message + quick instructions
  /help             Show usage instructions
  /remind           Create a reminder
  /list             List your upcoming reminders
  /cancel <id>      Cancel a reminder by its ID
  /privacy          Show the bot's privacy policy (required for Ads review)

Reminder formats supported:
  /remind in 30m Call John
  /remind in 2h Submit report
  /remind in 1d Pay rent
  /remind at 17:00 Call John        (today, or tomorrow if that time already passed)
  /remind at 2026-07-25 09:00 Dentist appointment

Data is stored in a local SQLite database so reminders survive bot restarts
(as long as the DB file lives on a persisted volume — see README.md).
"""

import logging
import os
import re
import sqlite3
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)

# ----------------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------------

BOT_TOKEN = os.environ.get("BOT_TOKEN")
DB_PATH = os.environ.get("DB_PATH", "reminders.db")
TIMEZONE = os.environ.get("TIMEZONE", "UTC")  # e.g. "Africa/Lagos"

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

TZ = ZoneInfo(TIMEZONE)

# ----------------------------------------------------------------------------
# Database helpers
# ----------------------------------------------------------------------------

def db_connect():
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            message TEXT NOT NULL,
            due_at TEXT NOT NULL,
            sent INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    conn.commit()
    return conn


def add_reminder(chat_id: int, message: str, due_at: datetime) -> int:
    conn = db_connect()
    cur = conn.execute(
        "INSERT INTO reminders (chat_id, message, due_at, sent) VALUES (?, ?, ?, 0)",
        (chat_id, message, due_at.isoformat()),
    )
    conn.commit()
    reminder_id = cur.lastrowid
    conn.close()
    return reminder_id


def get_upcoming_reminders(chat_id: int):
    conn = db_connect()
    rows = conn.execute(
        "SELECT id, message, due_at FROM reminders "
        "WHERE chat_id = ? AND sent = 0 ORDER BY due_at ASC",
        (chat_id,),
    ).fetchall()
    conn.close()
    return rows


def cancel_reminder(chat_id: int, reminder_id: int) -> bool:
    conn = db_connect()
    cur = conn.execute(
        "DELETE FROM reminders WHERE id = ? AND chat_id = ? AND sent = 0",
        (reminder_id, chat_id),
    )
    conn.commit()
    deleted = cur.rowcount > 0
    conn.close()
    return deleted


def mark_sent(reminder_id: int):
    conn = db_connect()
    conn.execute("UPDATE reminders SET sent = 1 WHERE id = ?", (reminder_id,))
    conn.commit()
    conn.close()


def get_due_reminders(now_iso: str):
    conn = db_connect()
    rows = conn.execute(
        "SELECT id, chat_id, message FROM reminders "
        "WHERE sent = 0 AND due_at <= ?",
        (now_iso,),
    ).fetchall()
    conn.close()
    return rows


def load_all_pending():
    """Used at startup to re-schedule reminders that survived a restart."""
    conn = db_connect()
    rows = conn.execute(
        "SELECT id, chat_id, message, due_at FROM reminders WHERE sent = 0"
    ).fetchall()
    conn.close()
    return rows


# ----------------------------------------------------------------------------
# Time parsing
# ----------------------------------------------------------------------------

RELATIVE_RE = re.compile(r"^in\s+(\d+)\s*(m|min|mins|minute|minutes|h|hr|hrs|hour|hours|d|day|days)\s+(.+)$", re.IGNORECASE)
ABSOLUTE_TIME_RE = re.compile(r"^at\s+(\d{1,2}):(\d{2})\s+(.+)$", re.IGNORECASE)
ABSOLUTE_DATETIME_RE = re.compile(r"^at\s+(\d{4}-\d{2}-\d{2})\s+(\d{1,2}):(\d{2})\s+(.+)$", re.IGNORECASE)


def parse_reminder_text(text: str):
    """
    Parses the text following '/remind '.
    Returns (due_datetime, message) or (None, None) if it can't be parsed.
    """
    text = text.strip()

    m = ABSOLUTE_DATETIME_RE.match(text)
    if m:
        date_str, hh, mm, message = m.groups()
        try:
            due = datetime.strptime(f"{date_str} {hh}:{mm}", "%Y-%m-%d %H:%M").replace(tzinfo=TZ)
            return due, message.strip()
        except ValueError:
            return None, None

    m = ABSOLUTE_TIME_RE.match(text)
    if m:
        hh, mm, message = m.groups()
        now = datetime.now(TZ)
        try:
            due = now.replace(hour=int(hh), minute=int(mm), second=0, microsecond=0)
        except ValueError:
            return None, None
        if due <= now:
            due += timedelta(days=1)
        return due, message.strip()

    m = RELATIVE_RE.match(text)
    if m:
        amount, unit, message = m.groups()
        amount = int(amount)
        unit = unit.lower()
        now = datetime.now(TZ)
        if unit.startswith("m"):
            due = now + timedelta(minutes=amount)
        elif unit.startswith("h"):
            due = now + timedelta(hours=amount)
        else:
            due = now + timedelta(days=amount)
        return due, message.strip()

    return None, None


# ----------------------------------------------------------------------------
# Command handlers
# ----------------------------------------------------------------------------

WELCOME_TEXT = (
    "👋 Hi! I'm *RemindMeBot* — I help you remember things.\n\n"
    "Set a reminder like this:\n"
    "• `/remind in 30m Call John`\n"
    "• `/remind in 2h Submit report`\n"
    "• `/remind at 17:00 Pick up kids`\n\n"
    "Other commands:\n"
    "/list — see your upcoming reminders\n"
    "/cancel <id> — cancel a reminder\n"
    "/help — show this again\n"
    "/privacy — privacy policy"
)

PRIVACY_TEXT = (
    "🔒 *Privacy Policy*\n\n"
    "RemindMeBot stores only what is needed to deliver your reminders: "
    "your Telegram chat ID, the reminder text you send, and the time you asked "
    "to be reminded. We do not collect names, phone numbers, or any other "
    "personal data, and we do not share data with third parties.\n\n"
    "You can delete a reminder at any time with /cancel <id>. "
    "If you'd like all your data removed, just message the bot owner."
)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(WELCOME_TEXT, parse_mode="Markdown")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(WELCOME_TEXT, parse_mode="Markdown")


async def privacy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(PRIVACY_TEXT, parse_mode="Markdown")


async def remind_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = " ".join(context.args)
    if not text:
        await update.message.reply_text(
            "Please tell me when and what to remind you about.\n\n"
            "Examples:\n"
            "`/remind in 30m Call John`\n"
            "`/remind at 17:00 Pick up kids`",
            parse_mode="Markdown",
        )
        return

    due, message = parse_reminder_text(text)
    if due is None:
        await update.message.reply_text(
            "Sorry, I couldn't understand that format. Try:\n"
            "`/remind in 30m Call John`\n"
            "`/remind at 17:00 Pick up kids`",
            parse_mode="Markdown",
        )
        return

    chat_id = update.effective_chat.id
    reminder_id = add_reminder(chat_id, message, due)
    schedule_reminder(context.application, reminder_id, chat_id, message, due)

    await update.message.reply_text(
        f"✅ Got it! I'll remind you to *{message}* on "
        f"{due.strftime('%Y-%m-%d %H:%M')} ({TIMEZONE}).\n"
        f"Reminder ID: `{reminder_id}`",
        parse_mode="Markdown",
    )


async def list_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    rows = get_upcoming_reminders(chat_id)
    if not rows:
        await update.message.reply_text("You have no upcoming reminders. 🎉")
        return

    lines = ["📋 *Your upcoming reminders:*"]
    for reminder_id, message, due_at in rows:
        due = datetime.fromisoformat(due_at)
        lines.append(f"• `{reminder_id}` — {message} — {due.strftime('%Y-%m-%d %H:%M')}")
    lines.append("\nCancel one with `/cancel <id>`")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: `/cancel <id>`", parse_mode="Markdown")
        return
    try:
        reminder_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Please provide a valid reminder ID number.")
        return

    chat_id = update.effective_chat.id
    ok = cancel_reminder(chat_id, reminder_id)
    if ok:
        # Also remove the scheduled job if it exists
        job_name = f"reminder_{reminder_id}"
        for job in context.application.job_queue.get_jobs_by_name(job_name):
            job.schedule_removal()
        await update.message.reply_text(f"🗑️ Reminder `{reminder_id}` cancelled.", parse_mode="Markdown")
    else:
        await update.message.reply_text("I couldn't find an active reminder with that ID.")


# ----------------------------------------------------------------------------
# Scheduling
# ----------------------------------------------------------------------------

async def send_reminder_callback(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    reminder_id, chat_id, message = job.data
    await context.bot.send_message(chat_id=chat_id, text=f"⏰ Reminder: {message}")
    mark_sent(reminder_id)


def schedule_reminder(application: Application, reminder_id: int, chat_id: int, message: str, due_at: datetime):
    now = datetime.now(TZ)
    delay = (due_at - now).total_seconds()
    if delay < 0:
        delay = 0
    application.job_queue.run_once(
        send_reminder_callback,
        when=delay,
        data=(reminder_id, chat_id, message),
        name=f"reminder_{reminder_id}",
    )


def reschedule_pending(application: Application):
    """Re-create scheduled jobs for reminders that were pending before a restart."""
    rows = load_all_pending()
    for reminder_id, chat_id, message, due_at in rows:
        due = datetime.fromisoformat(due_at)
        schedule_reminder(application, reminder_id, chat_id, message, due)
    if rows:
        logger.info(f"Rescheduled {len(rows)} pending reminder(s) after restart.")


# ----------------------------------------------------------------------------
# Entry point
# ----------------------------------------------------------------------------

def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN environment variable is not set.")

    db_connect().close()  # ensure table exists

    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("privacy", privacy_command))
    application.add_handler(CommandHandler("remind", remind_command))
    application.add_handler(CommandHandler("list", list_command))
    application.add_handler(CommandHandler("cancel", cancel_command))

    reschedule_pending(application)

    logger.info("RemindMeBot starting (polling mode)...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
