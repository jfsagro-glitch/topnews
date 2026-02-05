# 📚 Documentation Index - Sandbox Architecture Implementation

Quick navigation to all resources for the production/sandbox bot setup.

## 🎯 Start Here

**For first-time users**: [QUICKSTART.md](QUICKSTART.md)
- 5 deployment scenarios
- Step-by-step instructions
- Copy-paste commands
- Common troubleshooting

**For detailed understanding**: [SANDBOX_ARCHITECTURE.md](SANDBOX_ARCHITECTURE.md)
- Complete architecture overview
- How isolation works
- All components explained
- Migration guide

---

## 📖 Documentation by Purpose

### I want to... Deploy locally
→ [QUICKSTART.md](QUICKSTART.md) - Scenario 1 or 2

### I want to... Deploy with Docker
→ [QUICKSTART.md](QUICKSTART.md) - Scenario 3  
→ [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) - Docker Compose section

### I want to... Deploy on Linux VPS
→ [QUICKSTART.md](QUICKSTART.md) - Scenario 4  
→ [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) - systemd Services section

### I want to... Deploy on Railway (cloud)
→ [QUICKSTART.md](QUICKSTART.md) - Scenario 5  
→ [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) - Railway Deployment section

### I want to... Understand the architecture
→ [SANDBOX_ARCHITECTURE.md](SANDBOX_ARCHITECTURE.md)  
→ [IMPLEMENTATION_SUMMARY.md](IMPLEMENTATION_SUMMARY.md)

### I want to... Verify everything works
→ [VERIFICATION_CHECKLIST.md](VERIFICATION_CHECKLIST.md)  
→ [QUICKSTART.md](QUICKSTART.md) - Quick Verification section

### I want to... Troubleshoot issues
→ [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) - Troubleshooting section  
→ [QUICKSTART.md](QUICKSTART.md) - Troubleshooting Quick Tips

---

## 📁 File Reference

### Configuration Files (Edit before running)
```
.env.prod.example          ← Copy and edit for production
.env.sandbox.example       ← Copy and edit for sandbox
docker-compose.example.yml ← Copy and edit for Docker
```

### Deployment Files (Copy to server/use as-is)
```
deploy/systemd/
├── bot-prod.service       ← Production systemd unit
└── bot-sandbox.service    ← Sandbox systemd unit
Dockerfile                 ← Docker container definition
```

### Core Application Files
```
config/
├── config.py              ← Local config with environment support
└── railway_config.py      ← Railway config with environment support
bot.py                     ← Main bot logic
main.py                    ← Local entry point
main_railway.py            ← Railway entry point
utils/sandbox.py           ← Sandbox protection utilities
```

### Documentation Files
```
README.md                     ← Full feature documentation
QUICKSTART.md                 ← Quick start guide (START HERE)
DEPLOYMENT_GUIDE.md           ← Detailed deployment steps
SANDBOX_ARCHITECTURE.md       ← Architecture overview
IMPLEMENTATION_SUMMARY.md     ← What was implemented
VERIFICATION_CHECKLIST.md     ← Post-deployment verification
DOCUMENTATION_INDEX.md        ← This file
```

---

## 🚀 Quick Command Reference

### Local Development
```bash
# Sandbox only
cp .env.sandbox.example .env
python main.py

# Production + Sandbox parallel
export APP_ENV=prod && python main.py --env .env.prod
export APP_ENV=sandbox && python main.py --env .env.sandbox  # new terminal
```

### Docker Compose
```bash
docker-compose up -d
docker-compose logs -f
docker-compose down
```

### systemd (Linux)
```bash
sudo systemctl start bot-prod bot-sandbox
sudo systemctl status bot-prod bot-sandbox
sudo journalctl -u bot-prod -f
```

### Railway
1. Create project on Railway.app
2. Set environment variables from .env.prod.example
3. Set start command: `python main.py`
4. Deploy

---

## 🔑 Key Concepts

### APP_ENV
- `prod` - Production instance (no marker in /start)
- `sandbox` - Sandbox instance (shows 🧪 SANDBOX marker)

### Database Isolation
- Production: `db/news.db`
- Sandbox: `db/news_sandbox.db`
- Completely separate, no mixing

### Cache Isolation  
- Production: `content/cache/prod/`
- Sandbox: `content/cache/sandbox/`
- No cache key collisions

### Token Validation
- Both `BOT_TOKEN_PROD` and `BOT_TOKEN_SANDBOX` must be set
- Tokens validated against `APP_ENV` on startup
- Mismatch prevents bot from running

### Webhook vs Polling
- `TG_MODE=polling` (default) - Simple, local-friendly
- `TG_MODE=webhook` - Efficient, requires public URL

---

## ✅ Verification Checklist Summary

