from app import app
from database import init_db
from scheduler import start_scheduler

init_db()
start_scheduler()

