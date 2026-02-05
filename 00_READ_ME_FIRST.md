# 🎯 START HERE - TopNews Bot Production/Sandbox Setup

Welcome! This is your entry point to the complete TopNews bot deployment documentation.

## ⚡ 60-Second Summary

TopNews bot now supports **production and sandbox environments running simultaneously** with:
- ✅ Complete data isolation (separate databases)
- ✅ Token validation (prevents mistakes)
- ✅ 5 deployment methods (local, Docker, systemd, Railway, etc.)
- ✅ Comprehensive documentation
- ✅ 100% backward compatible (if you only need one instance, it works exactly as before)

---

## 🚀 Quick Start (Choose One)

### I want to run it locally for testing (5 minutes)
```bash
cp .env.sandbox.example .env
nano .env  # Add your tokens
python main.py
```
**→ Go to**: [QUICKSTART.md - Scenario 1](QUICKSTART.md#scenario-1-local-development-sandbox-only)

### I want to test prod + sandbox on my computer (10 minutes)
```bash
# Terminal 1
cp .env.prod.example .env.prod && nano .env.prod
export APP_ENV=prod && python main.py --env .env.prod

# Terminal 2
cp .env.sandbox.example .env.sandbox && nano .env.sandbox
export APP_ENV=sandbox && python main.py --env .env.sandbox
```
**→ Go to**: [QUICKSTART.md - Scenario 2](QUICKSTART.md#scenario-2-local--production-parallel-testing)

### I want to use Docker (10 minutes)
```bash
docker-compose up -d
docker-compose logs -f
```
**→ Go to**: [QUICKSTART.md - Scenario 3](QUICKSTART.md#scenario-3-docker-compose-testingstaging)

### I have a Linux server (20 minutes)
```bash
# Copy files, install, create .env files, then:
sudo systemctl start bot-prod bot-sandbox
```
**→ Go to**: [QUICKSTART.md - Scenario 4](QUICKSTART.md#scenario-4-linux-vps-systemd-services)

### I'm deploying to Railway (5 minutes)
Create project → Set environment variables → Deploy
**→ Go to**: [QUICKSTART.md - Scenario 5](QUICKSTART.md#scenario-5-railway-cloud-deployment)

---

## 📚 Choose Your Path

### 👤 I'm a **First-Time User**
1. Read: [QUICKSTART.md](QUICKSTART.md) (5 min)
2. Pick a scenario and follow the commands
3. Send `/start` to your bot in Telegram
4. Done!

### 👨‍💻 I'm a **Developer**
1. Read: [SANDBOX_ARCHITECTURE.md](SANDBOX_ARCHITECTURE.md) (15 min)
2. Try Scenario 2 (local prod+sandbox)
3. Explore the code changes in `config/config.py` and `bot.py`
4. Customize as needed

### 🔧 I'm a **DevOps/Operations Engineer**
1. Read: [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) (20 min)
2. Choose your deployment method
3. Follow the detailed instructions
4. Run: [VERIFICATION_CHECKLIST.md](VERIFICATION_CHECKLIST.md)
5. Monitor and maintain

### 📋 I'm a **Project Manager**
1. Read: [STATUS_REPORT.md](STATUS_REPORT.md) (5 min)
2. Review: [IMPLEMENTATION_SUMMARY.md](IMPLEMENTATION_SUMMARY.md)
3. Share QUICKSTART.md with your team
4. Monitor via: [VERIFICATION_CHECKLIST.md](VERIFICATION_CHECKLIST.md)

---

## 🎯 What This Enables

### Before
- Single bot instance only
- No way to test safely
- Risk of breaking production

### After (You Get)
✅ Production AND sandbox running simultaneously  
✅ Safe testing environment  
✅ Complete data separation  
✅ Token validation prevents mistakes  
✅ Visual markers (🧪 in sandbox)  
✅ 5 deployment methods  

---

## 📖 Full Documentation Map

```
QUICKSTART.md                      ← For everyone (START HERE)
├── Scenario 1: Local Sandbox
├── Scenario 2: Local Prod+Sandbox  
├── Scenario 3: Docker Compose
├── Scenario 4: Linux VPS
└── Scenario 5: Railway

DEPLOYMENT_GUIDE.md                ← For detailed steps
├── Token Setup
├── Database Isolation
├── Docker Compose
├── systemd Services
├── Railway Setup
└── Troubleshooting

SANDBOX_ARCHITECTURE.md            ← For technical understanding
├── Architecture Overview
├── Configuration System
├── Data Isolation
└── How It Works

STATUS_REPORT.md                   ← For project status
├── Implementation Summary
├── Features Matrix
└── Quality Metrics

VERIFICATION_CHECKLIST.md          ← For testing
├── Pre-Deployment
├── Post-Deployment
└── Troubleshooting

DOCUMENTATION_INDEX.md             ← For navigation
└── Complete file reference
```

---

## ✅ Key Information

### What You Need
- Python 3.8+ (for local) OR Docker (for containers)
- Telegram bot tokens (get from @BotFather)
- A Telegram channel (where bot publishes)

### What You Get
- Production bot (publishes to main channel)
- Sandbox bot (publishes to test channel)
- Both running simultaneously with no interference
- Complete documentation and verification procedures

### Time Required
- Local setup: 5 minutes
- Docker setup: 10 minutes
- Linux server setup: 20-30 minutes
- Railway setup: 10-15 minutes

---

## 🎮 Test Your Bot

Once running, send these commands:

| Command | What happens |
|---------|---|
| `/start` | Bot greets you (🧪 SANDBOX marker in sandbox) |
| `/status` | Shows if bot is running |
| `/sync` | Collects news from all sources |
| `/pause` | Stops auto-collection |
| `/resume` | Resumes auto-collection |
| `/help` | Shows all commands |

---

## 🔐 Important Notes

### Token Validation
- Both `BOT_TOKEN_PROD` and `BOT_TOKEN_SANDBOX` must be set
- Bot validates token matches environment on startup
- Wrong token = bot won't start (prevents mistakes!)

### Data Isolation
- Production news goes to `db/news.db`
- Sandbox news goes to `db/news_sandbox.db`
- They never mix (fully isolated)

### Backward Compatible
- Existing single-instance setups still work
- No breaking changes
- Can migrate to dual-instance anytime

---

## 🚨 Troubleshooting

### Bot won't start
```
→ Check: Does your token match APP_ENV?
→ Run: python main.py with correct .env file
→ See: DEPLOYMENT_GUIDE.md troubleshooting
```

### No response from bot
```
→ Check: Did you add bot to the channel?
→ Check: Is TELEGRAM_CHANNEL_ID correct?
→ Try: Send /sync to force collection
```

### Wrong environment running
```
→ Check: grep APP_ENV .env
→ Check: grep BOT_TOKEN .env
→ See: VERIFICATION_CHECKLIST.md
```

---

## 📱 Quick Reference

### Environment Variables (Minimum)
```env
APP_ENV=prod                          # or sandbox
BOT_TOKEN_PROD=123456789:ABC...       # Your prod token
BOT_TOKEN_SANDBOX=987654321:XYZ...    # Your sandbox token
TELEGRAM_CHANNEL_ID=-1001234567890    # Your channel
```

### Modes
```
TG_MODE=polling    # Default (simple, local-friendly)
TG_MODE=webhook    # Efficient (requires public URL)
```

### Databases
```
Production: db/news.db
Sandbox:    db/news_sandbox.db
```

---

## 🎯 Next Step

**Choose your deployment scenario and follow the steps:**

→ [QUICKSTART.md](QUICKSTART.md)

Or jump directly to detailed instructions:

→ [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md)

---

## 📞 Documentation Hub

- **Quick Start**: [QUICKSTART.md](QUICKSTART.md)
- **Detailed Guide**: [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md)
- **How It Works**: [SANDBOX_ARCHITECTURE.md](SANDBOX_ARCHITECTURE.md)
- **Testing**: [VERIFICATION_CHECKLIST.md](VERIFICATION_CHECKLIST.md)
- **Status**: [STATUS_REPORT.md](STATUS_REPORT.md)
- **Navigation**: [DOCUMENTATION_INDEX.md](DOCUMENTATION_INDEX.md)
- **Full Docs**: [README.md](README.md)

---

## ✨ What's New

✅ Production/Sandbox architecture  
✅ Token validation system  
✅ Database isolation  
✅ 5 deployment methods  
✅ Comprehensive documentation  
✅ Verification procedures  
✅ Webhook support  

---

## 🚀 Status

**✅ READY FOR DEPLOYMENT**

Everything is implemented, documented, and tested.
Pick your scenario and deploy today!

---

**Questions?** See [DOCUMENTATION_INDEX.md](DOCUMENTATION_INDEX.md) for full navigation.

**Ready?** Go to [QUICKSTART.md](QUICKSTART.md)

---

**Last Updated**: February 5, 2025  
**Status**: ✅ Complete  
**Ready**: Yes!
