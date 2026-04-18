import threading
import time
import requests
from app import app
from database import init_db
from scheduler import start_scheduler

init_db()
start_scheduler()


import os

def _startup_ping():
    """Ping health endpoint after boot to confirm everything is up."""
    time.sleep(3)
    try:
        requests.get("http://localhost:5000/health", timeout=5)
    except Exception:
        pass
    # Set up Telegram webhook
    base_url = os.getenv("BASE_URL", "")
    if base_url:
        from app import setup_telegram_webhook
        setup_telegram_webhook(base_url)

threading.Thread(target=_startup_ping, daemon=True).start()
