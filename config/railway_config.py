"""
Конфигурация для Railway deployment
Автоматически загружает переменные окружения из Railway
"""
import os
from dotenv import load_dotenv

# Загружаем .env только локально (не нужно на Railway)
if os.path.exists('.env'):
    load_dotenv()

# Telegram Bot API
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN', '')
if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_TOKEN not set. Please set it in Railway environment variables")

TELEGRAM_CHANNEL_ID = int(os.getenv('TELEGRAM_CHANNEL_ID', '0'))
if not TELEGRAM_CHANNEL_ID:
    raise ValueError("TELEGRAM_CHANNEL_ID not set. Please set it in Railway environment variables")

# Интервалы
CHECK_INTERVAL_SECONDS = int(os.getenv('CHECK_INTERVAL_SECONDS', '120'))  # 2 минуты по умолчанию
TIMEOUT_SECONDS = int(os.getenv('TIMEOUT_SECONDS', '30'))

# Прокси (если нужен)
USE_PROXY = os.getenv('USE_PROXY', 'False') == 'True'
PROXY_URL = os.getenv('PROXY_URL', '')

# Учетные данные для закрытых источников
CLOSED_SOURCE_LOGIN = os.getenv('CLOSED_SOURCE_LOGIN', '')
CLOSED_SOURCE_PASSWORD = os.getenv('CLOSED_SOURCE_PASSWORD', '')

# Database - используем переменную окружения для пути на Railway
DATABASE_PATH = os.getenv('DATABASE_PATH', 'db/news.db')

# Логирование
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
LOG_FILE = os.getenv('LOG_FILE', 'logs/bot.log')

# Категории
CATEGORIES = {
    'world': '#Мир',
    'russia': '#Россия',
    'moscow': '#Москва',
    'moscow_region': '#Подмосковье',
}

# Источники по категориям
SOURCES_CONFIG = {
    'russia': {
        'category': 'russia',
        'sources': [
            'https://dzen.ru/news/rubric/chronologic',
            'https://ria.ru/',
            'https://lenta.ru/',
            'https://www.gazeta.ru/',
            'https://tass.ru/',
            'https://rg.ru/',
            'https://ren.tv/news',
            'https://iz.ru/',
            'https://russian.rt.com/',
            'https://www.rbc.ru/',
            'https://www.kommersant.ru/',
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
            'https://riamo.ru/',
            'https://mosregtoday.ru/',
            'https://www.interfax-russia.ru/center/novosti-podmoskovya',
            'https://regions.ru/news',
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
