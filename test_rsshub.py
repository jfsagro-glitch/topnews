"""Тестирование RSSHub для Telegram каналов"""
import asyncio
import logging
from net.http_client import get_http_client

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_rsshub():
    """Тест доступности RSSHub для Telegram каналов"""
    channels = ['mash', 'bazabazon', 'shot_shot']
    base_url = 'https://rsshub-production-a367.up.railway.app'
    
    http_client = await get_http_client()
    
    for channel in channels:
        url = f"{base_url}/telegram/channel/{channel}"
        try:
            logger.info(f"Проверка {channel}: {url}")
            resp = await http_client.get(url, retries=2)
            logger.info(f"  Статус: {resp.status_code}")
            logger.info(f"  Размер ответа: {len(resp.text)} байт")
            
            if resp.status_code == 200:
                # Попробуем распарсить RSS
                import feedparser
                feed = feedparser.parse(resp.text)
                logger.info(f"  RSS записей: {len(feed.entries)}")
                if feed.entries:
                    logger.info(f"  Первая запись: {feed.entries[0].get('title', 'No title')[:100]}")
            else:
                logger.warning(f"  Ошибка: HTTP {resp.status_code}")
                logger.warning(f"  Ответ: {resp.text[:200]}")
        except Exception as e:
            logger.error(f"  Ошибка: {type(e).__name__}: {e}")
        
        print()

if __name__ == '__main__':
    asyncio.run(test_rsshub())
