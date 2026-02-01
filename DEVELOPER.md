# Руководство разработчика TopNews Bot

## 🔧 Структура кода

### Основные модули

#### `config/config.py`
- Центральная конфигурация приложения
- TELEGRAM_TOKEN, TELEGRAM_CHANNEL_ID
- Интервалы и таймауты
- Определение категорий
- Список источников по категориям

#### `db/database.py`
- `NewsDatabase` класс для работы с БД
- Методы: `add_news()`, `is_published()`, `get_recent_news()`, `get_stats()`
- SQLite для хранения опубликованных новостей

#### `parsers/`
- `rss_parser.py` - парсинг RSS фидов через feedparser
- `html_parser.py` - парсинг HTML страниц через BeautifulSoup

#### `sources/`
- `source_collector.py` - главный сборщик, координирует все парсеры
- `telegram_source.py` - сбор из Telegram каналов (заготовка)
- `auth_source.py` - сбор с авторизацией (заготовка)

#### `utils/`
- `logger.py` - настройка логирования
- `text_cleaner.py` - очистка HTML, форматирование текста

#### `bot.py`
- `NewsBot` класс - основной Telegram бот
- Обработка команд (/sync, /status, /pause, /resume)
- Периодический сбор новостей
- Публикация в канал

#### `main.py`
- Точка входа приложения
- Инициализация логирования
- Запуск бота

## 🚀 Добавление нового источника

### Вариант 1: RSS источник (самый простой)

1. Убедитесь, что источник предоставляет RSS:
   ```
   https://example.com/rss
   https://example.com/feed.xml
   ```

2. Добавьте в [config/config.py](config/config.py):
   ```python
   self.rss_sources = {
       'https://example.com/rss': 'Пример.ру',
   }
   ```

3. Если нужна нестандартная категория, добавьте в конфиг:
   ```python
   SOURCES_CONFIG = {
       'special': {
           'category': 'russia',
           'sources': ['https://example.com/rss']
       }
   }
   ```

Готово! RSS парсер автоматически подключится.

### Вариант 2: HTML источник (требуется кастомизация)

1. Добавьте в [sources/source_collector.py](sources/source_collector.py):
   ```python
   self.html_sources = {
       'https://example.com/news': 'Пример.ру',
   }
   ```

2. Базовый HTML парсер попытается найти статьи автоматически. Если не работает, создайте кастомный парсер:

3. В [parsers/html_parser.py](parsers/html_parser.py) добавьте специфичные для сайта селекторы:
   ```python
   def parse_example_site(self, soup):
       # Используя инспектор браузера, найдите CSS селекторы
       articles = soup.find_all('div', class_='article-item')
       for article in articles:
           title = article.find('h2').text
           link = article.find('a')['href']
           text = article.find('p', class_='summary').text
           # ...
   ```

### Вариант 3: Telegram канал (требует API)

1. Установите pyrogram или telethon:
   ```bash
   pip install pyrogram
   # или
   pip install telethon
   ```

2. В [sources/telegram_source.py](sources/telegram_source.py) реализуйте:
   ```python
   async def collect_from_channels(self, channels: List[str]):
       # Используйте pyrogram/telethon API
       # Получите последние посты из каналов
   ```

3. Добавьте в [sources/source_collector.py](sources/source_collector.py):
   ```python
   async def collect_from_telegram(self, channels):
       return await self.telegram_source.collect_from_channels(channels)
   ```

## 📝 Модификация форматирования сообщений

Отредактируйте функцию `format_telegram_message()` в [utils/text_cleaner.py](utils/text_cleaner.py):

```python
def format_telegram_message(title, text, source_name, source_url, category):
    # Текущий формат:
    # *Заголовок*
    # 
    # Абзац текста
    # 
    # Источник: Имя
    # URL
    # 
    # #Категория
    
    # Можно добавить:
    # - Эмодзи
    # - Теги для SEO
    # - Ссылку на оригинал
    # и т.д.
```

## 🔐 Использование переменных окружения

