from __future__ import annotations
import os
import re
import uuid
import logging
import tempfile
from datetime import datetime, timedelta
from flask import Flask, request, send_from_directory
from twilio.twiml.messaging_response import MessagingResponse
from twilio.twiml.voice_response import VoiceResponse, Gather
from twilio.rest import Client as TwilioClient
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
from scheduler import start_scheduler, get_scheduler

app = Flask(__name__)
tts_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
twilio_client = TwilioClient(os.getenv("TWILIO_ACCOUNT_SID"), os.getenv("TWILIO_AUTH_TOKEN"))
TWILIO_FROM = os.getenv("TWILIO_PHONE_NUMBER")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

# ── Telegram Bot ──
import telebot
tg_bot = telebot.TeleBot(TELEGRAM_TOKEN, threaded=True) if TELEGRAM_TOKEN else None


# Directory to store generated TTS audio files
AUDIO_DIR = os.path.join(tempfile.gettempdir(), "lockinbot_audio")
os.makedirs(AUDIO_DIR, exist_ok=True)

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


@app.route("/sms", methods=["POST"])
def incoming_sms():
    """Acknowledge Twilio immediately, process and reply in background."""
    phone = request.form.get("From", "")
    body = request.form.get("Body", "").strip()

    logger.info(f"📩 SMS from {phone}: \"{body}\"")

    # Process in background thread so Twilio never times out
    import threading
    threading.Thread(
        target=_process_and_reply,
        args=(phone, body),
        daemon=True,
    ).start()

    # Return empty TwiML immediately — reply will be sent via Twilio API
    resp = MessagingResponse()
    return str(resp), 200, {"Content-Type": "application/xml"}


def _process_and_reply(phone: str, body: str):
    """Background: generate AI response and send via Twilio API."""
    try:
        ensure_user(phone)

        # Auto-detect and save check-in
        pillar = detect_checkin(body)
        if pillar:
            save_checkin(phone, pillar, "done")
            logger.info(f"✅ Check-in detected: {pillar} for {phone}")

        # Get AI response
        logger.info(f"🧠 Generating AI response for {phone}...")
        reply_text = get_ai_response(phone, body)

        # Check for reminder tag [REMIND:X]
        remind_match = re.search(r'\[REMIND:(\d+)\]', reply_text)
        if remind_match:
            minutes = int(remind_match.group(1))
            reply_text = re.sub(r'\s*\[REMIND:\d+\]', '', reply_text).strip()
            schedule_followup(phone, minutes)
            logger.info(f"⏰ Scheduled follow-up for {phone} in {minutes} minutes")

        # Strip any remaining tags
        reply_text = re.sub(r'\s*\[PROFILE:.*?\]', '', reply_text, flags=re.DOTALL).strip()

        logger.info(f"📤 Reply to {phone}: \"{reply_text}\"")

        # Send reply via Twilio API (not TwiML)
        twilio_client.messages.create(
            body=reply_text,
            from_=TWILIO_FROM,
            to=phone,
        )
        logger.info(f"✅ SMS delivered to {phone}")

    except Exception as e:
        logger.error(f"❌ Error processing SMS from {phone}: {e}", exc_info=True)
        try:
            twilio_client.messages.create(
                body="something went wrong on my end. try again in a sec.",
                from_=TWILIO_FROM,
                to=phone,
            )
        except Exception:
            logger.error(f"❌ Failed to send error message to {phone}")


