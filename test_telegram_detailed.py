"""
Скрипт для тестирования реального сбора новостей из Telegram каналов
и проверки last_collected_counts
"""
import asyncio
import logging
import sys

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

try:
    from config.railway_config import SOURCES_CONFIG as ACTIVE_SOURCES_CONFIG
except (ImportError, ValueError):
    from config.config import SOURCES_CONFIG as ACTIVE_SOURCES_CONFIG

from db.database import NewsDatabase
from sources.source_collector import SourceCollector

async def test_telegram_collection():
    """Тестирует сбор из Telegram каналов"""
    print("=" * 80)
    print("ТЕСТ СБОРА НОВОСТЕЙ ИЗ TELEGRAM КАНАЛОВ")
    print("=" * 80)
    
    # Инициализация
    db = NewsDatabase()
    collector = SourceCollector(db=db, ai_client=None, bot=None)
    
    print("\n1. Проверка конфигурации Telegram каналов:")
    telegram_sources = ACTIVE_SOURCES_CONFIG.get('telegram', {}).get('sources', [])
    print(f"   Configured sources: {telegram_sources}")
    
    print("\n2. Проверка _configured_sources в SourceCollector:")
    telegram_configs = [s for s in collector._configured_sources if 'telegram' in s[0].lower() or 't.me' in s[0]]
    for fetch_url, source_name, category, src_type in telegram_configs:
        print(f"   - fetch_url: {fetch_url}")
        print(f"     source_name: {source_name}")
        print(f"     category: {category}")
        print(f"     src_type: {src_type}")
        print()
    
    print("\n3. Запуск сбора новостей...")
    news = await collector.collect_all()
    
    print(f"\n4. Результаты сбора:")
    print(f"   Всего собрано новостей: {len(news)}")
    
    print(f"\n5. Состояние last_collected_counts:")
    print(f"   Все ключи: {list(collector.last_collected_counts.keys())}")
    print()
    
    # Проверяем Telegram каналы отдельно
    print("6. Telegram каналы (детально):")
    telegram_keys = ['mash', 'bazabazon', 'shot_shot']
    for key in telegram_keys:
        count = collector.last_collected_counts.get(key, -999)
        health = collector.source_health.get(key, False)
        icon = "🟢" if count > 0 else "🔴"
        print(f"   {icon} {key}:")
        print(f"      - collected_count: {count}")
        print(f"      - health: {health}")
        
        # Проверяем сколько новостей в БД от этого источника
        db_count = db.get_source_counts([key]).get(key, 0)
        print(f"      - db_count: {db_count}")
        print()
    
    print("\n7. Проверка новостей из Telegram в выборке:")
    telegram_news = [n for n in news if n.get('source') in telegram_keys]
    print(f"   Новостей от Telegram каналов в этой выборке: {len(telegram_news)}")
    if telegram_news:
        print(f"   Примеры (первые 3):")
        for n in telegram_news[:3]:
            print(f"   - source: {n.get('source')}, title: {n.get('title', '')[:60]}")
    
    print("\n" + "=" * 80)
    print("ТЕСТ ЗАВЕРШЕН")
    print("=" * 80)

if __name__ == "__main__":
    asyncio.run(test_telegram_collection())
