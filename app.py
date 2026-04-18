from __future__ import annotations
import os
import re
import uuid
import tempfile
from flask import Flask, request, send_from_directory
from twilio.twiml.messaging_response import MessagingResponse
from twilio.twiml.voice_response import VoiceResponse, Gather
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

from database import init_db, ensure_user, save_checkin
from bot import get_ai_response
from scheduler import start_scheduler

app = Flask(__name__)
tts_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

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
    phone = request.form.get("From", "")
    body = request.form.get("Body", "").strip()

    ensure_user(phone)

    # Auto-detect and save check-in
    pillar = detect_checkin(body)
    if pillar:
        save_checkin(phone, pillar, "done")

    # Get AI response
    reply_text = get_ai_response(phone, body)

    resp = MessagingResponse()
    resp.message(reply_text)
    return str(resp), 200, {"Content-Type": "application/xml"}


@app.route("/health", methods=["GET"])
def health():
    return "LockIn Bot is running 💪", 200


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

