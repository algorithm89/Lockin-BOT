# 🔒 LockIn Bot — Your AI Accountability Partner

> **"Stop being a lazy bitch. I say that with love."**

LockIn Bot is an AI-powered accountability partner that keeps you on track with your daily habits through **SMS** and **Telegram**. It combines the personality of a tough-love best friend with research-backed mental health knowledge. It texts you, checks in on you, roasts you when you're slacking, and genuinely helps when life gets heavy.

---

## 📸 How It Looks In Action

```
You:    "I skipped the gym today"
LockIn: "bro you said you'd train today. it's 8pm. what happened?
         nobody FEELS like it. discipline > motivation. get your shoes on,
         do 10 minutes. that's it."

You:    "I've been feeling really down lately"
LockIn: "damn, that's real. i hear you. what's actually going on?
         no rush — just talk to me."

You:    "remind me in 5 minutes to stretch"
LockIn: "got it. i'll check back in 5."
         ... 5 minutes later ...
LockIn: "⏰ Time's up! What did you get done? Check in with me."

You:    "just finished meditating"
LockIn: "yo you actually did it?? that's legit. your prefrontal cortex is
         literally thanking you rn. how long did you sit for?"
```

---

## 🏗️ Architecture Overview

```
┌──────────────────────────────────────────────────────────┐
│                        USER                              │
│              (SMS / Telegram / Voice Call)                │
└──────────────┬───────────────────────┬───────────────────┘
               │                       │
               ▼                       ▼
┌──────────────────────┐  ┌──────────────────────┐
│   Twilio (SMS/Voice) │  │   Telegram Bot API   │
│   Webhook POST       │  │   Webhook POST       │
│   /sms  /voice       │  │   /telegram          │
└──────────┬───────────┘  └──────────┬───────────┘
           │                         │
           ▼                         ▼
┌──────────────────────────────────────────────────────────┐
│                     NGINX (Reverse Proxy)                │
│              bublikstudios.net → localhost:5000           │
└──────────────────────────┬───────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────┐
│                  Flask App (Gunicorn)                     │
│                   Port 5000 (Docker)                      │
│                                                          │
│  ┌─────────┐  ┌─────────┐  ┌───────────┐  ┌──────────┐ │
│  │ app.py  │  │ bot.py  │  │database.py│  │scheduler │ │
│  │ Routes  │  │ AI Brain│  │  MySQL    │  │  Cron    │ │
│  │ Webhook │──│ OpenAI  │──│  Storage  │  │ Reminders│ │
│  │ Handler │  │ GPT-4.1 │  │  Pool     │  │ APSched  │ │
│  └─────────┘  └─────────┘  └───────────┘  └──────────┘ │
└──────────────────────────────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────┐
│                    MySQL Database                        │
│                                                          │
│  ┌─────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐ │
│  │ users   │  │ messages │  │check_ins │  │  goals   │ │
│  │ phone   │  │ phone    │  │ phone    │  │ phone    │ │
│  │ profile │  │ role     │  │ category │  │ category │ │
│  │ timezone│  │ content  │  │ status   │  │ target   │ │
│  └─────────┘  └──────────┘  └──────────┘  └──────────┘ │
└──────────────────────────────────────────────────────────┘
```

---

## 📂 Project Structure

```
LockInBot/
├── app.py                  # Flask routes (SMS, Telegram, Voice webhooks)
├── bot.py                  # AI brain — system prompt + OpenAI integration
├── database.py             # MySQL connection pool, tables, CRUD operations
├── scheduler.py            # APScheduler — timed reminders (6:30am, 10pm, etc.)
├── wsgi.py                 # Gunicorn entry point — boots everything up
├── test_connections.py     # Health check script — tests all APIs
├── requirements.txt        # Python dependencies
├── Dockerfile              # Container build
├── docker-compose.yml      # Container orchestration
├── .github/
│   └── workflows/
│       └── deploy.yml      # CI/CD — auto-deploy on push to main
└── deployment/
    ├── lockinbot.service    # Systemd unit (non-Docker deployments)
    ├── lockinbot.nginx      # Nginx config snippet
    └── README.md            # Deployment notes
```

---

## ⚙️ How Each File Works

### `app.py` — The Web Server (Routes & Webhooks)

This is the entry point for all incoming messages. It runs as a Flask web app behind Gunicorn.