def schedule_followup(phone: str, minutes: int):
    """Schedule a one-time follow-up SMS."""
    from bot import guess_timezone
    from database import get_user_timezone
    from zoneinfo import ZoneInfo

    # Use the SAME timezone as the scheduler so the job fires at the right time
    tz_name = get_user_timezone(phone) or guess_timezone(phone)
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = ZoneInfo("America/Montreal")

    run_at = datetime.now(tz) + timedelta(minutes=minutes)
    job_id = f"followup_{phone}_{uuid.uuid4().hex[:8]}"

    logger.info(f"📅 Scheduling follow-up: now={datetime.now(tz).strftime('%H:%M:%S')} tz={tz_name} run_at={run_at.strftime('%H:%M:%S')}")
    job_id = f"followup_{phone}_{uuid.uuid4().hex[:8]}"

    # Pre-generate follow-up messages
    followup_messages = [
        "⏰ Time's up! What did you get done? Check in with me.",
        "⏰ Hey, this is your reminder. Lock in — what's the update?",
        "⏰ Yo, you asked me to check in. So... did you do the thing?",
        "⏰ Reminder fired. No excuses — tell me what's done.",
        "⏰ I'm back. You better have something to report. 💪",
    ]
    import random
    message = random.choice(followup_messages)

    def send_followup():
        try:
            logger.info(f"⏰ Follow-up firing for {phone}...")
            twilio_client.messages.create(
                body=message,
                from_=TWILIO_FROM,
                to=phone,
            )
            logger.info(f"✅ Follow-up sent to {phone}: \"{message}\"")
        except Exception as e:
            logger.error(f"❌ Follow-up FAILED for {phone}: {e}", exc_info=True)

    scheduler = get_scheduler()
    if scheduler:
        scheduler.add_job(
            send_followup,
            trigger='date',
            run_date=run_at,
            id=job_id,
        )
        logger.info(f"📅 Follow-up job {job_id} scheduled for {run_at.strftime('%H:%M:%S')}")
    else:
        logger.error(f"❌ Scheduler not available! Cannot schedule follow-up for {phone}")


@app.route("/health", methods=["GET"])
def health():
    logger.info("💚 Health check OK")
    return "LockIn Bot is running 💪", 200


# ═══════════════════════════════════════
# TELEGRAM
# ═══════════════════════════════════════

@app.route("/telegram", methods=["POST"])
def telegram_webhook():
    """Receive Telegram updates via webhook."""
    if not tg_bot:
        return "Telegram not configured", 503
    update = telebot.types.Update.de_json(request.get_json(force=True))
    tg_bot.process_new_updates([update])
    return "ok", 200


if tg_bot:
    @tg_bot.message_handler(commands=['start'])
    def tg_start(message):
        tg_bot.reply_to(message, "🔒 LockIn Bot here. i'm your accountability partner. text me anything — let's get to work.")

    @tg_bot.message_handler(func=lambda m: True)
    def tg_message(message):
        import threading
        threading.Thread(
            target=_process_telegram,
            args=(message,),
            daemon=True,
        ).start()


def _process_telegram(message):
    """Background: generate AI response and send via Telegram."""
    chat_id = message.chat.id
    body = message.text or ""
    phone = f"tg_{chat_id}"

    logger.info(f"📩 Telegram from {chat_id}: \"{body}\"")

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
        if remind_match:
            minutes = int(remind_match.group(1))
            reply_text = re.sub(r'\s*\[REMIND:\d+\]', '', reply_text).strip()
            schedule_telegram_followup(chat_id, phone, minutes)
            logger.info(f"⏰ Scheduled Telegram follow-up for {phone} in {minutes} minutes")

        reply_text = re.sub(r'\s*\[PROFILE:.*?\]', '', reply_text, flags=re.DOTALL).strip()

        logger.info(f"📤 Telegram reply to {chat_id}: \"{reply_text}\"")
        tg_bot.send_message(chat_id, reply_text)

    except Exception as e:
        logger.error(f"❌ Telegram error for {chat_id}: {e}", exc_info=True)
        try:
            tg_bot.send_message(chat_id, "something went wrong on my end. try again in a sec.")
        except Exception:
            pass


def schedule_telegram_followup(chat_id: int, phone: str, minutes: int):
    """Schedule a one-time Telegram follow-up."""
    from bot import guess_timezone
    from database import get_user_timezone
    from zoneinfo import ZoneInfo

    tz_name = get_user_timezone(phone) or guess_timezone(phone)
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = ZoneInfo("America/Montreal")

    run_at = datetime.now(tz) + timedelta(minutes=minutes)
    job_id = f"tg_followup_{chat_id}_{uuid.uuid4().hex[:8]}"

    import random
    followup_messages = [
        "⏰ Time's up! What did you get done? Check in with me.",
        "⏰ Yo, you asked me to check in. So... did you do the thing?",
        "⏰ Reminder fired. No excuses — tell me what's done.",
        "⏰ I'm back. You better have something to report. 💪",
    ]
    message = random.choice(followup_messages)

    def send_followup():
        try:
            logger.info(f"⏰ Telegram follow-up firing for {chat_id}...")
            tg_bot.send_message(chat_id, message)
            logger.info(f"✅ Telegram follow-up sent to {chat_id}")
        except Exception as e:
            logger.error(f"❌ Telegram follow-up FAILED for {chat_id}: {e}", exc_info=True)

    scheduler = get_scheduler()
    if scheduler:
        scheduler.add_job(send_followup, trigger='date', run_date=run_at, id=job_id)
        logger.info(f"📅 Telegram follow-up {job_id} scheduled for {run_at.strftime('%H:%M:%S')}")


