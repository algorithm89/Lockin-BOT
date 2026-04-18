import os
import mysql.connector
from mysql.connector import pooling

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT") or "3306"),
    "user": os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD", ""),
    "database": os.getenv("DB_NAME", "lockinbot"),
}

pool = None


def get_pool():
    global pool
    if pool is None:
        pool = pooling.MySQLConnectionPool(
            pool_name="lockin_pool",
            pool_size=5,
            **DB_CONFIG
        )
    return pool


def get_db():
    return get_pool().get_connection()


def init_db():
    """Create the database (if needed) and all tables."""
    cfg = {k: v for k, v in DB_CONFIG.items() if k != "database"}
    conn = mysql.connector.connect(**cfg)
    cur = conn.cursor()
    cur.execute(f"CREATE DATABASE IF NOT EXISTS `{DB_CONFIG['database']}` "
                f"CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
    conn.commit()
    cur.close()
    conn.close()

    conn = get_db()
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
        pass  # Column already exists

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

    conn.commit()
    cur.close()
    conn.close()


def save_message(phone: str, role: str, content: str):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("INSERT INTO messages (phone, role, content) VALUES (%s, %s, %s)",
                (phone, role, content))
    conn.commit()
    cur.close()
    conn.close()


def get_recent_messages(phone: str, limit: int = 20) -> list[dict]:
    conn = get_db()
    cur = conn.cursor(dictionary=True)
    cur.execute(
        "SELECT role, content FROM messages WHERE phone = %s ORDER BY id DESC LIMIT %s",
        (phone, limit)
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]


def get_todays_checkins(phone: str) -> list[dict]:
    conn = get_db()
    cur = conn.cursor(dictionary=True)
    cur.execute(
        "SELECT category, status, note, created_at FROM check_ins "
        "WHERE phone = %s AND DATE(created_at) = CURDATE() ORDER BY created_at",
        (phone,)
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows


def save_checkin(phone: str, category: str, status: str, note: str = ""):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO check_ins (phone, category, status, note) VALUES (%s, %s, %s, %s)",
        (phone, category, status, note)
    )
    conn.commit()
    cur.close()
    conn.close()


def ensure_user(phone: str):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("INSERT IGNORE INTO users (phone) VALUES (%s)", (phone,))
    conn.commit()
    cur.close()
    conn.close()


def get_user_timezone(phone: str) -> str | None:
    """Get the user's stored timezone, or None."""
    conn = get_db()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT timezone FROM users WHERE phone = %s", (phone,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    return row["timezone"] if row and row["timezone"] else None


def get_user_profile(phone: str) -> str | None:
    """Get the user's personalized profile."""
    conn = get_db()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT profile FROM users WHERE phone = %s", (phone,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    return row["profile"] if row and row["profile"] else None


def update_user_profile(phone: str, profile: str):
    """Update the user's personalized profile."""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE users SET profile = %s WHERE phone = %s", (profile, phone))
    conn.commit()
    cur.close()
    conn.close()





