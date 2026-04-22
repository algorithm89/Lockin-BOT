"""Scheduled reminders — sends Telegram nudges at key times of day."""
import os
import logging
from datetime import datetime
from zoneinfo import ZoneInfo
from apscheduler.schedulers.background import BackgroundScheduler
from database import get_todays_checkins, get_user_timezone
from bot import guess_timezone

logger = logging.getLogger("lockinbot")

_scheduler_instance = None
_tg_bot = None
_tg_chat_id = None


def get_scheduler():
    """Return the running scheduler instance, or None if stale/stopped."""
    if _scheduler_instance and _scheduler_instance.running:
        return _scheduler_instance
    return None


def set_telegram_sender(bot, chat_id: str):
    """Register the Telegram bot + chat_id for scheduled reminders."""
    global _tg_bot, _tg_chat_id
    _tg_bot = bot
    _tg_chat_id = chat_id
    logger.info(f"📱 Telegram reminder target set: chat_id={chat_id}")


REMINDERS = {
    "06:30": "🌅 Rise and shine. Time to lock in. What's the plan today?",
    "10:00": "🏋️ Have you trained yet? No excuses.",
    "14:00": "🧘 Meditation check — have you sat down for 10 min yet?",
    "17:00": "😴 Rest is part of the grind. Take a proper break if you haven't.",
    "22:00": "🛏️ 30 minutes to lights out. Wrap it up and get to bed.",
    "22:30": "🛏️ Lights OUT. Phone down. Sleep. Now.",
}


def send_reminder(body: str):
    if not _tg_bot or not _tg_chat_id:
        logger.info(f"⏰ [REMINDER - no Telegram target] {body}")
        return
    try:
        _tg_bot.send_message(_tg_chat_id, body)
        logger.info(f"✅ Reminder sent to {_tg_chat_id}: \"{body}\"")
    except Exception as e:
        logger.error(f"❌ Reminder send failed: {e}", exc_info=True)


def check_and_remind(time_key: str):
    phone = f"tg_{_tg_chat_id}" if _tg_chat_id else ""
    tz_name = (get_user_timezone(phone) if phone else None) or "America/Montreal"
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = ZoneInfo("America/Montreal")

    now = datetime.now(tz)
    current_time = now.strftime("%H:%M")

    if current_time != time_key:
        return

    checkins = get_todays_checkins(phone) if phone else []
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

    send_reminder(REMINDERS[time_key])


def start_scheduler():
    global _scheduler_instance

    if _scheduler_instance and _scheduler_instance.running:
        return _scheduler_instance

    tz_name = "America/Montreal"
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