After deployment, verify:
- [ ] Bot responds to /start
- [ ] Sandbox shows 🧪 marker, production doesn't
- [ ] Separate databases created (db/news.db vs db/news_sandbox.db)
- [ ] Separate caches created (content/cache/prod vs sandbox)
- [ ] Token validation works (wrong token prevents startup)
- [ ] /sync triggers news collection
- [ ] News appears in correct channel only

See [VERIFICATION_CHECKLIST.md](VERIFICATION_CHECKLIST.md) for full checklist.

---

## 🆘 Getting Help

| Problem | Resource |
|---------|----------|
| Where do I start? | [QUICKSTART.md](QUICKSTART.md) |
| How do I deploy? | [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) |
| Why isn't it working? | [VERIFICATION_CHECKLIST.md](VERIFICATION_CHECKLIST.md) |
| What was implemented? | [IMPLEMENTATION_SUMMARY.md](IMPLEMENTATION_SUMMARY.md) |
| How does it work? | [SANDBOX_ARCHITECTURE.md](SANDBOX_ARCHITECTURE.md) |
| All features/commands? | [README.md](README.md) |

---

## 📊 Project Structure

```
TopNews/
├── 📄 QUICKSTART.md                    ← START HERE
├── 📄 DEPLOYMENT_GUIDE.md              ← Detailed steps
├── 📄 SANDBOX_ARCHITECTURE.md          ← Architecture
├── 📄 IMPLEMENTATION_SUMMARY.md        ← What's new
├── 📄 VERIFICATION_CHECKLIST.md        ← Testing
├── 📄 README.md                        ← Full docs
├── 📄 DOCUMENTATION_INDEX.md           ← This file
│
├── ⚙️ Configuration
│   ├── .env.prod.example
│   ├── .env.sandbox.example
│   ├── docker-compose.example.yml
│   └── config/
│       ├── config.py
│       └── railway_config.py
│
├── 🚀 Deployment
│   ├── Dockerfile
│   ├── Procfile
│   └── deploy/systemd/
│       ├── bot-prod.service
│       └── bot-sandbox.service
│
├── 🤖 Application
│   ├── bot.py
│   ├── main.py
│   ├── main_railway.py
│   ├── utils/sandbox.py
│   └── [other source files]
│
└── 📦 Dependencies
    └── requirements.txt
```

---

## 🔗 Related Documents (Pre-Sandbox)

The following documents from earlier work are still relevant:
- [00_START_HERE_RAILWAY.md](00_START_HERE_RAILWAY.md) - Railway-specific setup
- [RAILWAY_QUICKSTART.md](RAILWAY_QUICKSTART.md) - Railway quick reference
- [README.md](README.md) - Full feature documentation

---

## 📝 Implementation Status

✅ **Complete** - All components implemented and documented:
- Configuration layer with APP_ENV support
- Token validation system
- Bot interface updates (sandbox marker)
- Database isolation (separate files)
- Cache isolation (separate directories)
- Sandbox protection utilities
- Docker Compose setup
- systemd services
- Comprehensive documentation

**Ready for**: Local development, Docker testing, VPS deployment, Railway cloud hosting

---

## 🎓 Learning Path

1. **Beginner**: [QUICKSTART.md](QUICKSTART.md) → Pick your scenario → Run it
2. **Intermediate**: [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) → Understand options → Deploy
3. **Advanced**: [SANDBOX_ARCHITECTURE.md](SANDBOX_ARCHITECTURE.md) → Understand internals → Customize

---

## 💡 Pro Tips

### Efficient Development
- Use scenario 2 (local prod + sandbox) for testing
- Use scenario 3 (Docker) before deploying to production
- Use scenario 4 (systemd) for production on your own server

### Safe Deployment
- Always verify with verification checklist before going live
- Test webhook in staging (Docker) before production
- Keep .env files backed up but secure

### Troubleshooting
- Check logs first: `journalctl -u bot-prod -f` or `docker-compose logs -f`
- Verify tokens: `echo $BOT_TOKEN`
- Test communication: Send `/start` to your bot
- Verify isolation: Check database files exist separately

---

## 📞 Support Resources

- **Telegram Bot Documentation**: [@BotFather](https://t.me/BotFather)
- **Python-telegram-bot**: https://python-telegram-bot.readthedocs.io
- **Docker Documentation**: https://docs.docker.com
- **systemd Documentation**: https://systemd.io
- **Railway Platform**: https://railway.app

---

**Last Updated**: February 5, 2025  
**Status**: ✅ Complete and Ready for Deployment  
**Version**: Sandbox Architecture v1.0  

---

## 🎯 Next Steps

1. Read [QUICKSTART.md](QUICKSTART.md) to pick your deployment scenario
2. Follow the steps in that scenario
3. Run the verification checklist from [VERIFICATION_CHECKLIST.md](VERIFICATION_CHECKLIST.md)
4. Deploy to production when ready!

**You're all set! 🚀**