**SMS Webhook (`POST /sms`)**
```python
@app.route("/sms", methods=["POST"])
def incoming_sms():
    phone = request.form.get("From", "")     # e.g. "+15149539447"
    body = request.form.get("Body", "").strip() # e.g. "I just trained"

    # Process in background so Twilio doesn't time out (15s limit)
    threading.Thread(target=_process_and_reply, args=(phone, body)).start()

    # Return empty TwiML immediately
    return str(MessagingResponse()), 200
```

When you text the Twilio number, Twilio sends a POST request to `/sms` with `From` (your phone) and `Body` (your message). The app:
1. Returns an empty response instantly (Twilio has a 15s timeout)
2. Processes the message in a background thread
3. Sends the AI reply back via Twilio's API

**Telegram Webhook (`POST /telegram`)**
```python
@app.route("/telegram", methods=["POST"])
def telegram_webhook():
    json_data = request.get_json(force=True)
    update = telebot.types.Update.de_json(json_data)

    if update.message and update.message.text:
        threading.Thread(target=_process_telegram, args=(update.message,)).start()
    return "ok", 200
```

When you message `@LockinAccountabilityBot` on Telegram, the Telegram Bot API sends a POST request to `/telegram`. Same flow — parse, background thread, reply.

**Auto Check-In Detection**
```python
PILLAR_KEYWORDS = {
    "sleep":    ["sleep", "slept", "bed", "woke", "wake"],
    "train":    ["train", "trained", "workout", "gym", "ran", "run", "lift"],
    "meditate": ["meditate", "meditated", "meditation", "breathwork"],
    "rest":     ["rest", "rested", "nap", "napped", "recovery", "stretched"],
}
```

If your message contains pillar keywords + positive signals ("done", "did", "just"), it auto-logs a check-in to the database. So texting "just finished training" automatically marks your `train` pillar as done.

**Follow-Up Reminders**

When the AI includes `[REMIND:5]` in its response (you never see this tag), the app schedules a one-time SMS/Telegram message in 5 minutes using APScheduler:

```python
def schedule_followup(phone, minutes):
    run_at = datetime.now(tz) + timedelta(minutes=minutes)
    scheduler.add_job(send_followup, trigger='date', run_date=run_at)
```

---

### `bot.py` — The AI Brain

This is where the magic happens. It manages the OpenAI GPT-4.1 conversation.

**System Prompt** — A massive, carefully crafted prompt that defines the bot's personality:
- Tough love ("stop being a lazy bitch")
- Research-backed advice (cites real studies from JAMA, Lancet, Harvard)
- Mental health awareness (supplements, journaling, therapy normalization)
- Crisis protocol (Canadian helplines: 9-8-8, text HELLO to 686868)
- Time-aware behavior (bedtime enforcement after 22:30)

**Context Building** — Every message includes:
```python
system = (
    SYSTEM_PROMPT
    + f"\nCurrent time: {time_str} ({tz_name})"     # Time awareness
    + f"\n{checkin_summary}"                          # Today's progress
    + f"\nRemaining pillars: {remaining_str}"         # What's left to do
    + profile_str                                     # What we know about the user
)

messages = [{"role": "system", "content": system}] + history  # Last 20 messages
```

So the AI knows:
- What time it is (to enforce bedtime, check pillars)
- What you've done today (to celebrate or push)
- Your conversation history (to remember context)
- Your profile (interests, struggles, personality)

**Profile Learning** — The AI can tag `[PROFILE:stressed college student, studies CS]` in its response. The app strips the tag and saves it to the database. Next conversation, the AI adapts its personality.

**OpenAI Call:**
```python
response = client.chat.completions.create(
    model="gpt-4.1",
    messages=messages,
    max_tokens=200,        # ~2-4 sentences
    temperature=0.8,       # Creative but not random
)
```

---

### `database.py` — MySQL Storage

Uses a connection pool (10 connections) for performance. Four tables:

| Table | Purpose | Key Columns |
|-------|---------|-------------|
| `users` | Registered users | `phone`, `timezone`, `profile` |
| `messages` | Full conversation history | `phone`, `role` (user/assistant), `content` |
| `check_ins` | Daily pillar tracking | `phone`, `category` (sleep/train/etc), `status` |
| `goals` | Custom goals per user | `phone`, `category`, `target` |

