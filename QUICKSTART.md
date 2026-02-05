# Quick Start Guide - TopNews Bot (Production + Sandbox)

Choose your deployment scenario and follow the steps.

## 🚀 Scenario 1: Local Development (Sandbox Only)

**Perfect for**: First-time setup, local testing

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Create config from template
cp .env.sandbox.example .env

# 3. Edit .env with your tokens
nano .env
# Set: BOT_TOKEN_SANDBOX, BOT_TOKEN_PROD, TELEGRAM_CHANNEL_ID

# 4. Run
python main.py

# 5. Send /start to your bot in Telegram
# You should see: "🧪 SANDBOX" marker
```

**That's it!** Your sandbox bot is running.

---

## 🎯 Scenario 2: Local + Production (Parallel Testing)

**Perfect for**: Testing before production deployment

```bash
# 1. Create both configs
cp .env.prod.example .env.prod
cp .env.sandbox.example .env.sandbox

# 2. Edit both files with correct tokens and channel IDs
nano .env.prod
nano .env.sandbox

# 3. Run production in Terminal 1
export APP_ENV=prod
python main.py --env .env.prod

# 4. Run sandbox in Terminal 2 (new terminal)
export APP_ENV=sandbox
python main.py --env .env.sandbox

# 5. Send /start to both bots
# Production: No marker
# Sandbox: Shows "🧪 SANDBOX"
```

**Both instances running simultaneously** with complete isolation.

---

## 🐳 Scenario 3: Docker Compose (Testing/Staging)

**Perfect for**: Realistic deployment testing before production

```bash
# 1. Prepare configs
cp docker-compose.example.yml docker-compose.yml
cp .env.prod.example .env.prod
cp .env.sandbox.example .env.sandbox

# 2. Edit .env files
nano .env.prod
nano .env.sandbox

# 3. Start both services
docker-compose up -d

# 4. Check status
docker-compose logs -f

# 5. Test both bots in Telegram
# Stop with: docker-compose down
```

---

## 🔧 Scenario 4: Linux VPS (systemd Services)

**Perfect for**: Production deployment on your own server

```bash
# 1. Copy app to server
scp -r . user@server:/opt/topnews

# 2. SSH into server
ssh user@server
cd /opt/topnews

# 3. Setup Python environment
python -m venv .venv
.venv/bin/pip install -r requirements.txt

# 4. Setup configs
sudo mkdir -p /etc/topnews
sudo cp .env.prod.example /etc/topnews/.env.prod
sudo cp .env.sandbox.example /etc/topnews/.env.sandbox
sudo nano /etc/topnews/.env.prod      # Edit
sudo nano /etc/topnews/.env.sandbox   # Edit
sudo chmod 600 /etc/topnews/.env*

# 5. Install systemd services
sudo cp deploy/systemd/bot-prod.service /etc/systemd/system/
sudo cp deploy/systemd/bot-sandbox.service /etc/systemd/system/
sudo systemctl daemon-reload

# 6. Start services
sudo systemctl start bot-prod bot-sandbox
sudo systemctl enable bot-prod bot-sandbox

# 7. Monitor
sudo systemctl status bot-prod
sudo systemctl status bot-sandbox
sudo journalctl -u bot-prod -f
```

---

## ☁️ Scenario 5: Railway (Cloud Deployment)

**Perfect for**: Serverless cloud hosting

### Production Service
1. Create new Railway project
2. Connect GitHub repository
3. Set Environment Variables:
   ```
   APP_ENV=prod
   BOT_TOKEN_PROD=<your_token>
   BOT_TOKEN_SANDBOX=<sandbox_token>
   TELEGRAM_CHANNEL_ID=-1001234567890
   TG_MODE=webhook
   WEBHOOK_BASE_URL=https://your-railway.up.railway.app
   ```
4. Set start command: `python main.py`
5. Deploy

### Sandbox Service
1. Create second Railway project  
2. Same steps as above but:
   ```
   APP_ENV=sandbox
   TELEGRAM_CHANNEL_ID=-1001234567891  # Different channel
   WEBHOOK_BASE_URL=https://your-sandbox-railway.up.railway.app
   ```

---

## 🎮 Common Commands

Once your bot is running, send these in Telegram:

| Command | What it does | Expected Response |
|---------|-------------|-------------------|
| `/start` | Greet the bot | Welcome + 🧪 SANDBOX if in sandbox |
| `/status` | Check bot health | 🟢 Running status |
| `/sync` | Trigger news collection | Bot collects from all sources |
| `/pause` | Stop collecting | Paused state |
| `/resume` | Resume collecting | Collecting again |
| `/help` | List commands | Full command list |

---

## ✅ Quick Verification

After starting your bot:

1. **Is the bot responding?**
   - Send `/start`
   - Should get response

2. **Is it the right environment?**
   - Sandbox: Should see "🧪 SANDBOX" in response
   - Production: No marker

3. **Is it collecting news?**
   - Send `/sync`
   - Check channel for new messages

4. **Check the database**
   - Sandbox: `db/news_sandbox.db` created
   - Production: `db/news.db` created

---

## 🔐 Token Setup Help

If you need to create bot tokens:

1. Open Telegram → Find **@BotFather**
2. Send `/newbot`
3. Follow prompts:
   - Bot name: `YourBotName`
   - Bot username: `your_bot_name_bot`
4. Copy the token provided
5. Paste into `.env` file as `BOT_TOKEN_SANDBOX` (or `BOT_TOKEN_PROD`)
6. Repeat for second token if running dual instances

---

## 📍 Channel ID Setup Help

If you need your channel ID:

1. Add bot to your channel as Administrator
2. Send any message to the channel
3. Run this command:
   ```bash
   curl "https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates" | grep chat_id
   ```
4. Copy the `chat_id` value
5. Paste into `.env` as `TELEGRAM_CHANNEL_ID`

---

## 🆘 Troubleshooting Quick Tips

| Problem | Solution |
|---------|----------|
| **Bot won't start** | Check token in .env matches APP_ENV (prod vs sandbox) |
| **No messages from bot** | Check TELEGRAM_CHANNEL_ID is correct |
| **Database lock error** | Only one instance per environment allowed |
| **Webhook connection fails** | Verify WEBHOOK_BASE_URL is publicly accessible |
| **Seeing wrong environment** | Verify APP_ENV variable is set correctly |

For more help, see:
- `README.md` - Full documentation
- `DEPLOYMENT_GUIDE.md` - Detailed deployment instructions
- `VERIFICATION_CHECKLIST.md` - Testing procedures

---

## 📚 File Reference

| What I want to do | See this file |
|------------------|--------------|
| Deploy locally | This guide (Scenario 1 or 2) |
| Use Docker | This guide (Scenario 3) |
| Use VPS/Linux | This guide (Scenario 4) |
| Use Railway | This guide (Scenario 5) |
| Deep dive on architecture | `SANDBOX_ARCHITECTURE.md` |
| Detailed deployment steps | `DEPLOYMENT_GUIDE.md` |
| Verify everything works | `VERIFICATION_CHECKLIST.md` |
| Understand all config options | `README.md` + `.env.*.example` |

---

## 🎯 Next Steps

1. **Choose your scenario** (1-5 above) based on your needs
2. **Follow the steps** in that scenario
3. **Send /start** to your bot to verify it's working
4. **Set /pause** or `/resume` to control news collection
5. **Check logs** if anything doesn't work

---

**You're ready! 🚀**

Pick your scenario and start in less than 5 minutes.
