"""Test all connections: MySQL, OpenAI, Telegram."""
import os
import sys
from dotenv import load_dotenv

load_dotenv()

errors = []

# 1. Check env vars
print("🔍 Checking environment variables...")
required = ["OPENAI_API_KEY", "DB_HOST", "DB_USER", "DB_PASSWORD", "DB_NAME"]
for var in required:
    val = os.getenv(var)
    if not val or val.startswith("your_"):
        print(f"  ❌ {var} — missing or placeholder")
        errors.append(var)
    else:
        masked = "***" if var in ("DB_USER", "DB_PASSWORD", "DB_NAME") else val[:8]
        print(f"  ✅ {var} — set ({masked}...)")

# 2. Test MySQL
print("\n🔍 Testing MySQL connection...")
try:
    import mysql.connector
    conn = mysql.connector.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT") or "3306"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME"),
    )
    cur = conn.cursor()
    cur.execute("SELECT 1")
    cur.fetchone()
    cur.execute("SHOW TABLES")
    tables = [t[0] for t in cur.fetchall()]
    print(f"  ✅ MySQL connected — database: ***")
    print(f"  📋 Tables: {', '.join(tables) if tables else 'none (will be created on first run)'}")
    cur.close()
    conn.close()
except Exception as e:
    print(f"  ❌ MySQL failed: {e}")
    errors.append("MySQL")

# 3. Test OpenAI
print("\n🔍 Testing OpenAI API...")
try:
    from openai import OpenAI
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    response = client.chat.completions.create(
        model="gpt-4.1",
        messages=[{"role": "user", "content": "say ok"}],
        max_tokens=5,
    )
    reply = response.choices[0].message.content.strip()
    print(f"  ✅ OpenAI connected — model: gpt-4.1, reply: \"{reply}\"")
except Exception as e:
    print(f"  ❌ OpenAI failed: {e}")
    errors.append("OpenAI")

# 4. Test Telegram Bot
print("\n🔍 Testing Telegram Bot...")
tg_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
if not tg_token:
    print("  ⚠️  TELEGRAM_BOT_TOKEN — not set (Telegram disabled)")
else:
    try:
        import requests as req
        resp = req.get(f"https://api.telegram.org/bot{tg_token}/getMe", timeout=10)
        data = resp.json()
        if data.get("ok"):
            bot_info = data["result"]
            print(f"  ✅ Telegram connected — @{bot_info['username']} (id: {str(bot_info['id'])[:6]}***)")
            resp2 = req.get(f"https://api.telegram.org/bot{tg_token}/getWebhookInfo", timeout=10)
            wh = resp2.json().get("result", {})
            wh_url = wh.get("url", "")
            if wh_url:
                print(f"  🔗 Webhook: ***/{wh_url.split('/')[-1]}")
                last_err = wh.get("last_error_message", "")
                if last_err:
                    print(f"  ⚠️  Last error: {last_err}")
            else:
                print("  ⚠️  No webhook set!")
        else:
            print(f"  ❌ Telegram failed: {data}")
            errors.append("Telegram")
    except Exception as e:
        print(f"  ❌ Telegram failed: {e}")
        errors.append("Telegram")

# 5. Check BASE_URL
print("\n🔍 Checking BASE_URL...")
base_url = os.getenv("BASE_URL", "")
if base_url:
    print(f"  ✅ BASE_URL — ***")
else:
    print("  ⚠️  BASE_URL — not set (Telegram webhook auto-setup disabled)")

# Summary
print("\n" + "=" * 40)
if errors:
    print(f"❌ {len(errors)} issue(s): {', '.join(errors)}")
    sys.exit(1)
else:
    print("✅ All systems go! LockIn Bot is ready.")
    sys.exit(0)

