# API Сбора Новостей - Архитектура

## 🏗️ Общая архитектура

```
┌─────────────────────────────────────────────────────────────┐
│                    Telegram Bot                             │
│  (telegram bot API, команды, кнопки, управление)           │
└──────────────────┬──────────────────────────────────────────┘
                   │
         ┌─────────┴──────────┬──────────────────┐
         │                    │                  │
    ┌────▼────┐        ┌─────▼──────┐    ┌─────▼───────┐
    │ Command │        │  Periodic  │    │  Collector  │
    │ Handler │        │ Task (2m)  │    │   Engine    │
    └────┬────┘        └─────┬──────┘    └─────┬───────┘
         │                   │                  │
         └───────────────────┼──────────────────┘
                             │
                    ┌────────▼────────┐
                    │  Source          │
                    │ Collector        │
                    │ (Async Parallel) │
                    └────────┬────────┘
         ┌──────────┬────────┼────────┬──────────┐
         │          │        │        │          │
    ┌────▼──┐ ┌────▼──┐ ┌───▼────┐ ┌──▼──┐ ┌───▼────┐
    │  RSS  │ │ HTML  │ │Telegram│ │Auth│ │Others │
    │Parser │ │Parser │ │ Source │ │Src │ │        │
    └────┬──┘ └────┬──┘ └───┬────┘ └──┬──┘ └───┬────┘
         │        │        │       │      │
         └────────┼────────┼───────┼──────┘
                  │        │       │
              [HTTP Requests / API Calls]
                  │        │       │
         ┌────────▼────────▼───────▼────────┐
         │   News Sources                    │
         │ (Websites, RSS, Telegram, APIs)  │
         └────────┬────────────────────────┘
                  │
         ┌────────▼──────────┐
         │  Text Processing  │
         │  & Cleaning       │
         │  (Async)          │
         └────────┬──────────┘
                  │
         ┌────────▼──────────┐
         │  Deduplication    │
         │  (Database Check) │
         └────────┬──────────┘
                  │
         ┌────────▼──────────┐
         │  Telegram Channel │
         │  Publisher        │
         └────────┬──────────┘
                  │
         ┌────────▼──────────┐
         │  Database         │
         │  (SQLite)         │
         └───────────────────┘
```

## 🔄 Жизненный цикл новости

```
1. COLLECTION PHASE
   ├─ Запуск периодического сборщика (каждые 2 минуты)
   ├─ Асинхронный запрос ко всем источникам параллельно
   └─ Получение массива новостей

2. AGGREGATION PHASE
   ├─ Объединение результатов из разных источников
   ├─ Удаление дубликатов на уровне результатов
   └─ Сортировка по времени публикации

3. PROCESSING PHASE
   ├─ Очистка HTML и форматирование текста
   ├─ Извлечение первого абзаца
    ├─ Определение категории
    ├─ Парсинг даты публикации (confidence: high/medium/low/none)
    └─ Фильтр актуальности по confidence и URL-датам
   └─ Создание Telegram сообщения

4. DEDUPLICATION PHASE
   ├─ Проверка URL в БД
   ├─ Пропуск если уже публиковалась
   └─ Разрешение повторов для обновлений (новый текст/ссылка)

5. PUBLISHING PHASE
   ├─ Отправка в Telegram канал
    ├─ Добавление inline кнопок (ИИ)
   ├─ Форматирование сообщения
   └─ Логирование ошибок

6. STORAGE PHASE
    ├─ Сохранение в БД (URL, заголовок, источник, даты, confidence)
    ├─ Запись событий источников (success/error/drop_old)
    └─ Обновление статистики
```

## 📊 Поток данных

### RSS Parser
```
RSS URL → feedparser → News Item
         {
             title: str,
             url: str,
             text: str,
             source: str,
             published_at: datetime,
             category: str
         }
```

### HTML Parser
```
HTML URL → BeautifulSoup → News Item
        → Search articles
        → Extract title
        → Extract link
        → Extract text
```

### Text Cleaner
```
Raw HTML/Text → Clean HTML → Extract paragraph → Truncate
     ↓
Format for Telegram:
**Title**

Paragraph text...

Source: Name
URL

#Category
```

## 🗄️ Структура базы данных

```sql
CREATE TABLE published_news (
    id INTEGER PRIMARY KEY,
    url TEXT UNIQUE NOT NULL,  -- Ключ дедупликации
    title TEXT NOT NULL,
    source TEXT NOT NULL,      -- Источник (РИА, Лента и т.д.)
    category TEXT NOT NULL,    -- Мир, Россия, Подмосковье
    published_at TIMESTAMP,    -- Время публикации
    published_date TEXT,
    published_time TEXT,
    published_confidence TEXT,
    published_source TEXT,
    fetched_at TIMESTAMP,
    first_seen_at TIMESTAMP,
    url_hash TEXT,
    guid TEXT
);

CREATE TABLE source_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    event_type TEXT NOT NULL,      -- success | error | drop_old
    error_code TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE source_health (
    source TEXT PRIMARY KEY,
    last_success_at TIMESTAMP,
    last_error_at TIMESTAMP,
    last_error_code TEXT,
    last_error_message TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

Индексы:
- url (UNIQUE) - для быстрой проверки дубликатов
- published_at - для сортировки
- source - для фильтрации по источнику
- url_hash, guid - для дедупликации по ссылке и GUID
```