**Connection Pool Pattern:**
```python
@contextmanager
def get_db():
    conn = get_pool().get_connection()
    try:
        yield conn
    finally:
        conn.close()  # Returns to pool, doesn't actually close

# Usage:
with get_db() as conn:
    cur = conn.cursor()
    cur.execute("INSERT INTO messages ...")
```

---

### `scheduler.py` — Timed Reminders

Uses APScheduler to send SMS reminders at fixed times:

| Time | Reminder |
|------|----------|
| 06:30 | 🌅 Rise and shine. What's the plan today? |
| 10:00 | 🏋️ Have you trained yet? No excuses. |
| 14:00 | 🧘 Meditation check — have you sat for 10 min? |
| 17:00 | 😴 Rest is part of the grind. Take a break. |
| 22:00 | 🛏️ 30 minutes to lights out. Wrap it up. |
| 22:30 | 🛏️ Lights OUT. Phone down. Sleep. Now. |

**Smart reminders** — it checks what you've already done today and skips pillars you've completed:

```python
def check_and_remind(time_key):
    checkins = get_todays_checkins(TO)
    done_categories = {c["category"] for c in checkins}

    # Only send if the pillar for this time slot isn't done yet
    if pillar and pillar in done_categories:
        return  # Already done, skip
    send_sms(REMINDERS[time_key])
```

---

### `wsgi.py` — Boot Sequence

```python
from app import app
from database import init_db
from scheduler import start_scheduler

init_db()           # Create database + tables if needed
start_scheduler()   # Start APScheduler for timed reminders

# Background: ping health + set up Telegram webhook
threading.Thread(target=_startup_ping, daemon=True).start()
```

---

## 🧠 The 4 Pillars (Research-Backed)

| Pillar | Why It Matters | Science |
|--------|---------------|---------|
| **Sleep** (22:30–06:30) | Repairs brain, regulates emotions, builds muscle | Matthew Walker: sleep deprivation impairs prefrontal cortex, tanks testosterone. Blue light suppresses melatonin by 58% (Harvard). |
| **Training** (daily) | Grows new brain cells, crushes depression | Exercise releases BDNF. 2018 Lancet study (1.2M people): exercise reduced mental health burden by 43%. |
| **Meditation** (10+ min) | Reduces anxiety, improves focus | 8-week MBSR increases gray matter in hippocampus (Hölzel et al., 2011). Reduces cortisol. |
| **Rest** (active recovery) | Prevents burnout, lowers inflammation | 10 min in nature drops cortisol by 16% (Frontiers in Psychology, 2019). |

---

## 💊 Supplements the Bot Recommends

| Supplement | Dose | What It Does | Source |
|-----------|------|-------------|--------|
| Omega-3 (EPA/DHA) | 1-2g/day | Antidepressant effect, reduces inflammation | Translational Psychiatry meta-analysis |
| Magnesium (glycinate) | 200-400mg before bed | Sleep, anxiety, muscle recovery | 70%+ of people are deficient |
| Vitamin D | 2000-4000 IU/day | Mood, immunity, energy | Linked to depression when low |
| Ashwagandha (KSM-66) | 600mg/day | Reduces cortisol by 30% | Clinical studies on stress/anxiety |
| L-theanine | 200mg | Calm focus without drowsiness | Pairs with caffeine |
| Creatine | 5g/day | Cognitive function + emerging mood support | Not just for gym bros |

> ⚠️ The bot always says "check with your doc" when mentioning supplements.

---

## 🚀 Deployment Pipeline (CI/CD)

```
Push to main → GitHub Actions → Self-hosted runner → Docker build → Deploy
```

