from app import app
from database import init_db

init_db()

# Scheduler is started inside the app on first request — see app.py
