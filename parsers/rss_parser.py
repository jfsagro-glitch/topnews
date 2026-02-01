"""
Парсер RSS фидов
"""
import feedparser
import logging
import asyncio
from typing import List, Dict
from datetime import datetime
from net.http_client import get_http_client
from utils.lead_extractor import extract_lead_from_rss, extract_lead_from_html

logger = logging.getLogger(__name__)


class RSSParser:
    """Парсит RSS фиды"""
    
    def __init__(self, timeout: int = 30, db=None):
        self.timeout = timeout
        self.db = db  # Optional database for conditional GET state
    
    async def parse(self, url: str, source_name: str) -> List[Dict]:
        """
        Парсит RSS фид и возвращает новости
        Использует conditional GET (ETag/Last-Modified) если доступно
        """
        news_items = []
        
        try:
            http_client = await get_http_client()
            
            # Get cached ETag and Last-Modified if available
            headers = {}
            if self.db:
                etag, last_modified = self.db.get_rss_state(url)
                if etag:
                    headers['If-None-Match'] = etag
                if last_modified:
                    headers['If-Modified-Since'] = last_modified
            
            response = await http_client.get(url, headers=headers if headers else None, retries=2)
            
            # 304 Not Modified means content hasn't changed
            if response.status_code == 304:
                logger.debug(f"RSS {url} not modified (304), skipping")
                return news_items
            
            # Store new ETag and Last-Modified for next request
            if self.db:
                etag = response.headers.get('ETag')
                last_modified = response.headers.get('Last-Modified')
                if etag or last_modified:
                    self.db.set_rss_state(url, etag, last_modified)
            
            content = response.text

            # Парсим RSS (может быть затратным - выполняем в отдельном потоке)
            feed = await asyncio.to_thread(lambda: feedparser.parse(content))
            
            if not feed.entries:
                logger.warning(f"No entries in RSS feed from {url}")
                return news_items
            
            # Обрабатываем каждую запись
            for entry in feed.entries[:10]:  # Берём до 10 последних
                lead = extract_lead_from_rss(entry, max_len=800)
                news_item = {
                    'title': entry.get('title', 'No title'),
                    'url': entry.get('link', ''),
                    'text': lead,
                    'source': source_name,
                    'published_at': self._parse_date(entry),
                }
                
                if news_item['url']:  # Только если есть ссылка
                    # Если в RSS нет текста или он слишком короткий — пробуем получить абзац со страницы
                    if not news_item.get('text') or len(news_item['text']) < 40:
                        preview = await self._fetch_article_preview(news_item['url'])
                        if preview:
                            news_item['text'] = preview
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

    async def _fetch_article_preview(self, url: str) -> str:
        """Пробует получить первые предложения со страницы статьи"""
        try:
            http_client = await get_http_client()
            response = await http_client.get(url, retries=1)
            lead = extract_lead_from_html(response.text, max_len=800)
            if lead:
                return lead
        except Exception as e:
            logger.debug(f"Failed to fetch article preview from {url}: {e}")
        return ""
