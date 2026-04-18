# 🔒 LockIn Bot — Architecture & Cost Guide

## What is LockIn Bot?

LockIn Bot is your **personal AI accountability coach** that talks to you via SMS and phone calls. It helps you stick to 4 daily pillars: **Sleep, Train, Meditate, and Rest** — and also supports your **mental health** with research-backed tips.

You text a phone number, and an AI coach texts you back. It also sends you **scheduled reminders** throughout the day to keep you on track.

---

## 🏗️ How It Works — Architecture

```
┌─────────────┐         ┌──────────────┐         ┌─────────────────┐
│             │  SMS/    │              │ Webhook  │                 │
│  Your Phone │────────▶│   Twilio      │────────▶│  LockIn Bot     │
│  📱         │◀────────│   ☁️          │◀────────│  (Flask/Python) │
│             │  Reply   │              │ TwiML    │  Port 5000      │
└─────────────┘         └──────────────┘         └────────┬────────┘
                                                          │
                                    ┌─────────────────────┼──────────────────┐
                                    │                     │                  │
                              ┌─────▼─────┐       ┌──────▼──────┐   ┌──────▼──────┐
                              │  OpenAI   │       │   MySQL     │   │  Scheduler  │
                              │  GPT-4o   │       │   Database  │   │  (APSched)  │
                              │  🧠       │       │   💾        │   │  ⏰         │
                              └───────────┘       └─────────────┘   └─────────────┘
```

### Flow: You Send a Text

```
1. You text "(438) 905-9600"
   │
2. Twilio receives your SMS
   │
3. Twilio sends a POST request (webhook) to:
   │  https://bublikstudios.net/sms
   │
4. Nginx (reverse proxy) forwards to Flask app on port 5000
   │
5. Flask app (/sms endpoint):
   │
   ├── a) Saves your phone number (ensure_user)
   │
   ├── b) Auto-detects if your message is a check-in
   │      "Just finished my workout" → detects "train" ✅
   │
   ├── c) Builds context for GPT-4o:
   │      - System prompt (personality + mental health tips)
   │      - Current time in YOUR timezone (auto-detected from phone #)
   │      - Today's check-ins (what you've done / what's left)
   │      - Last 20 messages (conversation history)
   │
   ├── d) Sends all context to OpenAI GPT-4o
   │
   ├── e) Gets AI response back
   │
   ├── f) Saves both your message and the reply to MySQL
   │
   └── g) Returns TwiML XML response to Twilio
          │
6. Twilio sends the reply back to your phone as SMS
   │
7. You receive: "💪 Workout done! That's 1/4. Meditation next?"
```

### Flow: Scheduled Reminders

```
┌─────────────────────────────────────────────────┐
│  APScheduler (runs inside the Flask app)        │
│                                                 │
│  06:30 → "🌅 Rise and shine. Lock in."          │
│  10:00 → "🏋️ Have you trained yet?"             │
│  14:00 → "🧘 Meditation check"                  │
│  17:00 → "😴 Rest time"                         │
│  22:00 → "🛏️ 30 min to lights out"              │
│  22:30 → "🛏️ Lights OUT. Phone down. Sleep."    │
│                                                 │
│  ⚡ Skips reminder if pillar already done today  │
│  🌍 Uses YOUR timezone (auto-detected)          │
└──────────────────────┬──────────────────────────┘
                       │
                       ▼
              Twilio sends SMS
                       │
                       ▼
                  Your phone 📱
```

### Flow: Voice Call

```
1. You call (438) 905-9600
   │
2. Twilio sends POST to /voice
   │
3. Bot greets you with AI-generated voice (OpenAI TTS)
   │
4. You speak → Twilio transcribes (speech-to-text)
   │
5. Bot processes your words same as SMS
   │
6. Bot responds with AI-generated voice
   │
7. Conversation continues until you hang up
```

---

## 🧠 AI Brain — What Makes It Smart

### Timezone Awareness
```
Your phone: +1-514-xxx-xxxx
             └─┬─┘
               │
     Detected: America/Montreal
               │
     Bot knows: "It's Friday, April 18 at 23:45"
               │
     Response: "Bro it's almost midnight. Why are you still up? 🛏️"
```

