# 🚀 ТЕХ.ПЛАН: Интеграция DeepSeek для AI пересказа

## Фаза 1: Подготовка (ОК ✅)

- ✅ Анализ юридических рисков (легально)
- ✅ Анализ требований к тексту первого абзаца (улучшен фильтр)
- ✅ Выбор API (DeepSeek)
- ✅ Проверка доступности DeepSeek API

---

## Фаза 2: Реализация (СЕЙЧАС)

### Шаг 1: Обновить `config/config.py`

**Добавить параметры:**
```python
# DeepSeek API Configuration
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")  # Get from .env
DEEPSEEK_API_ENDPOINT = "https://api.deepseek.com/v1/chat/completions"
AI_SUMMARY_TIMEOUT = 10  # seconds
AI_SUMMARY_MAX_REQUESTS_PER_MINUTE = 3  # Per user
CACHE_EXPIRY_HOURS = 1  # Summary cache TTL
```

**Требования:**
- Добавить `DEEPSEEK_API_KEY` в `.env`
- Убедиться, что `httpx` уже в `requirements.txt` (уже есть)

---

### Шаг 2: Расширить БД (`db/database.py`)

**Новая таблица `ai_summaries`:**
```sql
CREATE TABLE IF NOT EXISTS ai_summaries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    news_id INTEGER NOT NULL UNIQUE,
    summary_text TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (news_id) REFERENCES published_news(id) ON DELETE CASCADE
)
```

**Новые методы:**
```python
def get_cached_summary(self, news_id: int) -> str | None:
    """Get cached summary if exists and not expired (1 hour)"""
    query = """
    SELECT summary_text FROM ai_summaries 
    WHERE news_id = ? AND datetime(created_at) > datetime('now', '-1 hour')
    """
    result = self.conn.execute(query, (news_id,)).fetchone()
    return result[0] if result else None

def save_summary(self, news_id: int, summary_text: str):
    """Save AI summary to cache"""
    query = """
    INSERT OR REPLACE INTO ai_summaries (news_id, summary_text, created_at)
    VALUES (?, ?, CURRENT_TIMESTAMP)
    """
    self.conn.execute(query, (news_id, summary_text))
    self.conn.commit()
```

---

### Шаг 3: Добавить AI функцию в `bot.py`

**Новая async функция для DeepSeek:**
```python
# Rate limiting dict (per user)
user_ai_requests = {}  # {user_id: [timestamp1, timestamp2, ...]}

async def _summarize_with_deepseek(text: str, title: str) -> str | None:
    """
    Call DeepSeek API to summarize news
    
    Args:
        text: Article text to summarize
        title: Article title
        
    Returns:
        Summary string or None if error
    """
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                config.DEEPSEEK_API_ENDPOINT,
                headers={"Authorization": f"Bearer {config.DEEPSEEK_API_KEY}"},
                json={
                    "model": "deepseek-chat",
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "Ты помощник для сокращения новостных статей. "
                                "Сделай краткий пересказ новости в 1-2 предложениях. "
                                "Без лишних слов, суть новости. Пересказывай своими словами."
                            )
                        },
                        {
                            "role": "user",
                            "content": f"Заголовок: {title}\n\nТекст: {text}"
                        }
                    ],
                    "temperature": 0.7,
                    "max_tokens": 500
                }
            )
            
            if response.status_code == 200:
                data = response.json()
                summary = data["choices"][0]["message"]["content"]
                return text_cleaner.truncate_text(summary, max_length=200)
            else:
                logger.error(f"DeepSeek API error: {response.status_code}")
                return None
                
    except asyncio.TimeoutError:
        logger.error("DeepSeek API timeout")
        return None
    except Exception as e:
        logger.error(f"DeepSeek error: {e}")
        return None
```

**Callback обработчик для кнопки AI:**
```python
async def ai_summary_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle AI summarize button click"""
    query = update.callback_query
    await query.answer(loading_animation="typewriter")  # Show typing...
    
    # Extract news_id from callback_data
    news_id = int(query.data.split("_")[1])
    user_id = query.from_user.id
    
    # Rate limiting: max 3 requests per minute per user
    now = time.time()
    if user_id not in user_ai_requests:
        user_ai_requests[user_id] = []
    
    # Remove old requests (older than 1 minute)
    user_ai_requests[user_id] = [t for t in user_ai_requests[user_id] if now - t < 60]
    
    if len(user_ai_requests[user_id]) >= config.AI_SUMMARY_MAX_REQUESTS_PER_MINUTE:
        await query.edit_message_text(
            "⏳ Слишком много запросов. Подождите минуту и попробуйте снова."
        )
        return
    
    user_ai_requests[user_id].append(now)
    
    # Get news from DB
    news = db.get_news_by_id(news_id)
    if not news:
        await query.edit_message_text("❌ Новость не найдена")
        return
    
    # Check cache first
    cached_summary = db.get_cached_summary(news_id)
    if cached_summary:
        await query.edit_message_text(f"🤖 *Пересказ:*\n\n{cached_summary}")
        return
    
    # Call DeepSeek
    summary = await _summarize_with_deepseek(news["content"], news["title"])
    
    if summary:
        db.save_summary(news_id, summary)
        await query.edit_message_text(f"🤖 *Пересказ:*\n\n{summary}")
    else:
        await query.edit_message_text("❌ Не удалось создать пересказ. Попробуйте позже.")
```

