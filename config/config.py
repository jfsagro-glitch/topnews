"""
Конфигурация приложения
"""
import os
from dotenv import load_dotenv

load_dotenv()

# Telegram Bot API
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN', 'YOUR_BOT_TOKEN')
TELEGRAM_CHANNEL_ID = int(os.getenv('TELEGRAM_CHANNEL_ID', '-1001234567890'))

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

# Логирование
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
LOG_FILE = 'logs/bot.log'

# Категории
CATEGORIES = {
    'world': '#Мир',
    'russia': '#Россия',
    'moscow_region': '#Подмосковье',
}

# Источники по категориям
SOURCES_CONFIG = {
    'world': {
        'category': 'world',
        'sources': [
            'https://ria.ru/world/',
            'https://lenta.ru/tags/geo/',
            'https://tass.ru/world',
            'https://www.gazeta.ru/world/',
            'https://rg.ru/world/',
            'https://rbc.ru/rbcfreenews',
            'https://russian.rt.com/world/',
            'https://www.interfax.ru/world/',
            'https://dzen.ru/news/rubric/world',
        ]
    },
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
