# Новые источники - Документация

## 📝 Обзор

Добавлено 10 новых источников новостей с расширенной конфигурацией включая фильтрацию, приоритизацию и категоризацию на основе контента.

## 🌍 Глобальные источники (World Premium)

### Источники
- **Reuters** - https://www.reuters.com/rssFeed/worldNews
- **Associated Press** - https://apnews.com/rss
- **Financial Times** - https://www.ft.com/rss/world
- **Politico Europe** - https://www.politico.eu/rss-feed/

### Конфигурация
```python
'world_premium': {
    'category': 'world',
    'max_items_per_fetch': 15,
    'timeout': 8,          # 8 секунд таймаут
    'retry': 2,            # 2 попытки повторного запроса
}
```

### Особенности
- Официальные RSS фиды
- Увеличенный таймаут для медленных источников
- Автоматический retry при ошибках

## 💻 Технологии / AI / Криптовалюты

### Источники
- **TechCrunch** - https://techcrunch.com/feed/
- **The Verge** - https://www.theverge.com/rss/index.xml
- **CoinDesk** - https://www.coindesk.com/arc/outboundfeeds/rss/
- **Wired** - https://www.wired.com/feed/rss

### Конфигурация
```python
'tech_ai_crypto': {
    'category': 'tech',
    'max_items_per_fetch': 10,
    'timeout': 8,
    'retry': 2,
    'ai_hashtags_level': 2,                    # Уровень AI для хэштегов
    'enable_entity_extraction': True,           # Извлечение сущностей
    'priority_keywords': [                      # Приоритетные ключевые слова
        'OpenAI', 'Ethereum', 'Tesla', 
        'Bitcoin', 'AI', 'ChatGPT', 'cryptocurrency'
    ],
}
```

### Особенности
- **AI Hashtags Level 2**: Улучшенная категоризация хэштегов
- **Entity Extraction**: Автоматическое извлечение сущностей (компании, технологии)
- **Priority Keywords**: Новости с ключевыми словами получают приоритет
- Автоматическое выделение статей об OpenAI, Ethereum, Tesla и др.

## 📊 Финансы и рынки

### Источники
- **Trading Economics** - https://tradingeconomics.com/rss/news.aspx
- **Bloomberg** - https://www.bloomberg.com/feed/podcast/markets-daily.xml

### Конфигурация
```python
'finance_markets': {
    'category': 'finance',
    'max_items_per_fetch': 8,
    'timeout': 8,
    'retry': 2,
    'ai_summary_min_chars': 600,   # AI summary только для длинных статей
    'summary_only': True,           # Только краткие сводки + цифры
}
```

### Особенности
- **Summary Only**: НЕ пересказывать длинные аналитические статьи
- **AI Summary Min Chars**: AI включается только для статей > 600 символов
- Фокус на цифрах и ключевых данных

## 🇷🇺 Российские источники (обновлено)

### Добавлен источник
- **Meduza** - https://meduza.io/rss/all

### Конфигурация Strong Markers
```python
'russia': {
    'category': 'russia',
    'strong_markers': [
        'Москва', 'Кремль', 'ЦБ РФ', 'Госдума', 
        'Президент России', 'Правительство РФ', 
        'Минфин', 'МИД России'
    ],
}
```

### Логика категоризации
1. **Strong Markers найдены** → Категория: G1 (Россия)
2. **Strong Markers НЕ найдены** → AI geo-detection
3. Автоматическое переопределение категории при обнаружении маркеров

## 🐦 Twitter через RSSHub

### Аккаунты
- **Elon Musk** - /twitter/user/elonmusk
- **Pavel Durov** - /twitter/user/durov
- **Donald Trump** - /twitter/user/realDonaldTrump

### Конфигурация
```python
'twitter_rsshub': {
    'category': 'world',
    'src_type': 'rsshub',
    'min_likes': 300,        # Минимум 300 лайков
    'min_retweets': 100,     # ИЛИ 100 репостов
    'ignore_replies': True,  # Игнорировать ответы
}
```

### Фильтрация
- **Требования**: >= 300 лайков **ИЛИ** >= 100 репостов
- **Игнорируются**: Ответы на твиты (replies)
- **Глобальный рубильник**: `get_global_stop()` отключает весь сбор

