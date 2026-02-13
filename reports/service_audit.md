ЖУРБОТ — Отчет об аудите услуг

1. Резюме

Общий статус: Критический
Количество ошибок: 46
Количество предупреждений: 74

2. Статус услуг

| Сервис | Статус | Время ответа | Детали |
|---|---|---|---|
| API backend /health (localhost:8080) | ERROR | 2863ms | 503 http://localhost:8080/health |
| API backend /ready (localhost:8080) | ERROR | 2805ms | 503 http://localhost:8080/ready |
| Mgmt API /mgmt/collection/stop | SKIPPED | - | not applicable in prod |
| Redis | UNKNOWN | - | REDIS_URL not set |
| Database db/news.db | OK | - | - |
| Access DB db/access.db | OK | - | - |

3. Токены

- selected_from: BOT_TOKEN
- effective_present: False
- sources_present: {'BOT_TOKEN': True, 'TELEGRAM_TOKEN': True, 'BOT_TOKEN_PROD': False, 'BOT_TOKEN_SANDBOX': False}

4. Статус бота (Telegram)

| Имя | Telegram OK | Примечания |
|---|---|---|
| effective | UNKNOWN | effective token missing/placeholder |

5. Проверка ИИ

| Поставщик | Статус | Средний ответ | Тайм-аут |
|---|---|---|---|
| DeepSeek | UNKNOWN | 3447ms | 10s |

6. Целостность базы данных

| Проверка | Статус | Примечания |
|---|---|---|
| Required tables | OK | present |
| Indexes | OK | present |
| Orphan records | OK | user_source_settings=0, user_news_selections=0, ai_summaries=0 |

7. Источники

| Source | Kind | Resolved | Status | Code | Error |
|---|---|---|---|---:|---|
| https://ria.ru/world/ | html | https://ria.ru/world/ | OK | 200 |  |
| https://lenta.ru/tags/geo/ | html | https://lenta.ru/tags/geo/ | WARNING | 404 |  |
| https://tass.ru/rss/index.xml | rss | https://tass.ru/rss/index.xml | WARNING | 403 |  |
| https://www.gazeta.ru/news/ | html | https://www.gazeta.ru/news/ | ERROR | None |  |
| https://rg.ru/world/ | html | https://rg.ru/world/ | WARNING | 401 |  |
| https://www.rbc.ru/v10/static/rss/rbc_news.rss | rss | https://www.rbc.ru/v10/static/rss/rbc_news.rss | ERROR | None |  |
| https://russian.rt.com/rss/ | rss | https://russian.rt.com/rss/ | ERROR | None |  |
| https://www.interfax.ru/world/ | html | https://www.interfax.ru/world/ | ERROR | None |  |
| https://iz.ru/xml/rss/all.xml | rss | https://iz.ru/xml/rss/all.xml | ERROR | None |  |
| https://ren.tv/news | html | https://ren.tv/news | ERROR | None |  |
| https://ria.ru/ | html | https://ria.ru/ | ERROR | None |  |
| https://lenta.ru/ | html | https://lenta.ru/ | ERROR | None |  |
| https://www.gazeta.ru/news/ | html | https://www.gazeta.ru/news/ | ERROR | None |  |
| https://tass.ru/rss/v2.xml | rss | https://tass.ru/rss/v2.xml | ERROR | None |  |
| https://rg.ru/ | html | https://rg.ru/ | ERROR | None |  |
| https://ren.tv/news | html | https://ren.tv/news | ERROR | None |  |
| https://iz.ru/xml/rss/all.xml | rss | https://iz.ru/xml/rss/all.xml | ERROR | None |  |
| https://russian.rt.com/rss/ | rss | https://russian.rt.com/rss/ | ERROR | None |  |
| https://www.rbc.ru/v10/static/rss/rbc_news.rss | rss | https://www.rbc.ru/v10/static/rss/rbc_news.rss | ERROR | None |  |
| https://rss.kommersant.ru/K40/ | rss | https://rss.kommersant.ru/K40/ | ERROR | None |  |
| https://www.interfax.ru/rss | rss | https://www.interfax.ru/rss | ERROR | None |  |
| https://t.me/mash | rsshub | https://rsshub-production-a367.up.railway.app/telegram/channel/mash | ERROR | None |  |
| https://t.me/bazabazon | rsshub | https://rsshub-production-a367.up.railway.app/telegram/channel/bazabazon | ERROR | None |  |
| https://t.me/shot_shot | rsshub | https://rsshub-production-a367.up.railway.app/telegram/channel/shot_shot | ERROR | None |  |
| https://t.me/mod_russia | rsshub | https://rsshub-production-a367.up.railway.app/telegram/channel/mod_russia | OK | 200 |  |
| https://ria.ru/location_Moskovskaja_oblast/ | html | https://ria.ru/location_Moskovskaja_oblast/ | ERROR | None |  |
| https://lenta.ru/tags/geo/moskovskaya-oblast/ | html | https://lenta.ru/tags/geo/moskovskaya-oblast/ | ERROR | None |  |
| https://iz.ru/tag/moskovskaia-oblast | html | https://iz.ru/tag/moskovskaia-oblast | ERROR | None |  |
| https://tass.ru/moskovskaya-oblast | html | https://tass.ru/moskovskaya-oblast | ERROR | None |  |
| https://rg.ru/region/cfo/podmoskovie | html | https://rg.ru/region/cfo/podmoskovie | ERROR | None |  |
| https://360.ru/rubriki/mosobl/ | html | https://360.ru/rubriki/mosobl/ | ERROR | None |  |
| https://mosreg.ru/sobytiya/novosti | html | https://mosreg.ru/sobytiya/novosti | ERROR | None |  |
| https://riamo.ru/tag/podmoskove/ | html | https://riamo.ru/tag/podmoskove/ | ERROR | None |  |
| https://mosregtoday.ru/news/ | html | https://mosregtoday.ru/news/ | ERROR | None |  |
| https://www.interfax-russia.ru/center/novosti-podmoskovya | html | https://www.interfax-russia.ru/center/novosti-podmoskovya | ERROR | None |  |
| https://regions.ru/news | html | https://regions.ru/news | ERROR | None |  |
| https://news.yahoo.com/rss/ | rss | https://news.yahoo.com/rss/ | ERROR | None |  |
| https://news.yahoo.com/rss/world | rss | https://news.yahoo.com/rss/world | ERROR | None |  |
| https://naked-science.ru/ | html | https://naked-science.ru/ | ERROR | None |  |
| https://new-science.ru/category/news/ | html | https://new-science.ru/category/news/ | ERROR | None |  |
| https://forklog.com/news | html | https://forklog.com/news | ERROR | None |  |
| https://t.me/ruptlyalert | rsshub | https://rsshub-production-a367.up.railway.app/telegram/channel/ruptlyalert | OK | 200 |  |
| https://t.me/tass_agency | rsshub | https://rsshub-production-a367.up.railway.app/telegram/channel/tass_agency | OK | 200 |  |
| https://t.me/rian_ru | rsshub | https://rsshub-production-a367.up.railway.app/telegram/channel/rian_ru | ERROR | 503 |  |
| https://t.me/mod_russia | rsshub | https://rsshub-production-a367.up.railway.app/telegram/channel/mod_russia | OK | 200 |  |

8. Безопасность

| Проверка | Статус |
|---|---|
| Webhook secret configured | OK |
| Webhook base URL set | OK |
| Admin-only sandbox policy | UNKNOWN |

9. Критические вопросы

- КРИТИЧЕСКИЙ: Effective TELEGRAM/BOT token missing or placeholder

Сформировано: 2026-02-13T12:56:30.534736Z