**Flow:**
1. You push code to `main` branch
2. GitHub Actions triggers on the self-hosted runner (`lockinbot`)
3. Pipeline creates `.env` from GitHub Secrets
4. `docker compose down` → `docker compose up -d --build`
5. Runs `test_connections.py` to verify MySQL, OpenAI, Twilio, Telegram
6. Sets Telegram webhook via API
7. Cleans up `.env` file (secrets don't stay on disk)

**deploy.yml:**
```yaml
- name: Deploy
  run: |
    docker compose down || true
    docker compose up -d --build

- name: Test connections
  run: docker exec lockinbot python test_connections.py

- name: Set Telegram webhook
  run: |
    curl -s "https://api.telegram.org/bot${TOKEN}/setWebhook?url=${BASE}/telegram"
```

---

## 💰 Cost Breakdown

### OpenAI API (GPT-4.1)

| Component | Cost |
|-----------|------|
| Input tokens (system prompt + history) | ~$0.002/message |
| Output tokens (bot reply, ~200 tokens) | ~$0.003/message |
| **Per message round-trip** | **~$0.005** |
| **100 messages/month** | **~$0.50** |
| **500 messages/month** | **~$2.50** |

### Twilio SMS (Canadian numbers)

| Component | Cost |
|-----------|------|
| Inbound SMS | ~$0.0083/segment |
| Outbound SMS | ~$0.0083/segment |
| Segment = 160 characters | 1-2 segments per message |
| **Per round-trip (in + out)** | **~$0.016-0.033** |
| **100 messages/month** | **~$1.60-3.30** |
| Phone number rental | $1.15/month |

### Telegram — **FREE** 🎉

| Component | Cost |
|-----------|------|
| All messages | $0.00 |
| No limits | $0.00 |
| Typing indicators | $0.00 |
| **Unlimited messages/month** | **$0.00** |

### Total Monthly Estimate

| Usage Level | OpenAI | Twilio SMS | Telegram | Total |
|------------|--------|-----------|----------|-------|
| Light (50 msgs) | $0.25 | $1.65 | Free | ~$1.90 |
| Medium (200 msgs) | $1.00 | $4.45 | Free | ~$5.45 |
| Heavy (500 msgs) | $2.50 | $9.30 | Free | ~$11.80 |
| Telegram only (500) | $2.50 | $1.15 (number) | Free | ~$3.65 |

> 💡 **Pro tip:** Use Telegram for daily chatting (free), keep SMS for scheduled reminders only.

---

## 🛠️ Setup Guide

### Prerequisites
- Python 3.12+
- MySQL 8.0+
- Twilio account + phone number
- OpenAI API key (with billing)
- Telegram Bot (via @BotFather)
- Server with Docker

### 1. Clone & Configure
```bash
git clone https://github.com/algorithm89/Lockin-BOT.git
cd Lockin-BOT
```

### 2. Create `.env`
```env
OPENAI_API_KEY=sk-proj-...
DB_HOST=localhost
DB_PORT=3306
DB_USER=bublik
DB_PASSWORD=your_password
DB_NAME=lockinbot
TWILIO_ACCOUNT_SID=AC...
TWILIO_AUTH_TOKEN=...
TWILIO_PHONE_NUMBER=+14389059600
MY_PHONE_NUMBER=+15149539447
TELEGRAM_BOT_TOKEN=8658263306:AAG...
BASE_URL=https://yourdomain.com
```

### 3. Deploy with Docker
```bash
docker compose up -d --build
```

### 4. Set Webhooks
**Twilio:** Set SMS webhook URL to `https://yourdomain.com/sms` (POST)

**Telegram:**
```bash
curl "https://api.telegram.org/bot<TOKEN>/setWebhook?url=https://yourdomain.com/telegram"
```

### 5. Verify
```bash
docker exec lockinbot python test_connections.py
```

---

## 🧰 Tech Stack

| Component | Technology | Why |
|-----------|-----------|-----|
| Language | Python 3.12 | Fast development, great AI/API ecosystem |
| Web Framework | Flask + Gunicorn | Lightweight, battle-tested |
| AI Model | OpenAI GPT-4.1 | Best balance of quality and cost |
| SMS/Voice | Twilio | Industry standard, Canadian numbers |
| Chat | Telegram Bot API | Free, unlimited, typing indicators |
| Database | MySQL 8.0 | Reliable, familiar, connection pooling |
| Scheduler | APScheduler | In-process cron jobs, no extra service |
| Container | Docker + Compose | Reproducible deploys |
| CI/CD | GitHub Actions | Auto-deploy on push |
| Reverse Proxy | Nginx | SSL termination, routing |

---

## 🔒 Crisis Protocol

If a user mentions self-harm or suicide, the bot immediately shifts tone — no jokes, no tough love — and provides Canadian crisis resources:

- **9-8-8** — Canada's Suicide Crisis Helpline (call or text, 24/7)
- **Text HELLO to 686868** — Kids Help Phone (works for all ages)

---

## 📄 License

Built with ❤️ and tough love by [@algorithm89](https://github.com/algorithm89)

