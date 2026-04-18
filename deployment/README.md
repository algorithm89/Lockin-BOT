# Deploy LockIn Bot to bublikstudios.net

## 1. Open port 80 (if not already open)
```bash
sudo ufw allow 80/tcp
sudo ufw status
```

## 2. Upload project to server
```bash
scp -r . user@bublikstudios.net:/var/www/lockinbot/
```

## 3. SSH into server and set up
```bash
ssh user@bublikstudios.net
cd /var/www/lockinbot

# Create venv and install deps
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Create .env file
cat > .env << 'EOF'
OPENAI_API_KEY=sk-proj-xxx
TWILIO_ACCOUNT_SID=xxx
TWILIO_AUTH_TOKEN=xxx
TWILIO_PHONE_NUMBER=+14389059600
MY_PHONE_NUMBER=+1YOURNUMBER
MYSQL_HOST=localhost
MYSQL_USER=lockinbot
MYSQL_PASSWORD=xxx
MYSQL_DATABASE=lockinbot
EOF
```

## 4. Set up MySQL database
```bash
sudo mysql -u root -p
```
```sql
CREATE DATABASE lockinbot;
CREATE USER 'lockinbot'@'localhost' IDENTIFIED BY 'yourpassword';
GRANT ALL PRIVILEGES ON lockinbot.* TO 'lockinbot'@'localhost';
FLUSH PRIVILEGES;
EXIT;
```

## 5. Set up systemd service
```bash
sudo cp deployment/lockinbot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable lockinbot
sudo systemctl start lockinbot
sudo systemctl status lockinbot   # check it's running
```

## 6. Add to your existing nginx config
Add these blocks inside your `server` block in your Docker nginx config, **before** the `location /` catch-all:

```nginx
location /sms {
    proxy_pass         http://127.0.0.1:5000/sms;
    proxy_set_header   Host              $host;
    proxy_set_header   X-Real-IP         $remote_addr;
    proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
    proxy_set_header   X-Forwarded-Proto $scheme;
}

location /voice {
    proxy_pass         http://127.0.0.1:5000/voice;
    proxy_set_header   Host              $host;
    proxy_set_header   X-Real-IP         $remote_addr;
    proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
    proxy_set_header   X-Forwarded-Proto $scheme;
}

location /health {
    proxy_pass         http://127.0.0.1:5000/health;
    proxy_set_header   Host              $host;
    proxy_set_header   X-Real-IP         $remote_addr;
}
```

Then restart your nginx container:
```bash
docker restart bublik-nginx
```

## 7. Configure Twilio webhooks
Go to console.twilio.com → Phone Numbers → (438) 905-9600:
- **SMS webhook:** `https://bublikstudios.net/sms` (POST)
- **Voice webhook:** `https://bublikstudios.net/voice` (POST)

## 8. Test
```bash
# Check the bot is running
curl https://bublikstudios.net/health

# Check logs if something is wrong
sudo journalctl -u lockinbot -f
```
Send a text or call (438) 905-9600!



