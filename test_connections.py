"""Test all connections: MySQL, OpenAI, Twilio."""
import os
import sys
from dotenv import load_dotenv

load_dotenv()

errors = []

# 1. Check env vars
print("🔍 Checking environment variables...")
required = ["OPENAI_API_KEY", "DB_HOST", "DB_USER", "DB_PASSWORD", "DB_NAME",
            "TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_PHONE_NUMBER", "MY_PHONE_NUMBER"]
for var in required:
    val = os.getenv(var)
    if not val or val.startswith("your_"):
        print(f"  ❌ {var} — missing or placeholder")
        errors.append(var)
    else:
        print(f"  ✅ {var} — set ({val[:8]}...)")

# 2. Test MySQL
print("\n🔍 Testing MySQL connection...")
try:
    import mysql.connector
    conn = mysql.connector.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "3306")),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME"),
    )
    cur = conn.cursor()
    cur.execute("SELECT 1")
    cur.fetchone()
    cur.execute("SHOW TABLES")
    tables = [t[0] for t in cur.fetchall()]
    print(f"  ✅ MySQL connected — database: {os.getenv('DB_NAME')}")
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

# 4. Test Twilio
print("\n🔍 Testing Twilio credentials...")
try:
    from twilio.rest import Client
    client = Client(os.getenv("TWILIO_ACCOUNT_SID"), os.getenv("TWILIO_AUTH_TOKEN"))
    account = client.api.accounts(os.getenv("TWILIO_ACCOUNT_SID")).fetch()
    print(f"  ✅ Twilio connected — account: {account.friendly_name}, status: {account.status}")
    print(f"  📱 From: {os.getenv('TWILIO_PHONE_NUMBER')} → To: {os.getenv('MY_PHONE_NUMBER')}")
except Exception as e:
    print(f"  ❌ Twilio failed: {e}")
    errors.append("Twilio")

# Summary
print("\n" + "=" * 40)
if errors:
    print(f"❌ {len(errors)} issue(s): {', '.join(errors)}")
    sys.exit(1)
else:
    print("✅ All systems go! LockIn Bot is ready.")
    sys.exit(0)

