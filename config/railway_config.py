"""
Конфигурация для Railway deployment
Автоматически загружает переменные окружения из Railway
"""
import os
from dotenv import load_dotenv

# Загружаем .env только локально (не нужно на Railway)
if os.path.exists('.env'):
    load_dotenv()


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "y", "on")


def env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    try:
        return int(value)
    except ValueError:
        return default


def env_str(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return value

# App environment
APP_ENV = env_str('APP_ENV', 'prod')
if APP_ENV not in {'prod', 'sandbox'}:
    raise ValueError(f"APP_ENV must be 'prod' or 'sandbox', got: {APP_ENV}")

# Telegram Bot API
BOT_TOKEN_PROD = env_str('BOT_TOKEN_PROD', None)
BOT_TOKEN_SANDBOX = env_str('BOT_TOKEN_SANDBOX', None)
BOT_TOKEN = env_str('BOT_TOKEN', None) or env_str('TELEGRAM_TOKEN', None)

# Prefer env-specific tokens to avoid accidental wrong token values
if APP_ENV == 'sandbox' and BOT_TOKEN_SANDBOX:
    BOT_TOKEN = BOT_TOKEN_SANDBOX
elif APP_ENV == 'prod' and BOT_TOKEN_PROD:
    BOT_TOKEN = BOT_TOKEN_PROD

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN/TELEGRAM_TOKEN not set. Please set it in Railway environment variables")

TELEGRAM_TOKEN = BOT_TOKEN

# Bot usernames for invite links
BOT_PROD_USERNAME = env_str('BOT_PROD_USERNAME', 'Tops_News_bot')
BOT_SANDBOX_USERNAME = env_str('BOT_SANDBOX_USERNAME', 'topnews_sandbox_bot')

TELEGRAM_CHANNEL_ID = env_int('TELEGRAM_CHANNEL_ID', 0)
if not TELEGRAM_CHANNEL_ID:
    raise ValueError("TELEGRAM_CHANNEL_ID not set. Please set it in Railway environment variables")

# Admin Users IDs for sandbox management (comma-separated from env)
ADMIN_USER_IDS = env_str('ADMIN_USER_IDS', '')
if ADMIN_USER_IDS:
    try:
        ADMIN_USER_IDS = [int(uid.strip()) for uid in ADMIN_USER_IDS.split(',') if uid.strip()]
    except ValueError:
        ADMIN_USER_IDS = []
else:
    ADMIN_USER_IDS = []  # No default for Railway

# Access Control DB (shared for prod/sandbox access control)
ACCESS_DB_PATH = env_str('ACCESS_DB_PATH', 'db/access.db')

# Signed invite secret (must be same in prod and sandbox)
INVITE_SECRET = env_str('INVITE_SECRET', None)

# Интервалы
CHECK_INTERVAL_SECONDS = env_int('CHECK_INTERVAL_SECONDS', 300)  # 5 минут для оптимизации Railway
TIMEOUT_SECONDS = env_int('TIMEOUT_SECONDS', 30)
SOURCE_COLLECT_TIMEOUT_SECONDS = env_int('SOURCE_COLLECT_TIMEOUT_SECONDS', 60)
SOURCE_ERROR_STREAK_LIMIT = env_int('SOURCE_ERROR_STREAK_LIMIT', 3)
SOURCE_ERROR_STREAK_WINDOW_SECONDS = env_int('SOURCE_ERROR_STREAK_WINDOW_SECONDS', 600)
SOURCE_ERROR_COOLDOWN_SECONDS = env_int('SOURCE_ERROR_COOLDOWN_SECONDS', 900)

# Прокси (если нужен)
USE_PROXY = env_bool('USE_PROXY', False)
PROXY_URL = env_str('PROXY_URL', '')

# Учетные данные для закрытых источников
CLOSED_SOURCE_LOGIN = env_str('CLOSED_SOURCE_LOGIN', '')
CLOSED_SOURCE_PASSWORD = env_str('CLOSED_SOURCE_PASSWORD', '')

# Database - используем переменную окружения для пути на Railway
DATABASE_PATH = env_str('DATABASE_PATH', None)
if not DATABASE_PATH:
    DATABASE_PATH = 'db/news.db' if APP_ENV == 'prod' else 'db/news_sandbox.db'

# Cache / media / Redis (environment-aware)
CACHE_PREFIX = env_str('CACHE_PREFIX', None)
REDIS_URL = env_str('REDIS_URL', None)
REDIS_KEY_PREFIX = env_str('REDIS_KEY_PREFIX', None)
MEDIA_CACHE_DIR = env_str('MEDIA_CACHE_DIR', None)

if CACHE_PREFIX is None:
    CACHE_PREFIX = f"{APP_ENV}:"
if REDIS_KEY_PREFIX is None:
    REDIS_KEY_PREFIX = f"{APP_ENV}:"
if MEDIA_CACHE_DIR is None:
    MEDIA_CACHE_DIR = os.path.join("content", "cache", APP_ENV)

# Telegram mode
TG_MODE = env_str('TG_MODE', 'polling')
WEBHOOK_BASE_URL = env_str('WEBHOOK_BASE_URL', None)
WEBHOOK_PATH = env_str('WEBHOOK_PATH', '/tg/webhook')
WEBHOOK_SECRET = env_str('WEBHOOK_SECRET', None)
PORT = env_int('PORT', 8080)

# Management API (optional, sandbox-only)
MGMT_BIND = env_str('MGMT_BIND', '0.0.0.0')
MGMT_PORT = env_int('MGMT_PORT', 8081)

# Side effects guard (sandbox default: True)
DISABLE_PROD_SIDE_EFFECTS = env_bool(
    'DISABLE_PROD_SIDE_EFFECTS',
    True if APP_ENV == 'sandbox' else False,
)

# AI Category Verification
AI_CATEGORY_VERIFICATION_ENABLED = env_bool('AI_CATEGORY_VERIFICATION_ENABLED', True)

# AI Module Levels (0-5, where 0=disabled, 3=default balanced, 5=best quality)
AI_HASHTAGS_LEVEL_DEFAULT = env_int('AI_HASHTAGS_LEVEL_DEFAULT', 3)
AI_CLEANUP_LEVEL_DEFAULT = env_int('AI_CLEANUP_LEVEL_DEFAULT', 3)
AI_SUMMARY_LEVEL_DEFAULT = env_int('AI_SUMMARY_LEVEL_DEFAULT', 3)

# AI budget + limits
AI_DAILY_BUDGET_USD = float(env_str('AI_DAILY_BUDGET_USD', '4.0'))
AI_DAILY_MIN_RESERVE_USD = float(env_str('AI_DAILY_MIN_RESERVE_USD', '0.25'))
AI_DAILY_BUDGET_TOKENS = env_int('AI_DAILY_BUDGET_TOKENS', 0)
AI_CALLS_PER_TICK = env_int('AI_CALLS_PER_TICK', 6)
AI_CALLS_PER_TICK_MAX = env_int('AI_CALLS_PER_TICK_MAX', 30)  # Allow ~15 auto (actual) + 15 user-requested
AI_MAX_INPUT_CHARS = env_int('AI_MAX_INPUT_CHARS', 3200)
AI_MAX_INPUT_CHARS_HASHTAGS = env_int('AI_MAX_INPUT_CHARS_HASHTAGS', 1800)
SUMMARY_MIN_CHARS = env_int('SUMMARY_MIN_CHARS', 200)
AI_SUMMARY_MIN_CHARS = env_int('AI_SUMMARY_MIN_CHARS', SUMMARY_MIN_CHARS)
AI_SUMMARY_LONG_SOURCES = env_str('AI_SUMMARY_LONG_SOURCES', '') or ''

# Логирование
LOG_LEVEL = env_str('LOG_LEVEL', 'INFO')
LOG_FILE = env_str('LOG_FILE', f"logs/bot_{APP_ENV}.log")

# RSSHub (for Telegram channel RSS)
RSSHUB_BASE_URL = env_str('RSSHUB_BASE_URL', 'https://rsshub-production-a367.up.railway.app')
_RSSHUB_MIRROR_RAW = env_str('RSSHUB_MIRROR_URLS', 'https://rsshub.railway.internal')
RSSHUB_MIRROR_URLS = [url.strip() for url in (_RSSHUB_MIRROR_RAW or '').split(',') if url.strip()]

# Категории
CATEGORIES = {
    'world': '#Мир',
    'russia': '#Россия',
    'moscow': '#Москва',
    'moscow_region': '#Подмосковье',
}

# Источники по категориям
SOURCES_CONFIG = {
    'world': {
        'category': 'world',
        'sources': [
            'https://ria.ru/world/',
            'https://lenta.ru/tags/geo/',
            'https://tass.ru/rss/index.xml',
            'https://www.gazeta.ru/news/',
            'https://rg.ru/world/',
            'https://www.rbc.ru/v10/static/rss/rbc_news.rss',
            'https://russian.rt.com/rss/',
            'https://www.interfax.ru/world/',
            'https://iz.ru/xml/rss/all.xml',
            'https://ren.tv/news',
        ]
    },
    'yahoo_world_extended': {
        'category': 'world',
        'sources': [
            'https://news.yahoo.com/rss/world',
            'https://news.yahoo.com/rss/world/europe',
            'https://news.yahoo.com/rss/world/asia',
            'https://news.yahoo.com/rss/world/middle-east',
            'https://news.yahoo.com/rss/us',
            'https://news.yahoo.com/rss/us/politics',
            'https://news.yahoo.com/rss/us/elections',
            'https://news.yahoo.com/rss/politics',
            'https://news.yahoo.com/rss/politics/congress',
            'https://news.yahoo.com/rss/politics/white-house',
            'https://news.yahoo.com/rss/business',
            'https://news.yahoo.com/rss/finance',
            'https://news.yahoo.com/rss/markets',
            'https://news.yahoo.com/rss/crypto',
            'https://news.yahoo.com/rss/tech',
            'https://news.yahoo.com/rss/science',
            'https://news.yahoo.com/rss/climate',
            'https://news.yahoo.com/rss/health',
        ]
    },
    'russia': {
        'category': 'russia',
        'sources': [
            'https://ria.ru/',
            'https://lenta.ru/',
            'https://www.gazeta.ru/news/',
            'https://tass.ru/rss/v2.xml',
            'https://rg.ru/',
            'https://ren.tv/news',
            'https://iz.ru/xml/rss/all.xml',
            'https://russian.rt.com/rss/',
            'https://www.rbc.ru/v10/static/rss/rbc_news.rss',
            'https://rss.kommersant.ru/K40/',
            'https://www.interfax.ru/rss',
        ]
    },
    'telegram': {
        'category': 'russia',
        'sources': [
            'https://t.me/mash',
            'https://t.me/bazabazon',
            'https://t.me/shot_shot',
            'https://t.me/mod_russia',
            'https://t.me/moscowach',   # Moscow city news
            'https://t.me/moscow',      # Moscow official
        ]
    },
    'moscow_region': {
        'category': 'moscow_region',
        'sources': [
            'https://ria.ru/location_Moskovskaja_oblast/',
            'https://lenta.ru/tags/geo/moskovskaya-oblast/',
            'https://iz.ru/tag/moskovskaia-oblast',
            'https://tass.ru/moskovskaya-oblast',
            'https://rg.ru/region/cfo/podmoskovie',
            'https://360.ru/rubriki/mosobl/',
            'https://mosreg.ru/sobytiya/novosti',
            'https://riamo.ru/tag/podmoskove/',
            'https://mosregtoday.ru/news/',
            'https://www.interfax-russia.ru/center/novosti-podmoskovya',
            'https://regions.ru/news',
        ]
    },
    'additional': {
        'category': 'world',
        'sources': [
            'https://naked-science.ru/',
            'https://new-science.ru/category/news/',
            'https://forklog.com/news',
            # Telegram channels - Russian news agencies
            'https://t.me/ruptlyalert',
            'https://t.me/tass_agency',  # TASS официальное
            'https://t.me/rian_ru',
            'https://t.me/mod_russia',  # Минобороны России
            'https://t.me/frank_media',  # Frank Media
            # International news sources
            'https://meduza.io/',          # Russian independent news
            'https://www.reuters.com/world/',  # Reuters world news
            'https://apnews.com/',         # Associated Press
            'https://www.ft.com/',         # Financial Times
            # X (Twitter) accounts - ВРЕМЕННО ОТКЛЮЧЕНЫ (RSSHub и Nitter недоступны)
            # 'https://x.com/kadmitriev',  # Дмитриев
            # 'https://x.com/MedvedevRussia',  # Медведев
            # 'https://x.com/realDonaldTrump',  # Трамп
            # 'https://x.com/elonmusk',  # Маск
            # 'https://x.com/durov',  # Дуров
            # 'https://x.com/JDVance',  # Джей ди Венс
        ]
    },
}

# Закрытый источник требует авторизации
CLOSED_SOURCES = {
    'terminal.mosreg.ru': {
        'category': 'moscow_region',
        'requires_auth': True,
        'url': 'https://terminal.mosreg.ru/info-units',
    }
}
