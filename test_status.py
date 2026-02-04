"""Тест отображения статуса Telegram каналов"""
import asyncio
import logging
from db.database import NewsDatabase
from sources.source_collector import SourceCollector

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def test_status_display():
    """Тестирование отображения статуса"""
    # Создаем БД и коллектор
    db = NewsDatabase()
    collector = SourceCollector(db=db)
    
    # Собираем новости (чтобы заполнить last_collected_counts)
    logger.info("Собираем новости...")
    await collector.collect_all()
    
    # Симулируем отображение статуса (как в bot.py)
    try:
        from config.railway_config import SOURCES_CONFIG as ACTIVE_SOURCES_CONFIG
    except (ImportError, ValueError):
        from config.config import SOURCES_CONFIG as ACTIVE_SOURCES_CONFIG
    
    last_collected = getattr(collector, "last_collected_counts", {})
    
    # Telegram channels
    telegram_sources = ACTIVE_SOURCES_CONFIG.get('telegram', {}).get('sources', [])
    channel_keys = []
    for src in telegram_sources:
        channel = src.replace('https://t.me/', '').replace('http://t.me/', '').replace('@', '').strip('/')
        if channel:
            channel_keys.append(channel)
    
    logger.info("\n📡 Каналы Telegram:")
    for key in channel_keys:
        collected_count = last_collected.get(key, 0)
        icon = "🟢" if collected_count > 0 else "🔴"
        logger.info(f"  {icon} {key}: {collected_count}")
    
    logger.info(f"\nВсего источников в last_collected: {len(last_collected)}")
    logger.info(f"Telegram каналов с данными: {sum(1 for k in channel_keys if last_collected.get(k, 0) > 0)}")

if __name__ == '__main__':
    asyncio.run(test_status_display())
