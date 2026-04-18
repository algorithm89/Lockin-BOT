"""Scheduled reminders — sends nudges at key times of day."""
import os
from twilio.rest import Client
from apscheduler.schedulers.background import BackgroundScheduler
from database import get_todays_checkins

twilio_client = Client(os.getenv("TWILIO_ACCOUNT_SID"), os.getenv("TWILIO_AUTH_TOKEN"))
FROM = os.getenv("TWILIO_PHONE_NUMBER")
TO = os.getenv("MY_PHONE_NUMBER")

REMINDERS = {
    "06:30": "🌅 Rise and shine. Time to lock in. What's the plan today?",
    "10:00": "🏋️ Have you trained yet? No excuses.",
    "14:00": "🧘 Meditation check — have you sat down for 10 min yet?",
    "17:00": "😴 Rest is part of the grind. Take a proper break if you haven't.",
    "22:00": "🛏️ 30 minutes to lights out. Wrap it up and get to bed.",
}


def send_sms(body: str):
    if not TO or TO == "your_phone_number_here":
        print(f"[REMINDER] {body}")
        return
    twilio_client.messages.create(body=body, from_=FROM, to=TO)


def check_and_remind(time_key: str):
    checkins = get_todays_checkins(TO) if TO else []
    done_categories = {c["category"] for c in checkins}

    # Skip reminder if relevant pillar already done
    pillar_map = {
        "06:30": None,  # always send morning
        "10:00": "train",
        "14:00": "meditate",
        "17:00": "rest",
        "22:00": "sleep",
    }
    pillar = pillar_map.get(time_key)
    if pillar and pillar in done_categories:
        return

    send_sms(REMINDERS[time_key])


def start_scheduler():
    scheduler = BackgroundScheduler(timezone="America/Montreal")
    for time_key in REMINDERS:
        h, m = time_key.split(":")
        scheduler.add_job(
            check_and_remind, "cron",
            hour=int(h), minute=int(m),
            args=[time_key],
            id=f"reminder_{time_key}",
        )
    scheduler.start()
    return scheduler

