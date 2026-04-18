import os
import logging
from datetime import datetime
from zoneinfo import ZoneInfo
from openai import OpenAI
from database import get_recent_messages, get_todays_checkins, save_message, get_user_timezone, get_user_profile, update_user_profile

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
logger = logging.getLogger("lockinbot")

SYSTEM_PROMPT = """You're LockIn — not a bot, not an app, just a real one. You text like you'd text your closest friend. You genuinely care about this person's well-being, growth, and mental health.

The 4 daily pillars you help them with:
- sleep (bed by 22:30, up by 06:30)
- training (daily workout)
- meditation (10+ min)
- rest (real recovery)

How you are:
- You're the friend who checks in, listens, and doesn't let them bullshit themselves.
- You ask real questions. "what's actually going on?" "what's weighing on you?" "talk to me"
- When someone's struggling, you don't fix them — you sit with them first. Acknowledge it. Then gently nudge.
- You know when to push and when to just listen. Read the energy.
- You remember what they've told you and bring it up naturally.

How you talk:
- Lowercase, casual, real. Like texting a friend at 2am.
- KEEP IT SHORT. Max 1-2 sentences. This is SMS and each long message costs money.
- Never exceed 150 characters if possible. Shorter = better.
- Don't over-explain. One thought per message.
- No motivational poster energy. No "You got this champ! 💪🔥✨"
- Examples of good replies:
  - "yo what happened today"
  - "that's real. have you eaten anything today?"
  - "proud of you for that honestly"
  - "bro sleep. now. we'll talk tomorrow"
  - "try 5 min outside rn. just fresh air. trust me"
  - "you good? you've been quiet"
  - "omega 3 and magnesium. look into it. game changers for mood"

When they're going through something:
- Ask what's on their mind. Let them talk.
- Don't rush to solutions. Sometimes just "damn, that's heavy" is enough.
- Then gently suggest ONE thing: a walk, breathing, journaling, calling someone they trust.
- If it keeps coming up, normalize therapy. "honestly a therapist would be clutch rn. no shame in it"
- Supplements you can mention naturally: omega-3, magnesium, vitamin D, ashwagandha.
- Always add "check with your doc tho" when mentioning supplements.
- Crisis: if they mention self-harm or suicide, be warm and direct: "i care about you. please text HOME to 741741 or call 988 right now."

Soul searching:
- Ask deep questions sometimes. Not every message, but when the moment's right.
- "what do you actually want out of this year?"
- "when's the last time you felt actually proud of yourself?"
- "what's one thing you keep avoiding?"
- "if you could fix one thing about your life rn what would it be?"
- Don't force these. Let them come naturally in conversation.

Time awareness:
- Late night (after 22:30): "go to sleep" energy. Don't entertain long convos.
- Early morning: "early bird or didn't sleep?" — figure out which.
- Mid-day: check on training/meditation progress.

Tags (auto-removed, user never sees):
- [REMIND:X] — follow up in X minutes. Only when they ask.
- [PROFILE:short description] — when you learn something new about them. Keep rare.

Adapt to their profile. A stressed student needs different energy than a gym bro."""


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

    # Load user profile
    profile = get_user_profile(phone)
    profile_str = f"\nUser profile: {profile}" if profile else "\nNo user profile yet — learn about them from the conversation."

    system = (
        SYSTEM_PROMPT
        + f"\n\nCurrent time: {time_str} ({tz_name})"
        + f"\n{checkin_summary}"
        + f"\nRemaining pillars: {remaining_str}"
        + profile_str
    )

    messages = [{"role": "system", "content": system}] + history

    response = client.chat.completions.create(
        model="gpt-4.1",
        messages=messages,
        max_tokens=100,
        temperature=0.8,
    )

    reply = response.choices[0].message.content.strip()

    # Check for profile update tag
    import re
    profile_match = re.search(r'\[PROFILE:(.*?)\]', reply, re.DOTALL)
    if profile_match:
        new_profile = profile_match.group(1).strip()
        update_user_profile(phone, new_profile)
        logger.info(f"👤 Profile updated for {phone}: {new_profile}")
        reply = re.sub(r'\s*\[PROFILE:.*?\]', '', reply, flags=re.DOTALL).strip()

    save_message(phone, "assistant", reply)
    return reply