## 🔧 Технические детали

### Обработка в source_collector.py

```python
# Twitter фильтрация
if min_likes or min_retweets or ignore_replies:
    likes = item.get('likes', 0)
    retweets = item.get('retweets', 0)
    is_reply = item.get('is_reply', False)
    
    if ignore_replies and is_reply:
        continue
    if min_likes and likes < min_likes:
        if not (min_retweets and retweets >= min_retweets):
            continue

# Strong markers для России
if strong_markers and (title or text):
    content = f"{title} {text}".lower()
    has_marker = any(marker.lower() in content for marker in strong_markers)
    if has_marker:
        category = 'russia'

# Priority keywords для tech
if priority_keywords and (title or text):
    content = f"{title} {text}".lower()
    priority_boost = any(keyword.lower() in content for keyword in priority_keywords)
    if priority_boost:
        item['priority_boost'] = True
```

### Новые параметры source_config

```python
entry = {
    "timeout": timeout,                        # Таймаут запроса
    "retry": retry,                            # Количество повторов
    "ai_hashtags_level": ai_hashtags_level,   # Уровень AI для хэштегов
    "enable_entity_extraction": enable_entity_extraction,
    "priority_keywords": priority_keywords,    # Ключевые слова приоритета
    "ai_summary_min_chars": ai_summary_min_chars,
    "summary_only": summary_only,              # Только краткие сводки
    "strong_markers": strong_markers,          # Маркеры для категории
    "min_likes": min_likes,                    # Twitter: мин лайки
    "min_retweets": min_retweets,             # Twitter: мин репосты
    "ignore_replies": ignore_replies,          # Twitter: игнорировать ответы
}
```

## 📈 Статистика

### Итого источников
- **Глобальные**: 4 новых (Reuters, AP, FT, Politico)
- **Технологии**: 4 новых (TechCrunch, The Verge, CoinDesk, Wired)
- **Финансы**: 2 новых (Trading Economics, Bloomberg)
- **Россия**: +1 (Meduza)
- **Twitter**: 3 аккаунта через RSSHub
- **Всего**: +14 источников

### Новые категории хэштегов
- #Технологии (tech)
- #Криптовалюты (crypto)
- #Финансы (finance)

## 🚀 Использование

### Запуск сбора
```python
from sources.source_collector import SourceCollector

collector = SourceCollector(
    db=db,
    rss_parser=rss_parser,
    html_parser=html_parser
)

# Собирает из всех источников включая новые
news = await collector.collect_all()
```

### Тестирование конфигурации
```bash
python test_new_sources.py
```

### Проверка источника
```python
# Проверка одного источника
items = await collector._collect_from_rss(
    'https://techcrunch.com/feed/',
    'techcrunch.com',
    'tech',
    10,
    source_config={'ai_hashtags_level': 2, 'priority_keywords': ['OpenAI']}
)
```

## ⚠️ Важные замечания

1. **Reuters, AP, FT, Politico**: Могут требовать специального user-agent для избежания 403
2. **Bloomberg RSS**: Ограниченный контент, в основном подкасты
3. **Twitter RSSHub**: Требует работающий RSSHub instance
4. **Meduza**: Может блокироваться в России, использовать VPN
5. **Financial Times**: Некоторые статьи за paywall

## 🔒 Защита от 403/429

### User-Agent ротация
Система автоматически использует случайный user-agent из пула для избежания блокировок.

### Retry логика
- Первая попытка: стандартный таймаут (8с)
- Вторая попытка: увеличенный таймаут
- После 2 ошибок: cooldown

### Cooldown периоды
- 403 Forbidden: 600 секунд (10 минут)
- 429 Too Many Requests: 300 секунд (5 минут)
- 503 Service Unavailable: 600 секунд (10 минут)

## 📝 TODO

- [ ] Добавить прямой парсинг Financial Times (если RSS недостаточен)
- [ ] Реализовать proxy rotation для заблокированных источников
- [ ] Добавить больше tech-аккаунтов в Twitter
- [ ] Мониторинг качества новых источников
- [ ] A/B тестирование priority_keywords

---

**Дата обновления**: 15 февраля 2026  
**Версия**: 1.0.0
