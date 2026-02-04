"""
Скрипт для отладки ключей Telegram каналов
Проверяет, как формируются ключи в collector и bot
"""
try:
    from config.railway_config import SOURCES_CONFIG as ACTIVE_SOURCES_CONFIG
except (ImportError, ValueError):
    from config.config import SOURCES_CONFIG as ACTIVE_SOURCES_CONFIG

print("=" * 60)
print("ПРОВЕРКА КЛЮЧЕЙ TELEGRAM КАНАЛОВ")
print("=" * 60)

# Как формирует ключи SourceCollector
print("\n1. Как SourceCollector формирует source_name:")
telegram_sources = ACTIVE_SOURCES_CONFIG.get('telegram', {}).get('sources', [])
collector_keys = []
for src in telegram_sources:
    channel = src.replace('https://t.me/', '').replace('http://t.me/', '').replace('@', '').strip('/')
    collector_keys.append(channel)
    print(f"   URL: {src}")
    print(f"   -> source_name: {channel}")
    print()

# Как формирует ключи bot.py в cmd_status
print("2. Как bot.py формирует ключи для last_collected:")
bot_keys = []
for src in telegram_sources:
    channel = src.replace('https://t.me/', '').replace('http://t.me/', '').replace('@', '').strip('/')
    if channel:
        bot_keys.append(channel)
        print(f"   URL: {src}")
        print(f"   -> channel_key: {channel}")
        print()

# Сравнение
print("3. СРАВНЕНИЕ:")
print(f"   Collector keys: {collector_keys}")
print(f"   Bot keys: {bot_keys}")
if collector_keys == bot_keys:
    print("   ✅ КЛЮЧИ СОВПАДАЮТ!")
else:
    print("   ❌ КЛЮЧИ НЕ СОВПАДАЮТ!")
    print(f"   Разница: {set(collector_keys) ^ set(bot_keys)}")

print("\n" + "=" * 60)