def setup_telegram_webhook(base_url: str):
    """Set Telegram webhook to point to our server."""
    if not tg_bot:
        logger.info("⚠️ Telegram not configured (no TELEGRAM_BOT_TOKEN)")
        return
    webhook_url = f"{base_url.rstrip('/')}/telegram"
    try:
        tg_bot.remove_webhook()
        import time
        time.sleep(1)
        tg_bot.set_webhook(url=webhook_url)
        logger.info(f"✅ Telegram webhook set to {webhook_url}")
    except Exception as e:
        logger.error(f"❌ Failed to set Telegram webhook: {e}", exc_info=True)


@app.route("/voice", methods=["POST"])
def incoming_call():
    """Handle incoming voice calls — greet and start listening."""
    phone = request.form.get("From", "")

    ensure_user(phone)

    resp = VoiceResponse()
    greeting = "Yo. LockIn Bot here. What did you get done today?"

    # Generate TTS audio for greeting
    audio_url = generate_tts(greeting, request.url_root)
    resp.play(audio_url)

    # Listen for the caller's speech
    gather = Gather(
        input="speech",
        action="/voice/respond",
        method="POST",
        speech_timeout="auto",
        language="en-US",
    )
    resp.append(gather)

    # If no speech detected, prompt again
    resp.redirect("/voice")
    return str(resp), 200, {"Content-Type": "application/xml"}


@app.route("/voice/respond", methods=["POST"])
def voice_respond():
    """Process caller's speech, get AI reply, speak it back."""
    phone = request.form.get("From", "")
    speech_text = request.form.get("SpeechResult", "")

    if not speech_text:
        resp = VoiceResponse()
        resp.say("I didn't catch that. Try again.")
        resp.redirect("/voice")
        return str(resp), 200, {"Content-Type": "application/xml"}

    ensure_user(phone)

    # Detect check-in from speech
    pillar = detect_checkin(speech_text)
    if pillar:
        save_checkin(phone, pillar, "done")

    # Get AI response
    reply_text = get_ai_response(phone, speech_text)

    resp = VoiceResponse()
    audio_url = generate_tts(reply_text, request.url_root)
    resp.play(audio_url)

    # Keep listening for more
    gather = Gather(
        input="speech",
        action="/voice/respond",
        method="POST",
        speech_timeout="auto",
        language="en-US",
    )
    resp.append(gather)

    # If silence, say goodbye
    resp.say("Alright, stay locked in. Peace.")
    return str(resp), 200, {"Content-Type": "application/xml"}


@app.route("/audio/<filename>", methods=["GET"])
def serve_audio(filename):
    """Serve generated TTS audio files."""
    return send_from_directory(AUDIO_DIR, filename)


def generate_tts(text: str, base_url: str) -> str:
    """Generate TTS audio with OpenAI and return a public URL."""
    filename = f"{uuid.uuid4().hex}.mp3"
    filepath = os.path.join(AUDIO_DIR, filename)

    response = tts_client.audio.speech.create(
        model="gpt-4o-mini-tts",
        voice="ash",
        input=text,
        instructions="Speak like a tough but supportive accountability coach. Direct, motivating, no-BS energy.",
        response_format="mp3",
    )
    response.stream_to_file(filepath)

    # Build public URL for Twilio to fetch
    return f"{base_url.rstrip('/')}/audio/{filename}"


if __name__ == "__main__":
    init_db()
    start_scheduler()
    print("🔒 LockIn Bot is running!")
    app.run(host="0.0.0.0", port=5000, debug=False)