Добавьте новую переменную в `.env`:
```env
MY_CUSTOM_SETTING=value
```

Используйте в коде:
```python
from config.config import MY_CUSTOM_SETTING
# или
import os
value = os.getenv('MY_CUSTOM_SETTING', 'default_value')
```

## 🧪 Отладка

### Включить debug логирование

В [config/config.py](config/config.py):
```python
LOG_LEVEL = 'DEBUG'  # Вместо 'INFO'
```

### Посмотреть последние логи
```bash
tail -f logs/bot.log
```

### Тестировать парсер отдельно
```python
import asyncio
from parsers.rss_parser import RSSParser

async def test():
    parser = RSSParser()
    news = await parser.parse('https://ria.ru/', 'РИА')
    for item in news:
        print(item)

asyncio.run(test())
```

### Тестировать сборщик
```python
import asyncio
from sources.source_collector import SourceCollector

async def test():
    collector = SourceCollector()
    news = await collector.collect_all()
    print(f"Собрано {len(news)} новостей")

asyncio.run(test())
```

## 🔄 CI/CD интеграция

### GitHub Actions пример

Создайте `.github/workflows/test.yml`:
```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - uses: actions/setup-python@v2
        with:
          python-version: 3.9
      - run: pip install -r requirements.txt
      - run: python -m pytest tests/
```

## 📚 API для расширения

### Добавить веб-API

```python
from fastapi import FastAPI

app = FastAPI()

@app.get("/api/status")
async def get_status():
    return {"status": "running", "stats": bot.db.get_stats()}

@app.post("/api/sync")
async def trigger_sync():
    count = await bot.collect_and_publish()
    return {"published": count}
```

### WebSocket для реал-тайм обновлений

```python
from fastapi import WebSocket

@app.websocket("/ws/news")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    while True:
        news = await bot.collect_and_publish()
        await websocket.send_json({"news_count": news})
```

## 🎓 Лучшие практики

### 1. Обработка ошибок
```python
try:
    result = await operation()
except asyncio.TimeoutError:
    logger.error("Timeout")
    return None  # или default value
except Exception as e:
    logger.error(f"Unexpected error: {e}", exc_info=True)
    return None
```

### 2. Логирование
```python
logger.debug("Detailed info for debugging")
logger.info("Important state changes")
logger.warning("Something unexpected but not critical")
logger.error("Error occurred", exc_info=True)
```

### 3. Асинхронный код
```python
# ✅ Правильно: параллельное выполнение
tasks = [fetch(url) for url in urls]
results = await asyncio.gather(*tasks)

# ❌ Неправильно: последовательное выполнение
results = [await fetch(url) for url in urls]
```

### 4. Типизация
```python
from typing import List, Dict, Optional

async def collect_from_source(
    url: str, 
    source_name: str
) -> List[Dict[str, any]]:
    """Собирает новости из источника"""
    # ...
```

## 🔗 Полезные ссылки

- [Telegram Bot API](https://core.telegram.org/bots/api)
- [python-telegram-bot docs](https://python-telegram-bot.readthedocs.io/)
- [asyncio docs](https://docs.python.org/3/library/asyncio.html)
- [BeautifulSoup docs](https://www.crummy.com/software/BeautifulSoup/bs4/doc/)
- [feedparser docs](https://feedparser.readthedocs.io/)

## ❓ FAQ

**Q: Как добавить новый хештег?**
A: В [config/config.py](config/config.py) добавьте в CATEGORIES и SOURCES_CONFIG

**Q: Как изменить интервал проверки?**
A: В [config/config.py](config/config.py) измените CHECK_INTERVAL_SECONDS

**Q: Как добавить фильтрацию по ключевым словам?**
A: В [sources/source_collector.py](sources/source_collector.py) добавьте фильтр после collect_all()

**Q: Как использовать прокси?**
A: Установите USE_PROXY=True в .env и укажите PROXY_URL

**Q: Как работает дедупликация?**
A: Проверка по URL в БД. Если URL уже есть - новость не публикуется
