# CONFIG

## Environment

- APP_ENV: prod|sandbox (default: prod)
- DATABASE_PATH: SQLite DB path (default: db/news.db or db/news_sandbox.db)
- ACCESS_DB_PATH: shared access DB (default: db/access.db)
- REDIS_URL: Redis connection string (optional)
- REDIS_KEY_PREFIX: Redis key prefix (default: {APP_ENV}:)
- CACHE_PREFIX: cache prefix (default: {APP_ENV}:)

## Telegram

- BOT_TOKEN/BOT_TOKEN_PROD/BOT_TOKEN_SANDBOX
- TELEGRAM_CHANNEL_ID
- TG_MODE: polling|webhook
- WEBHOOK_BASE_URL, WEBHOOK_PATH, WEBHOOK_SECRET
- PORT
- ADMIN_TELEGRAM_IDS or ADMIN_TELEGRAM_ID

## AI

- DEEPSEEK_API_KEY
- DAILY_LLM_BUDGET_USD (default: 1.0)
- AI_HASHTAGS_LEVEL_DEFAULT
- AI_CLEANUP_LEVEL_DEFAULT
- AI_SUMMARY_LEVEL_DEFAULT

## Ingestion

- CHECK_INTERVAL_SECONDS (default: 120)
- RSSHUB_BASE_URL, RSSHUB_MIRROR_URLS
- USE_PROXY, PROXY_URL

## Deduplication

Dedup uses canonical URL (url_normalized), url_hash, checksum, and simhash with a 48h window.
