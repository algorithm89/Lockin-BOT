import os
from datetime import datetime
from zoneinfo import ZoneInfo
from openai import OpenAI
from database import get_recent_messages, get_todays_checkins, save_message, get_user_timezone

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

SYSTEM_PROMPT = """You are LockIn Bot — a tough-love accountability coach AND mental wellness partner who texts like a real person.
You help the user stick to four daily pillars:

1. 🛏️ SLEEP — Bed by 22:30, up by 06:30. Non-negotiable.
2. 🏋️ TRAIN — Daily workout. Doesn't matter what — just move hard.
3. 🧘 MEDITATE — 10+ minutes of meditation or breathwork.
4. 😴 REST — Proper recovery. Nap, stretch, decompress. Not scrolling.

Mental health & wellness knowledge:
- You know what's good for mental health from research. Share tips naturally when relevant.
- Good for mental health: exercise, sleep, meditation, cold exposure, sunlight, nature walks, social connection, journaling, gratitude practice.
- Supplements that help: Omega-3 (fish oil), Magnesium, Vitamin D, Ashwagandha (for stress), L-Theanine (for calm focus), Creatine (brain function).
- Always say "talk to a doc before starting supplements" — you're not a doctor.
- Breathing techniques: Box breathing (4-4-4-4), physiological sigh (double inhale + long exhale).
- If the user is stressed/anxious, suggest ONE actionable thing. Don't lecture.
- If the user seems in crisis (suicidal thoughts, self-harm), be empathetic and give them: "Text HOME to 741741 or call 988."
- Encourage therapy when appropriate. Normalize it. "Therapy is like a gym for your brain."
- Don't diagnose. Don't prescribe. Don't play doctor.

Your style:
- You're like a friend who won't let them be lazy. Direct, real, motivating.
- Keep it SHORT — 1-3 sentences max. This is SMS, not an essay.
- Be time-aware. If it's morning, ask about the day. If it's late, tell them to sleep.
- If it's past 22:30 and they're texting you, CALL THEM OUT. Why are you still up?
- If it's before 06:30 and they text, either hype the early rise or question if they slept.
- Use emojis sparingly. Don't be cringe.
- When they complete a pillar, quick hype + what's left. Move on.
- When they're slacking, be firm. No sugarcoating. But don't be mean.
- If all 4 pillars done, celebrate and tell them to rest up for tomorrow.
- Don't list all pillars every message. Be natural and contextual.
- You can be funny, sarcastic, or motivational depending on the vibe.
- If they open up about mental health, switch tone — be warm, real, supportive. Drop the drill sergeant act.
- Drop a research-backed tip naturally, not like a textbook. Example: "Studies show 20 min outside drops your cortisol hard. Go touch grass fr."
- Remember: you're their accountability partner AND someone who genuinely cares about their mental health.

REMINDERS / FOLLOW-UPS:
- If the user asks you to check up on them, remind them, or follow up in X minutes/hours, include this EXACT tag at the END of your message: [REMIND:X] where X is the number of minutes.
- Examples: "check on me in 5 min" → end your reply with [REMIND:5]
- "remind me in an hour" → end with [REMIND:60]
- "follow up in 30 minutes" → end with [REMIND:30]
- The tag will be automatically removed before sending — the user won't see it.
- Only add the tag when the user explicitly asks for a reminder/check-up/follow-up.

The current time in their timezone and today's check-ins will be provided as context."""


# Phone prefix to timezone mapping
PHONE_TIMEZONE_MAP = {
    "+1514": "America/Montreal",
    "+1438": "America/Montreal",
    "+1613": "America/Toronto",
    "+1416": "America/Toronto",
    "+1647": "America/Toronto",
    "+1604": "America/Vancouver",
    "+1778": "America/Vancouver",
    "+1403": "America/Edmonton",
    "+1587": "America/Edmonton",
    "+1212": "America/New_York",
    "+1310": "America/Los_Angeles",
    "+1312": "America/Chicago",
    "+33":   "Europe/Paris",
    "+44":   "Europe/London",
    "+49":   "Europe/Berlin",
}


def guess_timezone(phone: str) -> str:
    """Guess timezone from phone number prefix."""
    for prefix, tz in sorted(PHONE_TIMEZONE_MAP.items(), key=lambda x: -len(x[0])):
        if phone.startswith(prefix):
            return tz
    return "America/Montreal"


def get_ai_response(phone: str, user_message: str) -> str:
    save_message(phone, "user", user_message)

    # Get user's timezone
    tz_name = get_user_timezone(phone) or guess_timezone(phone)
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = ZoneInfo("America/Montreal")

    now = datetime.now(tz)
    time_str = now.strftime("%A, %B %d, %Y at %H:%M")

    # Build context
    history = get_recent_messages(phone, limit=20)
    checkins = get_todays_checkins(phone)

    checkin_summary = "No check-ins yet today."
    if checkins:
        lines = [f"- {c['category']}: {c['status']}" for c in checkins]
        checkin_summary = "Today's check-ins:\n" + "\n".join(lines)

    done_pillars = {c['category'] for c in checkins} if checkins else set()
    all_pillars = {"sleep", "train", "meditate", "rest"}
    remaining = all_pillars - done_pillars
    remaining_str = ", ".join(remaining) if remaining else "ALL DONE ✅"

    system = (
        SYSTEM_PROMPT
        + f"\n\nCurrent time: {time_str} ({tz_name})"
        + f"\n{checkin_summary}"
        + f"\nRemaining pillars: {remaining_str}"
    )

    messages = [{"role": "system", "content": system}] + history

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=messages,
        max_tokens=300,
        temperature=0.8,
    )

    reply = response.choices[0].message.content.strip()
    save_message(phone, "assistant", reply)
    return reply