---

### Шаг 4: Обновить клавиатуру в `bot.py`

**Функция `_create_news_keyboard()`:**
```python
def _create_news_keyboard(news_id: int) -> InlineKeyboardMarkup:
    """Create inline keyboard with AI button"""
    keyboard = [
        [
            InlineKeyboardButton("ИИ", callback_data=f"ai_{news_id}")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)
```

---

## Фаза 3: Тестирование

### Unit тесты

**Тест 1: DeepSeek вызов**
```python
async def test_deepseek_api():
    """Test DeepSeek API works"""
    result = await _summarize_with_deepseek(
        "Русская армия продвинулась на 3 км...",
        "Боевые сводки 01.02.2026"
    )
    assert result is not None
    assert len(result) > 10
    assert len(result) <= 200
```

**Тест 2: Rate limiting**
```python
async def test_rate_limiting():
    """Test rate limiting works"""
    user_id = 12345
    user_ai_requests[user_id] = [time.time() for _ in range(3)]
    
    # 4-й запрос должен быть заблокирован
    # (проверяется в callback'e)
```

**Тест 3: Cache**
```python
def test_cache():
    """Test summary caching"""
    db.save_summary(news_id=1, summary_text="Тест")
    cached = db.get_cached_summary(news_id=1)
    assert cached == "Тест"
```

---

## Фаза 4: Deployment

### На Railway

1. **Добавить `DEEPSEEK_API_KEY` в переменные окружения:**
   ```bash
   DEEPSEEK_API_KEY = "sk-xxxxxxxxxxxxxxxxxxxxx"
   ```

2. **Запустить миграцию БД:**
   ```python
   db.conn.execute("""
   CREATE TABLE IF NOT EXISTS ai_summaries (
       id INTEGER PRIMARY KEY AUTOINCREMENT,
       news_id INTEGER NOT NULL UNIQUE,
       summary_text TEXT NOT NULL,
       created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
       FOREIGN KEY (news_id) REFERENCES published_news(id) ON DELETE CASCADE
   )
   """)
   ```

3. **Перезапустить бот:**
   ```bash
   railway up
   ```

---

## ✅ Итоговый чек-лист

- [ ] `DEEPSEEK_API_KEY` добавлен в `.env` и Railway
- [ ] Таблица `ai_summaries` создана в БД
- [ ] Методы `get_cached_summary()` и `save_summary()` реализованы
- [ ] Функция `_summarize_with_deepseek()` добавлена в bot.py
- [ ] Callback `ai_summary_callback()` зарегистрирован
- [ ] Клавиатура обновлена (две кнопки в одном ряду)
- [ ] Rate limiting реализован (3 запроса в минуту)
- [ ] Логирование добавлено для всех вызовов API
- [ ] Unit тесты пройдены
- [ ] Railway развёрнут и работает

---

## 🎯 Успех?

Когда пользователь нажимает 🤖 **Пересказ**:
1. ✅ Проверяется rate limit (макс 3/мин)
2. ✅ Проверяется кэш (1 час TTL)
3. ✅ Вызывается DeepSeek API
4. ✅ Результат кэшируется
5. ✅ Пересказ отправляется в ЛС пользователя
6. ✅ Указан источник исходной новости

**Результат:** новость + 1 абзац + кнопка ИИ ✨

---

## 📊 Ожидаемые затраты

| Операция | Цена (USD) |
|----------|-----------|
| 1 запрос DeepSeek (~500 токенов) | ~$0.0001 |
| 1000 пересказов/день | ~$0.10 |
| 1 месяц (30k пересказов) | ~$3.00 |
| Plus тарифы (если нужен высокий приоритет) | ~$10-20/месяц |

**Итого:** ≈ $13-23/месяц на AI пересказ (при активном использовании)

---

**Готово к реализации! 🚀**
