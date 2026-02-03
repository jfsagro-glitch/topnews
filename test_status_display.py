"""
Тест отображения статуса Telegram каналов в боте
"""
try:
    from config.railway_config import SOURCES_CONFIG as ACTIVE_SOURCES_CONFIG
except (ImportError, ValueError):
    from config.config import SOURCES_CONFIG as ACTIVE_SOURCES_CONFIG

from db.database import NewsDatabase

# Симулируем last_collected_counts из collector
last_collected = {
    'mash': 10,
    'bazabazon': 10,
    'shot_shot': 10,
    'ria.ru': 10,
    'lenta.ru': 10,
    'tass.ru': 10,
}

print("=" * 80)
print("ТЕСТ ОТОБРАЖЕНИЯ СТАТУСА TELEGRAM КАНАЛОВ")
print("=" * 80)

# Получаем Telegram sources из конфига
telegram_sources = ACTIVE_SOURCES_CONFIG.get('telegram', {}).get('sources', [])
print(f"\n1. Telegram sources из config: {telegram_sources}")

# Формируем ключи также, как это делает bot.py
channel_keys = []
channel_labels = []
for src in telegram_sources:
    channel = src.replace('https://t.me/', '').replace('http://t.me/', '').replace('@', '').strip('/')
    if channel:
        channel_keys.append(channel)
        channel_labels.append(channel)

print(f"\n2. Сформированные ключи: {channel_keys}")
print(f"   Метки: {channel_labels}")

# Получаем counts из БД
db = NewsDatabase()
channel_counts = db.get_source_counts(channel_keys) if channel_keys else {}

print(f"\n3. Counts из БД (published):")
for key in channel_keys:
    print(f"   {key}: {channel_counts.get(key, 0)}")

print(f"\n4. Counts из last_collected:")
for key in channel_keys:
    print(f"   {key}: {last_collected.get(key, 0)}")

# Имитируем вывод как в bot.py
print(f"\n5. Как будет выглядеть в команде /status:")
print("📡 Каналы Telegram:")
for channel, key in zip(channel_labels, channel_keys):
    published_count = channel_counts.get(key, 0)
    collected_count = last_collected.get(key, 0)
    # Зеленый если собрано > 0, иначе красный
    icon = "🟢" if collected_count > 0 else "🔴"
    print(f"{icon} {channel}: {collected_count}")

print("\n" + "=" * 80)
