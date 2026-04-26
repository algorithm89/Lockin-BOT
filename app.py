from __future__ import annotations
import os
import re
import uuid
import logging
import tempfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from flask import Flask, request
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("lockinbot")

from database import init_db, ensure_user, save_checkin
from bot import get_ai_response
from scheduler import start_scheduler, get_scheduler, set_telegram_sender

app = Flask(__name__)
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

# ── Telegram Bot ──
import telebot
tg_bot = telebot.TeleBot(TELEGRAM_TOKEN, threaded=True) if TELEGRAM_TOKEN else None

WORKER_POOL = ThreadPoolExecutor(max_workers=int(os.getenv("MESSAGE_WORKERS", "8")))

# ── Human Verification ──
VERIFIED_USERS: set[int] = set()  # chat_ids that passed the verification tap

# Auto-detect check-in keywords
PILLAR_KEYWORDS = {
    "sleep":    ["sleep", "slept", "bed", "woke", "wake"],
    "train":    ["train", "trained", "workout", "gym", "ran", "run", "lift", "exercise"],
    "meditate": ["meditate", "meditated", "meditation", "breathwork", "breath"],
    "rest":     ["rest", "rested", "nap", "napped", "recovery", "stretched"],
}


def detect_checkin(text: str) -> str | None:
    """Return pillar name if the message looks like a check-in, else None."""
    lower = text.lower()
    # Look for positive check-in signals
    positive = any(w in lower for w in ["done", "did", "finished", "completed", "just", "✅", "checked"])
    for pillar, keywords in PILLAR_KEYWORDS.items():
        if any(k in lower for k in keywords):
            if positive or len(lower.split()) <= 4:
                return pillar
    return None


def extract_reminder_minutes(text: str) -> int | None:
    """Extract reminder minutes from common user phrases like 'in 5 min' or 'remind me 10 minutes'."""
    lower = (text or "").lower()
    m = re.search(r"\bin\s*(\d{1,3})\s*(m|min|mins|minute|minutes)\b", lower)
    if not m:
        m = re.search(r"\bremind\s+me\s*(?:in\s*)?(\d{1,3})\s*(m|min|mins|minute|minutes)\b", lower)
    if not m:
        return None
    minutes = int(m.group(1))
    if 1 <= minutes <= 1440:
        return minutes
    return None


def strip_internal_tags(text: str) -> str:
    cleaned = re.sub(r'\s*\[REMIND:\d+\]', '', text or '').strip()
    cleaned = re.sub(r'\s*\[PROFILE:.*?\]', '', cleaned, flags=re.DOTALL).strip()
    return cleaned


@app.route("/health", methods=["GET"])
def health():
    logger.info("💚 Health check OK")
    return "LockIn Bot is running 💪", 200


# ═══════════════════════════════════════
# TELEGRAM
# ═══════════════════════════════════════

def _process_telegram(message):
    """Background: generate AI response and send via Telegram."""
    chat_id = message.chat.id
    body = message.text or ""
    phone = f"tg_{chat_id}"

    logger.info(f"📩 Telegram from {chat_id}: \"{body}\"")

    # Register this user as the Telegram reminder target
    set_telegram_sender(tg_bot, chat_id)

    # Handle /start — send verification button
    if body.strip() == "/start":
        markup = telebot.types.InlineKeyboardMarkup()
        markup.add(telebot.types.InlineKeyboardButton(
            "✅ I'm a human, let me in", callback_data="verify_human"
        ))
        tg_bot.send_message(
            chat_id,
            "👋 Welcome to LockIn Bot!\nBefore we start — tap the button below to verify you're human.",
            reply_markup=markup
        )
        return

    # Gate: must verify first
    if chat_id not in VERIFIED_USERS:
        markup = telebot.types.InlineKeyboardMarkup()
        markup.add(telebot.types.InlineKeyboardButton(
            "✅ I'm a human, let me in", callback_data="verify_human"
        ))
        tg_bot.send_message(
            chat_id,
            "⚠️ Please verify you're human first by tapping the button below.",
            reply_markup=markup
        )
        return

    # Send typing indicator
    tg_bot.send_chat_action(chat_id, 'typing')

    try:
        ensure_user(phone)

        # Auto-detect and save check-in
        pillar = detect_checkin(body)
        if pillar:
            save_checkin(phone, pillar, "done")
            logger.info(f"✅ Check-in detected: {pillar} for {phone}")

        logger.info(f"🧠 Generating AI response for {phone}...")
        reply_text = get_ai_response(phone, body)

        # Check for reminder tag
        remind_match = re.search(r'\[REMIND:(\d+)\]', reply_text)
        minutes = int(remind_match.group(1)) if remind_match else extract_reminder_minutes(body)
        if minutes:
            scheduled = schedule_telegram_followup(chat_id, phone, minutes)
            if scheduled:
                logger.info(f"⏰ Scheduled Telegram follow-up for {phone} in {minutes} minutes")
            else:
                logger.warning(f"⚠️ Telegram follow-up NOT scheduled for {phone}")

        reply_text = strip_internal_tags(reply_text)

        logger.info(f"📤 Telegram reply to {chat_id}: \"{reply_text}\"")
        tg_bot.send_message(chat_id, reply_text)

    except Exception as e:
        logger.error(f"❌ Telegram error for {chat_id}: {e}", exc_info=True)
        try:
            tg_bot.send_message(chat_id, "something went wrong on my end. try again in a sec.")
        except Exception:
            pass


