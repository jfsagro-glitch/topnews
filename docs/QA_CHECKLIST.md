# Manual QA Checklist: Sandbox Admin UI + Hashtag Hierarchy + RSSHub Optimization

## Part A: Sandbox Admin-Only UI

### A1. Verify No User Buttons in Sandbox

- [ ] Deploy sandbox bot with `APP_ENV=sandbox`
- [ ] Message `/start` to sandbox bot
- [ ] **Expected**: No pause/resume/send/settings top-row buttons appear
- [ ] **Expected**: Only admin inline menu shown (InlineKeyboardMarkup)
- [ ] Old reply keyboard should disappear (ReplyKeyboardRemove sent)

### A2. Admin Menu Navigation

- [ ] Click "🧨 ОСТАНОВИТЬ ВСЮ СИСТЕМУ" button
- [ ] **Expected**: Button text changes to "✅ ВОЗОБНОВИТЬ ВСЮ СИСТЕМУ"
- [ ] **Expected**: Log shows "[ADMIN] SYSTEM FULL STOP by admin_id=..."
- [ ] Click again to resume
- [ ] **Expected**: Button text reverts to "⛔ ОСТАНОВИТЬ ВСЮ СИСТЕМУ"
- [ ] **Expected**: Log shows "[ADMIN] SYSTEM RESUME by admin_id=..."

### A3. Admin Panels Accessible

- [ ] Click "📊 Статус системы" → shows redis/db status
- [ ] Click "🤖 AI управление" → shows AI level controls
- [ ] Click "📰 Источники" → shows source list + RSSHub toggle
- [ ] Click "📈 Статистика" → shows AI usage stats
- [ ] Click "🧰 Диагностика" → shows db/redis/rsshub info
- [ ] All panels have "⬅️ Назад в меню" button
- [ ] **All**: No "Недоступно в админ-режиме" message

### A4. RSSHub Telegram Toggle

- [ ] In "📰 Источники" panel
- [ ] Click "🔕 Telegram: выключить" (if enabled)
- [ ] **Expected**: Alert "⛔ Telegram RSSHub отключен"
- [ ] Panel refreshes showing toggle button state changed
- [ ] Sources re-scan should skip Telegram channels efficiently

### A5. Non-Admin Rejection

- [ ] Send `/help` from non-admin user in sandbox
- [ ] **Expected**: "⛔ Доступ запрещен"
- [ ] No admin menu shown

## Part B: Global Stop Integration (Prod + Sandbox)

### B1. Global Stop Affects Prod Collection

- [ ] Deploy prod bot
- [ ] Verify prod bot collecting news (log lines: "Collected X items...")
- [ ] In sandbox, click "⛔ ОСТАНОВИТЬ ВСЮ СИСТЕМУ"
- [ ] Wait 5 seconds
- [ ] **Expected**: Prod collection stops; no new "Collected X items..." logs
- [ ] Prod user /status shows "🔴 Система временно остановлена" or silent timeout
- [ ] Toggle back to resume
- [ ] **Expected**: Prod collection resumes within 10s; logs show collection restarting

### B2. Collection Loop Respects Global Stop

- [ ] Check prod `run_periodic_collection()` logs
- [ ] When global_stop=1: logs show 5s sleeps, no fetch attempts
- [ ] When global_stop=0: logs show normal collection cycle

## Part C: Hashtag Hierarchy + Correctness

### C1. Run Unit Tests

```bash
pytest tests/test_hashtags_taxonomy.py -v
```

- [ ] `test_hashtags_moscow_kremlin` passes: tags contain #Россия, #ЦФО, #Москва
- [ ] `test_hashtags_world_politics` passes: tags contain #Мир, #Политика; no #Россия
- [ ] `test_hashtags_crypto_world` passes: tags contain #Мир, one of {#Технологии_медиа, #Экономика}; no #Россия

### C2. Verify Output Format (Production Message)

- [ ] Collect a news item about Moscow politics
- [ ] **Expected message** should contain:
  ```
  🇷🇺 #Россия #ЦФО #Москва #Политика
  ```
  (not: 🇷🇺 #Россия then #Политика separately)
- [ ] Collect a world news item (e.g., "White House statement")
- [ ] **Expected message** should contain:
  ```
  🌍 #Мир #Политика
  ```
  (not: 🌍 #Мир then #Политика separately; not #Россия)

### C3. Rubric Tagging Correctness

- [ ] Test news item: tech + Russia markers → #Россия + #Технологии_медиа
- [ ] Test news item: sport news → contains #Спорт (not #Общество default)
- [ ] Test news item: random/unclear → defaults to #Общество (safe fallback)

## Part D: RSSHub / RSS Optimization

### D1. Verify Per-Source Scheduling

- [ ] Check database table `source_fetch_state`
- [ ] Each RSSHub source has `next_fetch_at` in future
- [ ] RSSHub sources have 15min interval (RSSHUB_MIN_INTERVAL_SECONDS=900)
- [ ] Regular RSS sources have 5min interval (RSS_MIN_INTERVAL_SECONDS=300)

### D2. Backoff on Errors

- [ ] Manually set RSS source to return 503 (test fixture)
- [ ] Wait 5min → source should remain in `next_fetch_at > now`
- [ ] Next interval should be 15min, then 1h if error persists
- [ ] Check log: "...will retry in Xs" with correct cooldown value

### D3. Yahoo RSS Limits

- [ ] Check `SOURCES_CONFIG['yahoo_world_extended']['max_items_per_fetch']` = 20
- [ ] Verify collection logs: Yahoo RSS pulls up to 20 items per feed
- [ ] Verify no duplication: cached items not re-published

### D4. RSSHub Concurrency

- [ ] Set `RSSHUB_CONCURRENCY=2` in env
- [ ] Monitor SQL: simultaneous collectors never > 2 for RSSHub sources
- [ ] CPU/memory stable (no spike)

## Part E: Documentation & Env

### E1. Railway Config

- [ ] Env vars set on Railway:
  ```
  RSSHUB_MIN_INTERVAL_SECONDS=900
  RSS_MIN_INTERVAL_SECONDS=300
  RSSHUB_CONCURRENCY=2
  RSSHUB_SOURCE_COOLDOWN_SECONDS=600
  RSSHUB_DISABLED_CHANNELS=rian_ru
  RSSHUB_TELEGRAM_ENABLED=true
  ```

### E2. Documentation Updated

- [ ] [ADMIN_SANDBOX.md](../ADMIN_SANDBOX.md) reflects new menu structure + global stop UX
- [ ] [docs/COST_OPTIMIZATION_RAILWAY.md](../docs/COST_OPTIMIZATION_RAILWAY.md) documents RSSHub scheduling & memory hints

### E3. No Breaking Changes

- [ ] Prod user still receives daily news
- [ ] Prod user can still use /help, personal settings, filters (if not in sandbox)
- [ ] Hashtags appear correctly in all prod messages

## Sign-Off

- [ ] All Part A checks pass (admin UI works)
- [ ] All Part B checks pass (global stop works end-to-end)
- [ ] All Part C checks pass (hashtags hierarchical & correct)
- [ ] All Part D checks pass (RSSHub throttled & backoff works)
- [ ] All Part E checks pass (env & docs)
- [ ] **Ready for prod deploy**
