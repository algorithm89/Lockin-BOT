import os
from openai import OpenAI
from database import get_recent_messages, get_todays_checkins, save_message

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

SYSTEM_PROMPT = """You are LockIn Bot — a tough-love accountability coach over text message.
Your job is to help the user stick to four daily pillars:

1. 🛏️ SLEEP — Go to bed on time (target: 22:30) and wake up on time (target: 06:30).
2. 🏋️ TRAIN — Complete a workout every day (any movement counts, but push hard).
3. 🧘 MEDITATE — At least 10 minutes of meditation or breathwork.
4. 😴 REST — Take a proper rest/recovery period (nap, stretching, or just doing nothing).

Personality:
- You are direct, no-BS, motivating. Think David Goggins meets a supportive friend.
- Keep messages SHORT (SMS-length, 1-3 sentences max).
- Use emojis sparingly but effectively.
- If they completed something, hype them up briefly then move on.
- If they're slacking, call them out firmly but not cruelly.
- If they check in, log it and remind them what's left for the day.
- You can ask what they've done today or nudge them toward the next pillar.

When the user reports completing a pillar, respond with a confirmation and mention what's remaining.
If all 4 are done, celebrate and tell them to lock in again tomorrow.

Keep the conversation natural. Don't repeat the full list every message — be contextual.
Today's check-ins so far will be provided as context."""


def get_ai_response(phone: str, user_message: str) -> str:
    save_message(phone, "user", user_message)

    # Build context
    history = get_recent_messages(phone, limit=20)
    checkins = get_todays_checkins(phone)

    checkin_summary = "No check-ins yet today."
    if checkins:
        lines = [f"- {c['category']}: {c['status']}" for c in checkins]
        checkin_summary = "Today's check-ins:\n" + "\n".join(lines)

    system = SYSTEM_PROMPT + f"\n\n{checkin_summary}"

    messages = [{"role": "system", "content": system}] + history

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        max_tokens=200,
        temperature=0.8,
    )

    reply = response.choices[0].message.content.strip()
    save_message(phone, "assistant", reply)
    return reply

