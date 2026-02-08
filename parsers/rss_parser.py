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
from utils.date_parser import parse_datetime_value, split_date_time

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
            
            # 304 Not Modified means content hasn't changed - use cached data
            if response.status_code == 304:
                logger.debug(f"RSS {url} not modified (304), using cached content")
                if self.db:
                    cached_items = self.db.get_rss_cached_items(url)
                    if cached_items:
                        logger.info(f"Using {len(cached_items)} cached items from {source_name} RSS")
                        return cached_items
                # If no cache available, treat as empty (first request)
                return news_items
            
            # Check for error status codes
            if response.status_code != 200:
                logger.error(f"RSS {url} returned status {response.status_code}")
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
                published_info = self._parse_date_info(entry)
                published_at = published_info.get('published_at')
                pub_date = None
                pub_time = None
                if published_at:
                    pub_date, pub_time = split_date_time(published_at)

                news_item = {
                    'title': entry.get('title', 'No title'),
                    'url': entry.get('link', ''),
                    'text': lead,
                    'source': source_name,
                    'published_at': published_at.isoformat() if published_at else None,
                    'published_date': pub_date,
                    'published_time': pub_time,
                    'published_confidence': published_info.get('published_confidence', 'none'),
                    'published_source': published_info.get('published_source'),
                    'guid': entry.get('id') or entry.get('guid') or entry.get('link', ''),
                }
                
                if news_item['url']:  # Только если есть ссылка
                    # Если в RSS нет текста или он слишком короткий — пробуем получить абзац со страницы
                    # For sources like ria.ru that don't provide text in RSS, always fetch
                    if not news_item.get('text') or len(news_item['text']) < 60:
                        logger.debug(f"Text too short or missing ({len(news_item.get('text', ''))} chars), fetching from page...")
                        preview = await self._fetch_article_preview(news_item['url'])
                        if preview:
                            news_item['text'] = preview
                            logger.debug(f"Successfully fetched text ({len(preview)} chars) for: {news_item['title'][:50]}")
                        else:
                            logger.warning(f"Could not fetch text for: {news_item['title'][:50]}")
                    news_items.append(news_item)

            
            # Cache the items for potential 304 responses
            if self.db and news_items:
                self.db.cache_rss_items(url, news_items)
            
            logger.info(f"Parsed {len(news_items)} items from {source_name} RSS")
            
        except asyncio.TimeoutError:
            logger.error(f"Timeout parsing RSS from {url}")
        except Exception as e:
            logger.error(f"Error parsing RSS from {url}: {e}")
        
        return news_items
    
    def _parse_date_info(self, entry) -> dict:
        """Parse date and return confidence/source metadata."""
        try:
            if hasattr(entry, 'published_parsed') and entry.published_parsed:
                dt = datetime(*entry.published_parsed[:6])
                return {
                    'published_at': parse_datetime_value(dt),
                    'published_confidence': 'high',
                    'published_source': 'rss:published_parsed',
                }
            if hasattr(entry, 'updated_parsed') and entry.updated_parsed:
                dt = datetime(*entry.updated_parsed[:6])
                return {
                    'published_at': parse_datetime_value(dt),
                    'published_confidence': 'medium',
                    'published_source': 'rss:updated_parsed',
                }
        except Exception as e:
            logger.debug(f"Error parsing date: {e}")

        for key, confidence in (('published', 'high'), ('updated', 'medium')):
            raw = entry.get(key) if isinstance(entry, dict) else getattr(entry, key, None)
            if not raw:
                continue
            dt = parse_datetime_value(str(raw))
            if dt:
                return {
                    'published_at': dt,
                    'published_confidence': confidence,
                    'published_source': f"rss:{key}",
                }

        return {
            'published_at': None,
            'published_confidence': 'none',
            'published_source': None,
        }

    async def _fetch_article_preview(self, url: str) -> str:
        """Пробует получить первые предложения со страницы статьи"""
        try:
            http_client = await get_http_client()
            try:
                response = await http_client.get(url, retries=1, timeout=10)
                lead = extract_lead_from_html(response.text, max_len=800)
                if lead:
                    logger.debug(f"Fetched preview from {url}: {len(lead)} chars")
                    return lead
            except asyncio.TimeoutError:
                logger.debug(f"Timeout fetching article preview from {url}, trying again with longer timeout")
                # Retry with longer timeout
                response = await http_client.get(url, retries=0, timeout=20)
                lead = extract_lead_from_html(response.text, max_len=800)
                if lead:
                    logger.debug(f"Fetched preview (retry) from {url}: {len(lead)} chars")
                    return lead
        except Exception as e:
            logger.debug(f"Failed to fetch article preview from {url}: {type(e).__name__}: {str(e)[:80]}")
        return ""
