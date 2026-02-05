# Deployment Guide - Production vs Sandbox

This document provides a quick reference for deploying the TopNews bot in production and sandbox environments.

## Quick Reference Table

| Component | Production | Sandbox | Notes |
|-----------|-----------|---------|-------|
| **Environment** | `APP_ENV=prod` | `APP_ENV=sandbox` | Controls all segregation |
| **Database** | `db/news.db` | `db/news_sandbox.db` | Auto-created, fully isolated |
| **Bot Token** | `BOT_TOKEN_PROD` | `BOT_TOKEN_SANDBOX` | Both must be set for validation |
| **Cache Directory** | `content/cache/prod/` | `content/cache/sandbox/` | Auto-created |
| **Visual Marker** | None | 🧪 SANDBOX in /start | Easy identification |
| **Mode** | polling or webhook | polling or webhook | Via `TG_MODE` env var |

## 1. Local Development Setup

### Quick Start (Sandbox)
```bash
# Copy sandbox template
cp .env.sandbox.example .env

# Edit .env with your tokens
nano .env

# Install dependencies
pip install -r requirements.txt

# Run
python main.py
```

### Running Both Simultaneously
```bash
# Terminal 1: Production
export APP_ENV=prod
python main.py --env .env.prod

# Terminal 2: Sandbox  
export APP_ENV=sandbox
python main.py --env .env.sandbox
```

## 2. Docker Compose (Recommended for testing)

```bash
# Prepare configs
cp docker-compose.example.yml docker-compose.yml
cp .env.prod.example .env.prod
cp .env.sandbox.example .env.sandbox

# Edit configs
nano .env.prod
nano .env.sandbox

# Start both services
docker-compose up -d

# Check logs
docker-compose logs -f
```

## 3. systemd Services (Linux VPS)

### Installation
```bash
# Copy app
sudo cp -r . /opt/topnews/
cd /opt/topnews

# Setup Python env
python -m venv .venv
.venv/bin/pip install -r requirements.txt

# Copy configs
sudo mkdir -p /etc/topnews
sudo cp .env.prod.example /etc/topnews/.env.prod
sudo cp .env.sandbox.example /etc/topnews/.env.sandbox
sudo chmod 600 /etc/topnews/.env*

# Install systemd units
sudo cp deploy/systemd/bot-prod.service /etc/systemd/system/
sudo cp deploy/systemd/bot-sandbox.service /etc/systemd/system/
sudo systemctl daemon-reload
```

### Running
```bash
# Start
sudo systemctl start bot-prod
sudo systemctl start bot-sandbox

# Enable auto-start
sudo systemctl enable bot-prod
sudo systemctl enable bot-sandbox

# Monitor
sudo journalctl -u bot-prod -f
sudo journalctl -u bot-sandbox -f
```

## 4. Railway Deployment

### Create Production Service
1. New Project → Deploy from GitHub
2. Select TopNews repo
3. Environment Variables:
   ```
   APP_ENV=prod
   BOT_TOKEN_PROD=<your_token>
   BOT_TOKEN_SANDBOX=<sandbox_token>
   TELEGRAM_CHANNEL_ID=-1001234567890
   TG_MODE=webhook  # or polling
   WEBHOOK_BASE_URL=https://your-railway-url.up.railway.app
   ```
4. Start command: `python main.py`

### Create Sandbox Service
1. Repeat above but with:
   ```
   APP_ENV=sandbox
   BOT_TOKEN_SANDBOX=<your_token>
   BOT_TOKEN_PROD=<prod_token>
   TELEGRAM_CHANNEL_ID=-1001234567891  # different channel
   TG_MODE=webhook
   WEBHOOK_BASE_URL=https://your-sandbox-url.up.railway.app
   ```

## 5. Webhook vs Polling

### Polling (Default)
- **Pros**: Simple, no public URL needed
- **Cons**: Higher latency, more API calls
- **Use for**: Local dev, or simple setups
- **Config**: `TG_MODE=polling`

### Webhook
- **Pros**: Real-time, efficient
- **Cons**: Requires public URL, firewall access
- **Use for**: Production, reliable hosting
- **Config**:
  ```env
  TG_MODE=webhook
  WEBHOOK_BASE_URL=https://yourdomain.com
  WEBHOOK_PATH=/webhook
  PORT=8000
  ```

## 6. Environment Variables

### Token Validation
- Both `BOT_TOKEN_PROD` and `BOT_TOKEN_SANDBOX` must be set
- On startup, the bot validates the token matches `APP_ENV`
- Mismatch → RuntimeError (prevents wrong bot from running)

### Database Isolation
- Automatically set based on `APP_ENV`:
  - `prod` → uses `db/news.db`
  - `sandbox` → uses `db/news_sandbox.db`

### Cache Segregation
- Automatically set based on `APP_ENV`:
  - `prod` → uses `content/cache/prod/`
  - `sandbox` → uses `content/cache/sandbox/`
- Prevents cache mixing between environments

### Startup Behavior
- Logs `APP_ENV` and `TG_MODE` at startup
- Shows 🧪 SANDBOX marker in `/start` if `APP_ENV=sandbox`
- Validates webhook URL if `TG_MODE=webhook`

## 7. Monitoring & Logs

### Local
```bash
# Tail logs
tail -f logs/bot.log

# With grep
tail -f logs/bot.log | grep ERROR
```

### Docker
```bash
docker-compose logs -f bot-prod
docker-compose logs -f bot-sandbox
```

### systemd
```bash
sudo journalctl -u bot-prod -f
sudo journalctl -u bot-sandbox -f
```

### Railway
Use Railway dashboard → Logs tab

## 8. Troubleshooting

### Bot won't start
1. Check token: `BOT_TOKEN_PROD` vs `BOT_TOKEN_SANDBOX` match `APP_ENV`
2. Check dependencies: `pip install -r requirements.txt`
3. Check logs for details

### Webhook fails
1. Ensure `WEBHOOK_BASE_URL` is publicly accessible
2. Check firewall/port 8000 is open
3. Verify `WEBHOOK_SECRET` if using custom one

### Database issues
1. Check `db/` directory exists and is writable
2. For sandbox: ensure `db/news_sandbox.db` is created
3. Check logs for database errors

### Wrong env running
1. Verify `APP_ENV` matches intended environment
2. Verify token matches env: `grep BOT_TOKEN .env`
3. Check `/start` response - shows 🧪 SANDBOX if in sandbox

## 9. Key Files Reference

| File | Purpose | Edit? |
|------|---------|-------|
| `.env.prod.example` | Production template | Copy & customize |
| `.env.sandbox.example` | Sandbox template | Copy & customize |
| `config/config.py` | Config logic | No, unless modifying behavior |
| `utils/sandbox.py` | Sandbox protection | No, unless adding guards |
| `docker-compose.example.yml` | Docker setup | Copy & customize |
| `deploy/systemd/bot-*.service` | systemd units | Copy to `/etc/systemd/system/` |
| `main.py` | Entry point | No |
| `bot.py` | Bot logic | For custom features |

## 10. Common Commands

```bash
# Check APP_ENV
echo $APP_ENV

# Validate config
python -c "from config.config import *; print(f'ENV: {APP_ENV}, MODE: {TG_MODE}')"

# Force sync (when running)
# Send /sync to bot via Telegram

# Check bot status
# Send /status to bot via Telegram

# Stop bot gracefully
# Send Ctrl+C or kill signal
```

---

**Last Updated**: 2024
**Status**: Complete sandbox/production split implemented
