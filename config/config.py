"""
Конфигурация приложения
"""
import os
from dotenv import load_dotenv

load_dotenv()

# Telegram Bot API
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN', 'YOUR_BOT_TOKEN')
TELEGRAM_CHANNEL_ID = int(os.getenv('TELEGRAM_CHANNEL_ID', '-1001234567890'))

ADMIN_IDS = [464108692, 1592307306, 408817675]

# Интервалы
CHECK_INTERVAL_SECONDS = 120  # 2 минуты
TIMEOUT_SECONDS = 30

# Прокси (если нужен)
USE_PROXY = os.getenv('USE_PROXY', 'False') == 'True'
PROXY_URL = os.getenv('PROXY_URL', '')

# Учетные данные для закрытых источников
CLOSED_SOURCE_LOGIN = os.getenv('CLOSED_SOURCE_LOGIN', '')
CLOSED_SOURCE_PASSWORD = os.getenv('CLOSED_SOURCE_PASSWORD', '')

# Database
DATABASE_PATH = 'db/news.db'

# AI Category Verification
AI_CATEGORY_VERIFICATION_ENABLED = os.getenv('AI_CATEGORY_VERIFICATION_ENABLED', 'True') == 'True'
AI_CATEGORY_VERIFICATION_RATE = float(os.getenv('AI_CATEGORY_VERIFICATION_RATE', '0.3'))  # 30% of news

# Логирование
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
LOG_FILE = 'logs/bot.log'

# Категории
CATEGORIES = {
    'world': '🌍 #Мир',
    'russia': '🇷🇺 #Россия',
    'moscow': '🏛️ #Москва',
    'moscow_region': '🏘️ #Подмосковье',
}

# RSSHub (for Telegram channel RSS)
RSSHUB_BASE_URL = os.getenv('RSSHUB_BASE_URL', 'https://rsshub-production-a367.up.railway.app')

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
DEEPSEEK_API_KEY = os.getenv('DEEPSEEK_API_KEY', '')
DEEPSEEK_API_ENDPOINT = 'https://api.deepseek.com/v1/chat/completions'
AI_SUMMARY_TIMEOUT = 10  # seconds
AI_SUMMARY_MAX_REQUESTS_PER_MINUTE = 3  # Per user per minute
CACHE_EXPIRY_HOURS = 1  # Summary cache TTL

# DeepSeek pricing (February 2026)
DEEPSEEK_INPUT_COST_PER_1K_TOKENS_USD = float(os.getenv('DEEPSEEK_INPUT_COST_PER_1K_TOKENS_USD', '0.00014'))  # $0.14 per 1M
DEEPSEEK_OUTPUT_COST_PER_1K_TOKENS_USD = float(os.getenv('DEEPSEEK_OUTPUT_COST_PER_1K_TOKENS_USD', '0.00028'))  # $0.28 per 1M