## 🟢🔴 Статус источников (логика)

Статус рассчитывается по событиям ingestion за последние 24 часа:

- 🟢 если есть валидные новости и error_rate < 0.5
- 🔴 если валидных новостей нет или error_rate >= 0.5
- DROP_OLD_NEWS не считается ошибкой источника

Отображается:
- название источника
- тип (rss | html | api | x/twitter | yahoo)
- статус и причина (например HTTP_403, TIMEOUT, RSS_INVALID)

Метрики:
- success_count_24h
- error_count_24h
- drop_old_count_24h
- last_error_code/last_error_message

## 🔐 Prod vs Sandbox (доступ и scope)

Sandbox (APP_ENV=sandbox) — админ‑бот. Обычные пользователи не обслуживаются.
Prod (APP_ENV=prod) — пользовательский бот.

### Матрица настроек

Глобальные (bot_settings, меняет только админ в sandbox):
- Уровни AI (hashtags/cleanup/summary)
- Глобальный стоп/старт коллектора
- Глобальный category filter (только sandbox)

Локальные пользовательские (user_* таблицы, только prod):
- Перевод (toggle + lang)
- Pause/Resume
- Включение источников для пользователя
- Выбранные новости и экспорт
- Персональный category filter (prod)

## ⚙️ Асинхронная архитектура

```python
# Все сборщики работают параллельно
tasks = [
    collect_from_rss('url1'),
    collect_from_rss('url2'),
    collect_from_html('url3'),
    collect_from_html('url4'),
    collect_from_telegram('channel1'),
    ...
]

results = await asyncio.gather(*tasks, return_exceptions=True)
```

**Преимущества:**
- Скорость: не ждем ответа от каждого источника
- Надежность: ошибка одного источника не блокирует других
- Масштабируемость: легко добавлять новые источники

## 🎯 Категории и маршрутизация

```
URL → Определение категории → Выбор хештега → Публикация

Правила:
├─ Если домен в SOURCES_CONFIG → используем категорию оттуда
├─ Если URL содержит "moscow" → #Подмосковье
└─ По умолчанию → #Россия
```

## 🔐 Обработка ошибок

```python
try:
    # Сбор новостей
    news = await collect()
except asyncio.TimeoutError:
    # Источник слишком долго отвечает
    logger.warning(f"Timeout: {source}")
    continue  # Идем дальше
except Exception as e:
    # Любая другая ошибка
    logger.error(f"Error: {e}")
    return []  # Возвращаем пусто для этого источника

# Бот продолжит работу с другими источниками
```

## 🕒 Фильтр актуальности (freshness)

Правила:
- high: окно 36ч
- medium: окно 48ч
- low: окно 2 дня (по published_date)
- none: допускается по URL-дате или first_seen в пределах 48ч
- для отдельных доменов возможно расширение окна (override)

## 📈 Масштабируемость

### Добавление нового RSS источника
```python
# В config.py
'SOURCES_CONFIG': {
    'russia': {
        'sources': [
            'https://new-source.ru/rss',  # Просто добавляем
        ]
    }
}
# Done! Автоматически подключится
```

### Добавление HTML парсера для сайта
```python
# В sources/source_collector.py
self.html_sources = {
    'https://new-website.ru/news': 'New Source',  # Добавляем
}
# HTML Parser попробует найти новости автоматически
```

### Пользовательский парсер
```python
# 1. Создаем новый модуль в parsers/
# 2. Добавляем в source_collector.py
# 3. Вызываем из collect_all()
```

## 🧪 Тестирование

### Единичный источник
```python
from parsers.rss_parser import RSSParser
parser = RSSParser()
news = await parser.parse('https://ria.ru/rss', 'РИА')
```

### Все источники
```python
from sources.source_collector import SourceCollector
collector = SourceCollector()
all_news = await collector.collect_all()
```

### Публикация
```python
from bot import NewsBot
bot = NewsBot()
await bot.collect_and_publish()
```

## 🎓 Расширение функционала

### 1. Добавить фильтрацию по ключевым словам
```python
def filter_by_keywords(news, keywords):
    return [n for n in news if any(k in n['title'] for k in keywords)]
```

### 2. Добавить машинный перевод
```python
from google.translate import Translator
def translate_news(news, target_language='en'):
    # ...
```

### 3. Добавить AI-переписывание (EDIT кнопка)
```python
from openai import OpenAI
def rewrite_for_radio(text):
    # Переписать в стиль радио-новостей
```

### 4. Добавить веб-панель
```
Flask/FastAPI app:
/api/news - получить новости
/api/sources - управление источниками
/api/status - статус бота
```

## 📋 Чеклист развертывания

- [ ] Установлены все зависимости
- [ ] Получен и настроен TELEGRAM_TOKEN
- [ ] Создан канал и получен CHANNEL_ID
- [ ] Заполнен файл .env
- [ ] Запущен тест `/sync`
- [ ] Проверены логи в logs/bot.log
- [ ] Настроен автоматический запуск (если нужен)
- [ ] Настроены интервалы проверки
- [ ] Добавлены нужные источники новостей
