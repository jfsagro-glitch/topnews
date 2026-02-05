"""
Конфигурация приложения
"""
import os
from dotenv import load_dotenv

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
    BOT_TOKEN = 'YOUR_BOT_TOKEN'

TELEGRAM_TOKEN = BOT_TOKEN
TELEGRAM_CHANNEL_ID = env_int('TELEGRAM_CHANNEL_ID', -1001234567890)

ADMIN_IDS = [464108692, 1592307306, 408817675]

# Интервалы
CHECK_INTERVAL_SECONDS = env_int('CHECK_INTERVAL_SECONDS', 120)  # 2 минуты
TIMEOUT_SECONDS = env_int('TIMEOUT_SECONDS', 30)

# Прокси (если нужен)
USE_PROXY = env_bool('USE_PROXY', False)
PROXY_URL = env_str('PROXY_URL', '')

# Учетные данные для закрытых источников
CLOSED_SOURCE_LOGIN = env_str('CLOSED_SOURCE_LOGIN', '')
CLOSED_SOURCE_PASSWORD = env_str('CLOSED_SOURCE_PASSWORD', '')

# Database
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

# Side effects guard (sandbox default: True)
DISABLE_PROD_SIDE_EFFECTS = env_bool(
    'DISABLE_PROD_SIDE_EFFECTS',
    True if APP_ENV == 'sandbox' else False,
)

# AI Category Verification
AI_CATEGORY_VERIFICATION_ENABLED = env_bool('AI_CATEGORY_VERIFICATION_ENABLED', True)
AI_CATEGORY_VERIFICATION_RATE = float(env_str('AI_CATEGORY_VERIFICATION_RATE', '1.0'))  # 100% verification for maximum hashtag quality

# Логирование
LOG_LEVEL = env_str('LOG_LEVEL', 'INFO')
LOG_FILE = env_str('LOG_FILE', f"logs/bot_{APP_ENV}.log")

# Категории
CATEGORIES = {
    'world': '🌍 #Мир',
    'russia': '🇷🇺 #Россия',
    'moscow': '🏛️ #Москва',
    'moscow_region': '🏘️ #Подмосковье',
}

# RSSHub (for Telegram channel RSS)
RSSHUB_BASE_URL = env_str('RSSHUB_BASE_URL', 'https://rsshub-production-a367.up.railway.app')

# Источники по категориям
SOURCES_CONFIG = {
    'world': {
        'category': 'world',
        'sources': [
            'https://ria.ru/world/',
            'https://lenta.ru/tags/geo/',
            'https://tass.ru/rss/index.xml',
            'https://www.gazeta.ru/export/rss/lenta.xml',
            'https://rg.ru/world/',
            'https://www.rbc.ru/v10/static/rss/rbc_news.rss',
            'https://russian.rt.com/rss/',
            'https://www.interfax.ru/world/',
            'https://dzen.ru/news/rubric/world',
            'https://iz.ru/xml/rss/all.xml',
            'https://ren.tv/export/rss.xml',
        ]
    },
    'russia': {
        'category': 'russia',
        'sources': [
            'https://dzen.ru/news/rubric/chronologic',
            'https://ria.ru/',
            'https://lenta.ru/',
            'https://www.gazeta.ru/export/rss/lenta.xml',
            'https://tass.ru/rss/v2.xml',
            'https://rg.ru/',
            'https://ren.tv/export/rss.xml',
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
            'https://mosreg.ru/sobytiya/novosti/news-submoscow',
            'https://riamo.ru/tag/podmoskove/',
            'https://mosregtoday.ru/',
            'https://www.interfax-russia.ru/center/novosti-podmoskovya',
            'https://regions.ru/rss/all/',
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

# DeepSeek API Configuration
DEEPSEEK_API_KEY = env_str('DEEPSEEK_API_KEY', '')
DEEPSEEK_API_ENDPOINT = 'https://api.deepseek.com/v1/chat/completions'
AI_SUMMARY_TIMEOUT = 10  # seconds
AI_SUMMARY_MAX_REQUESTS_PER_MINUTE = 3  # Per user per minute
CACHE_EXPIRY_HOURS = 1  # Summary cache TTL

# DeepSeek pricing (February 2026)
DEEPSEEK_INPUT_COST_PER_1K_TOKENS_USD = float(os.getenv('DEEPSEEK_INPUT_COST_PER_1K_TOKENS_USD', '0.00014'))  # $0.14 per 1M
DEEPSEEK_OUTPUT_COST_PER_1K_TOKENS_USD = float(os.getenv('DEEPSEEK_OUTPUT_COST_PER_1K_TOKENS_USD', '0.00028'))  # $0.28 per 1M
