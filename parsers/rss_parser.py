"""
Парсер RSS фидов
"""
import feedparser
import logging
from typing import List, Dict
from datetime import datetime
import aiohttp
import asyncio

logger = logging.getLogger(__name__)


class RSSParser:
    """Парсит RSS фиды"""
    
    def __init__(self, timeout: int = 30):
        self.timeout = timeout
    
    async def parse(self, url: str, source_name: str) -> List[Dict]:
        """
        Парсит RSS фид и возвращает новости
        """
        news_items = []
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=self.timeout) as response:
                    if response.status != 200:
                        logger.warning(f"Failed to fetch {url}: {response.status}")
                        return news_items
                    
                    content = await response.text()
            
            # Парсим RSS
            feed = feedparser.parse(content)
            
            if not feed.entries:
                logger.warning(f"No entries in RSS feed from {url}")
                return news_items
            
            # Обрабатываем каждую запись
            for entry in feed.entries[:10]:  # Берём до 10 последних
                news_item = {
                    'title': entry.get('title', 'No title'),
                    'url': entry.get('link', ''),
                    'text': entry.get('summary', '') or entry.get('description', ''),
                    'source': source_name,
                    'published_at': self._parse_date(entry),
                }
                
                if news_item['url']:  # Только если есть ссылка
                    news_items.append(news_item)
            
            logger.info(f"Parsed {len(news_items)} items from {source_name} RSS")
            
        except asyncio.TimeoutError:
            logger.error(f"Timeout parsing RSS from {url}")
        except Exception as e:
            logger.error(f"Error parsing RSS from {url}: {e}")
        
        return news_items
    
    def _parse_date(self, entry) -> str:
        """Парсит дату из записи"""
        try:
            if hasattr(entry, 'published_parsed') and entry.published_parsed:
                return datetime(*entry.published_parsed[:6]).isoformat()
            elif hasattr(entry, 'updated_parsed') and entry.updated_parsed:
                return datetime(*entry.updated_parsed[:6]).isoformat()
        except Exception as e:
            logger.debug(f"Error parsing date: {e}")
        
        return datetime.now().isoformat()
