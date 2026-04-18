import threading
import time
import requests
from app import app
from database import init_db
from scheduler import start_scheduler

init_db()
start_scheduler()


def _startup_ping():
    """Ping health endpoint after boot to confirm everything is up."""
    time.sleep(3)
    try:
        requests.get("http://localhost:5000/health", timeout=5)
    except Exception:
        pass

threading.Thread(target=_startup_ping, daemon=True).start()
