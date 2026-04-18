"""Scheduled reminders — sends nudges at key times of day."""
import os
import logging
from datetime import datetime
from zoneinfo import ZoneInfo
from twilio.rest import Client
from apscheduler.schedulers.background import BackgroundScheduler
from database import get_todays_checkins, get_user_timezone
from bot import guess_timezone

logger = logging.getLogger("lockinbot")

_scheduler_instance = None


def get_scheduler():
    """Return the running scheduler instance."""
    return _scheduler_instance

twilio_client = Client(os.getenv("TWILIO_ACCOUNT_SID"), os.getenv("TWILIO_AUTH_TOKEN"))
FROM = os.getenv("TWILIO_PHONE_NUMBER")
TO = os.getenv("MY_PHONE_NUMBER")

REMINDERS = {
    "06:30": "🌅 Rise and shine. Time to lock in. What's the plan today?",
    "10:00": "🏋️ Have you trained yet? No excuses.",
    "14:00": "🧘 Meditation check — have you sat down for 10 min yet?",
    "17:00": "😴 Rest is part of the grind. Take a proper break if you haven't.",
    "22:00": "🛏️ 30 minutes to lights out. Wrap it up and get to bed.",
    "22:30": "🛏️ Lights OUT. Phone down. Sleep. Now.",
}


def send_sms(body: str):
    if not TO or TO == "your_phone_number_here":
        logger.info(f"⏰ [REMINDER - no recipient] {body}")
        return
    logger.info(f"⏰ Sending reminder to {TO}: \"{body}\"")
    twilio_client.messages.create(body=body, from_=FROM, to=TO)
    logger.info(f"✅ Reminder sent to {TO}")


def check_and_remind(time_key: str):
    tz_name = (get_user_timezone(TO) if TO else None) or guess_timezone(TO or "")
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = ZoneInfo("America/Montreal")

    now = datetime.now(tz)
    current_time = now.strftime("%H:%M")

    if current_time != time_key:
        return

    checkins = get_todays_checkins(TO) if TO else []
    done_categories = {c["category"] for c in checkins}

    pillar_map = {
        "06:30": None,
        "10:00": "train",
        "14:00": "meditate",
        "17:00": "rest",
        "22:00": "sleep",
        "22:30": "sleep",
    }
    pillar = pillar_map.get(time_key)
    if pillar and pillar in done_categories:
        logger.info(f"⏭️ Skipping {time_key} reminder — {pillar} already done")
        return

    send_sms(REMINDERS[time_key])


def start_scheduler():
    global _scheduler_instance
    tz_name = (get_user_timezone(TO) if TO else None) or guess_timezone(TO or "")
    logger.info(f"⏰ Starting scheduler with timezone: {tz_name}")
    scheduler = BackgroundScheduler(timezone=tz_name)
    for time_key in REMINDERS:
        h, m = time_key.split(":")
        scheduler.add_job(
            check_and_remind, "cron",
            hour=int(h), minute=int(m),
            args=[time_key],
            id=f"reminder_{time_key}",
        )
        logger.info(f"  📅 Scheduled reminder at {time_key}")
    scheduler.start()
    _scheduler_instance = scheduler
    return scheduler

