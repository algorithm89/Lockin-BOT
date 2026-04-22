import os
import logging
from contextlib import contextmanager
import mysql.connector
from mysql.connector import pooling

logger = logging.getLogger("lockinbot")

DB_CONFIG = {
    "host": os.getenv("DB_HOST") or "localhost",
    "port": int(os.getenv("DB_PORT") or "3306"),
    "user": os.getenv("DB_USER") or "",
    "password": os.getenv("DB_PASSWORD") or "",
    "database": os.getenv("DB_NAME") or "lockinbot",
}


def _validate_db_config():
    missing = []
    if not DB_CONFIG["host"]:
        missing.append("DB_HOST")
    if not DB_CONFIG["user"]:
        missing.append("DB_USER")
    if not DB_CONFIG["database"]:
        missing.append("DB_NAME")
    if missing:
        raise RuntimeError(
            f"Missing DB environment variables: {', '.join(missing)}. "
            "Check your .env / GitHub secrets and docker-compose env wiring."
        )


pool = None


def get_pool():
    global pool
    if pool is None:
        pool = pooling.MySQLConnectionPool(
            pool_name="lockin_pool",
            pool_size=10,
            pool_reset_session=True,
            **DB_CONFIG
        )
    return pool


@contextmanager
def get_db():
    """Context manager that always returns connection to pool."""
    conn = get_pool().get_connection()
    try:
        yield conn
    finally:
        try:
            conn.close()
        except Exception:
            pass


def init_db():
    """Create the database (if needed) and all tables."""
    _validate_db_config()
    cfg = {k: v for k, v in DB_CONFIG.items() if k != "database"}
    conn = mysql.connector.connect(**cfg)
    cur = conn.cursor()
    cur.execute(f"CREATE DATABASE IF NOT EXISTS `{DB_CONFIG['database']}` "
                f"CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
    conn.commit()
    cur.close()
    conn.close()

    with get_db() as conn:
        cur = conn.cursor()

        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                phone VARCHAR(20) PRIMARY KEY,
                name VARCHAR(100),
                timezone VARCHAR(50) DEFAULT 'America/Montreal',
                profile TEXT DEFAULT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Add profile column if upgrading from older version
        try:
            cur.execute("ALTER TABLE users ADD COLUMN profile TEXT DEFAULT NULL")
        except Exception:
            pass

        cur.execute("""
            CREATE TABLE IF NOT EXISTS goals (
                id INT AUTO_INCREMENT PRIMARY KEY,
                phone VARCHAR(20) NOT NULL,
                category VARCHAR(20) NOT NULL,
                target VARCHAR(50),
                enabled TINYINT DEFAULT 1,
                FOREIGN KEY (phone) REFERENCES users(phone)
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS check_ins (
                id INT AUTO_INCREMENT PRIMARY KEY,
                phone VARCHAR(20) NOT NULL,
                category VARCHAR(20) NOT NULL,
                status VARCHAR(20),
                note TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (phone) REFERENCES users(phone)
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INT AUTO_INCREMENT PRIMARY KEY,
                phone VARCHAR(20) NOT NULL,
                role VARCHAR(10) NOT NULL,
                content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (phone) REFERENCES users(phone)
            )
        """)

        # Hot-path indexes for faster message/check-in lookups.
        for sql in [
            "CREATE INDEX idx_messages_phone_id ON messages (phone, id)",
            "CREATE INDEX idx_checkins_phone_created_at ON check_ins (phone, created_at)",
        ]:
            try:
                cur.execute(sql)
            except Exception:
                pass  # Index already exists

        conn.commit()
        cur.close()


def save_message(phone: str, role: str, content: str):
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("INSERT INTO messages (phone, role, content) VALUES (%s, %s, %s)",
                    (phone, role, content))
        conn.commit()
        cur.close()


def get_recent_messages(phone: str, limit: int = 20) -> list[dict]:
    with get_db() as conn:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            "SELECT role, content FROM messages WHERE phone = %s ORDER BY id DESC LIMIT %s",
            (phone, limit)
        )
        rows = cur.fetchall()
        cur.close()
    return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]


def get_todays_checkins(phone: str) -> list[dict]:
    with get_db() as conn:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            "SELECT category, status, note, created_at FROM check_ins "
            "WHERE phone = %s AND created_at >= CURDATE() "
            "AND created_at < (CURDATE() + INTERVAL 1 DAY) ORDER BY created_at",
            (phone,)
        )
        rows = cur.fetchall()
        cur.close()
    return rows


def save_checkin(phone: str, category: str, status: str, note: str = ""):
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO check_ins (phone, category, status, note) VALUES (%s, %s, %s, %s)",
            (phone, category, status, note)
        )
        conn.commit()
        cur.close()


def ensure_user(phone: str):
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("INSERT IGNORE INTO users (phone) VALUES (%s)", (phone,))
        conn.commit()
        cur.close()


def get_user_timezone(phone: str) -> str | None:
    with get_db() as conn:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT timezone FROM users WHERE phone = %s", (phone,))
        row = cur.fetchone()
        cur.close()
    return row["timezone"] if row and row["timezone"] else None


def get_user_profile(phone: str) -> str | None:
    with get_db() as conn:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT profile FROM users WHERE phone = %s", (phone,))
        row = cur.fetchone()
        cur.close()
    return row["profile"] if row and row["profile"] else None


def update_user_profile(phone: str, profile: str):
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE users SET profile = %s WHERE phone = %s", (profile, phone))
        conn.commit()
        cur.close()
