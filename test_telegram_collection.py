"""Тест сбора новостей из Telegram каналов"""
import asyncio
import logging
from db.database import NewsDatabase
from sources.source_collector import SourceCollector

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def test_telegram_collection():
    """Тестирование сбора из Telegram каналов"""
    logger.info("Начало теста сбора новостей из Telegram каналов")
    
    # Создаем БД и коллектор
    db = NewsDatabase()
    collector = SourceCollector(db=db)
    
    # Показываем сконфигурированные источники
    logger.info(f"Всего источников: {len(collector._configured_sources)}")
    telegram_sources = [s for s in collector._configured_sources if any(x in s[0] for x in ['telegram', 't.me'])]
    logger.info(f"Telegram источников: {len(telegram_sources)}")
    for fetch_url, source_name, category, src_type in telegram_sources:
        logger.info(f"  - {source_name}: {fetch_url} (тип: {src_type})")
    
    # Собираем новости
    logger.info("Начинаем сбор новостей...")
    news_items = await collector.collect_all()
    
    logger.info(f"\nВсего собрано новостей: {len(news_items)}")
    logger.info(f"\nСтатистика по источникам:")
    for source_name, count in collector.last_collected_counts.items():
        status = "✅" if collector.source_health.get(source_name) else "❌"
        logger.info(f"  {status} {source_name}: {count} новостей")
    
    # Показываем новости из Telegram
    telegram_news = [n for n in news_items if n.get('source') in ['mash', 'bazabazon', 'shot_shot']]
    logger.info(f"\nНовостей из Telegram каналов: {len(telegram_news)}")
    for news in telegram_news[:5]:  # Показываем первые 5
        logger.info(f"  - [{news.get('source')}] {news.get('title')[:60]}...")

if __name__ == '__main__':
    asyncio.run(test_telegram_collection())