### Check-In Detection
```
You text: "just did a 5k run"
           │        │
           │        └── keyword: "run" → pillar: TRAIN
           └── positive signal: "just did"
           
Result: Auto-logged as train ✅
Bot: "5K? That's elite. 3 pillars left — meditate, rest, sleep."
```

### Mental Health Mode
```
You text: "feeling really anxious today"
           │
           └── Bot switches from drill sergeant → supportive friend
           
Bot: "Hey, I hear you. Try box breathing — 4 seconds in, 
      4 hold, 4 out, 4 hold. Research shows it calms your 
      nervous system in under 2 minutes. You got this. 💙"
```

---

## 📁 Project Structure

```
LockIn-BOT/
├── app.py           # Flask web server — handles SMS/voice webhooks
├── bot.py           # AI brain — system prompt, GPT-4o calls, timezone logic
├── database.py      # MySQL — users, messages, check-ins, goals
├── scheduler.py     # Timed reminders via APScheduler + Twilio
├── wsgi.py          # Gunicorn entry point
├── requirements.txt # Python dependencies
├── .env             # Secrets (API keys, DB credentials) — NOT in git
└── deployment/
    ├── lockinbot.service  # Systemd service file
    ├── lockinbot.nginx    # Nginx config (reference)
    └── README.md          # Deployment guide
```

---

## 💰 Costs — What You'll Pay Monthly

### OpenAI (AI Responses)

| | GPT-4o (current) | GPT-4o-mini (budget) |
|---|---|---|
| Cost per message | ~$0.006 | ~$0.0004 |
| 10 msgs/day (300/mo) | **$1.80/mo** | $0.12/mo |
| 30 msgs/day (900/mo) | **$5.40/mo** | $0.36/mo |
| 100 msgs/day (3000/mo) | **$18.00/mo** | $1.20/mo |

*Each "message" = your text + bot's reply. Includes system prompt (~600 tokens), conversation history (~500-2000 tokens), and reply (~100 tokens).*

### Twilio (SMS Delivery)

| Item | Cost |
|---|---|
| Phone number rental | **$1.15/mo** |
| Outbound SMS (per msg) | $0.0079 |
| Inbound SMS (per msg) | $0.0079 |
| 6 reminders/day (180/mo) | ~$1.42/mo |
| 30 replies/day (900/mo) | ~$7.11/mo |

### Server

| Provider | Cost |
|---|---|
| Your existing VPS (bublikstudios.net) | **$0** (already running) |
| MySQL (Docker, already running) | **$0** |
| Nginx (Docker, already running) | **$0** |

### 📊 Total Monthly Cost Estimate

| Usage Level | OpenAI | Twilio | Server | **Total** |
|---|---|---|---|---|
| Light (10 msgs/day) | $1.80 | $2.57 | $0 | **~$4.37/mo** |
| Medium (30 msgs/day) | $5.40 | $8.53 | $0 | **~$13.93/mo** |
| Heavy (100 msgs/day) | $18.00 | $15.37 | $0 | **~$33.37/mo** |
| Light + gpt-4o-mini | $0.12 | $2.57 | $0 | **~$2.69/mo** |

---

## 🔧 Tech Stack

| Component | Technology |
|---|---|
| Language | Python 3.12 |
| Web Framework | Flask |
| WSGI Server | Gunicorn |
| AI Model | OpenAI GPT-4o |
| SMS/Voice | Twilio |
| Database | MySQL 8 (Docker) |
| Scheduler | APScheduler |
| Reverse Proxy | Nginx (Docker) |
| Process Manager | systemd |
| SSL/HTTPS | CDN (Cloudflare or similar) |
| Hosting | VPS at bublikstudios.net |

---

## 🔒 Security

- API keys stored in `.env` file (not in git)
- `.gitignore` excludes `.env`, `__pycache__/`, `.idea/`
- Phone number whitelist (optional) — restrict who can use the bot
- Twilio webhook validation available (can be enabled)
- SELinux set to permissive on AlmaLinux

---

## 🚀 Future Ideas

- [ ] WhatsApp integration (Twilio supports it)
- [ ] Weekly progress reports (summary of check-ins)
- [ ] Streak tracking ("🔥 7 days in a row!")
- [ ] Multiple users with individual schedules
- [ ] Web dashboard to view check-in history
- [ ] Custom pillar goals per user
- [ ] Voice journaling (call the bot, talk, it logs your thoughts)