@app.route("/telegram", methods=["POST"])
def telegram_webhook():
    """Receive Telegram updates via webhook."""
    if not tg_bot:
        return "Telegram not configured", 503
    try:
        json_data = request.get_json(force=True)
        update = telebot.types.Update.de_json(json_data)

        if update.callback_query:
            cb = update.callback_query
            if cb.data == "verify_human":
                VERIFIED_USERS.add(cb.from_user.id)
                tg_bot.answer_callback_query(cb.id, "✅ Verified!")
                tg_bot.edit_message_text(
                    "✅ You're verified! 🔒 LockIn Bot here — your accountability partner.\nText me anything. Let's get to work.",
                    chat_id=cb.message.chat.id,
                    message_id=cb.message.message_id
                )
            return "ok", 200

        if update.message and update.message.text:
            WORKER_POOL.submit(_process_telegram, update.message)
    except Exception as e:
        logger.error(f"❌ Telegram webhook error: {e}", exc_info=True)
    return "ok", 200


def schedule_telegram_followup(chat_id: int, phone: str, minutes: int) -> bool:
    """Schedule a one-time Telegram follow-up."""
    from bot import guess_timezone
    from database import get_user_timezone
    from zoneinfo import ZoneInfo
    import random

    tz_name = get_user_timezone(phone) or guess_timezone(phone)
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = ZoneInfo("America/Montreal")

    run_at = datetime.now(tz) + timedelta(minutes=minutes)
    job_id = f"tg_followup_{chat_id}_{uuid.uuid4().hex[:8]}"

    message = random.choice([
        "⏰ Time's up! What did you get done? Check in with me.",
        "⏰ Yo, you asked me to check in. So... did you do the thing?",
        "⏰ Reminder fired. No excuses — tell me what's done.",
        "⏰ I'm back. You better have something to report. 💪",
    ])

    def send_followup():
        try:
            logger.info(f"⏰ Telegram follow-up firing for {chat_id}...")
            tg_bot.send_message(chat_id, message)
            logger.info(f"✅ Telegram follow-up sent to {chat_id}")
        except Exception as e:
            logger.error(f"❌ Telegram follow-up FAILED for {chat_id}: {e}", exc_info=True)

    scheduler = get_scheduler()
    if not scheduler:
        logger.warning("⚠️ Scheduler not running, attempting restart...")
        try:
            scheduler = start_scheduler()
        except Exception as e:
            logger.error(f"❌ Could not start scheduler: {e}", exc_info=True)
            return False

    try:
        scheduler.add_job(send_followup, trigger='date', run_date=run_at, id=job_id)
        logger.info(f"📅 Telegram follow-up {job_id} scheduled for {run_at.strftime('%H:%M:%S')}")
        return True
    except Exception as e:
        logger.error(f"❌ Could not enqueue follow-up {job_id}: {e}", exc_info=True)
        return False


def setup_telegram_webhook(base_url: str):
    """Set Telegram webhook to point to our server."""
    if not tg_bot:
        logger.info("⚠️ Telegram not configured (no TELEGRAM_BOT_TOKEN)")
        return
    webhook_url = f"{base_url.rstrip('/')}/telegram"
    ip_address = os.getenv("WEBHOOK_IP", "")
    try:
        tg_bot.remove_webhook()
        import time
        time.sleep(1)
        if ip_address:
            tg_bot.set_webhook(url=webhook_url, ip_address=ip_address)
        else:
            tg_bot.set_webhook(url=webhook_url)
        logger.info(f"✅ Telegram webhook set to {webhook_url} (ip={ip_address or 'auto'})")
    except Exception as e:
        logger.error(f"❌ Failed to set Telegram webhook: {e}", exc_info=True)




if __name__ == "__main__":
    init_db()
    start_scheduler()
    print("🔒 LockIn Bot is running!")
    app.run(host="0.0.0.0", port=5000, debug=False)

