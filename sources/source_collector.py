"""
Сборщик новостей из множества источников
"""
import logging
import asyncio
import time
from typing import List, Dict
from config.config import SOURCES_CONFIG
from parsers.rss_parser import RSSParser
from parsers.html_parser import HTMLParser
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class SourceCollector:
    """Собирает новости из всех источников"""
    
    def __init__(self, db=None):
        self.db = db
        self.rss_parser = RSSParser(db=db)
        self.html_parser = HTMLParser()
        
        # Семафор для ограничения параллелизма (6 одновременных запросов)
        self._sem = asyncio.Semaphore(6)
        
        # Cooldown для источников, которые возвращают 403/429
        self._cooldown_until = {}  # url -> timestamp
        
        # Known RSS overrides by domain (when config contains site root)
        self.rss_overrides = {
            'ria.ru': 'https://ria.ru/export/rss2/archive/index.xml',
            'lenta.ru': 'https://lenta.ru/rss/',
            'www.gazeta.ru': 'https://www.gazeta.ru/rss/',
            'tass.ru': 'https://tass.ru/rss/index.xml',
            'rg.ru': 'https://rg.ru/xml/',
            'iz.ru': 'https://iz.ru/rss.xml',
            'russian.rt.com': 'https://russian.rt.com/rss/',
            'www.rbc.ru': 'https://www.rbc.ru/v10/static/rss/rbc_news.rss',
            'www.kommersant.ru': 'https://rss.kommersant.ru/K40/',
        }

        # We'll dynamically build source list from `SOURCES_CONFIG` so all configured
        # sources are actually collected. Each entry will be classified as 'rss' or 'html'.
        self._configured_sources = []  # list of tuples (fetch_url, source_name, category, type)
        for category_key, cfg in SOURCES_CONFIG.items():
            for src in cfg.get('sources', []):
                parsed = urlparse(src)
                domain = parsed.netloc.lower()

                # Prefer RSS override when we know the host's RSS endpoint
                if domain in self.rss_overrides:
                    fetch_url = self.rss_overrides[domain]
                    src_type = 'rss'
                    source_name = domain
                else:
                    # Heuristics: if URL looks like RSS or XML, treat as RSS
                    if 'rss' in src.lower() or src.lower().endswith(('.xml', '.rss')):
                        fetch_url = src
                        src_type = 'rss'
                        source_name = domain
                    else:
                        # t.me channels treated as HTML pages
                        if domain.endswith('t.me'):
                            fetch_url = src
                            src_type = 'html'
                            source_name = src.replace('https://', '')
                        else:
                            fetch_url = src
                            src_type = 'html'
                            source_name = domain

                self._configured_sources.append((fetch_url, source_name, cfg.get('category', 'russia'), src_type))
    
    def _in_cooldown(self, url: str) -> bool:
        """Check if URL is in cooldown period"""
        return self._cooldown_until.get(url, 0) > time.time()
    
    def _set_cooldown(self, url: str, seconds: int = 600):
        """Set cooldown for URL (default 10 minutes)"""
        self._cooldown_until[url] = time.time() + seconds
        logger.warning(f"Cooldown set for {url} for {seconds}s")
    
    async def collect_all(self) -> List[Dict]:
        """
        Собирает новости из всех источников асинхронно
        """
        all_news = []
        
        try:
            # Параллельно запускаем сбор из разных типов источников
            tasks = []
            
            # Используем сконфигурированные источники, автоматически классифицированные
            for fetch_url, source_name, category, src_type in self._configured_sources:
                if src_type == 'rss':
                    tasks.append(self._collect_from_rss(fetch_url, source_name, category))
                else:
                    tasks.append(self._collect_from_html(fetch_url, source_name, category))
            
            # Запускаем все параллельно
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Собираем результаты
            for result in results:
                if isinstance(result, list):
                    all_news.extend(result)
                elif isinstance(result, Exception):
                    logger.error(f"Error in collector task: {result}")
            
            logger.info(f"Collected total {len(all_news)} news items")
            
        except Exception as e:
            logger.error(f"Error in collect_all: {e}")
        
        return all_news
    
    async def _collect_from_rss(self, url: str, source_name: str, category: str) -> List[Dict]:
        """Собирает из RSS источника"""
        async with self._sem:
            try:
                news = await self.rss_parser.parse(url, source_name)
                for item in news:
                    item['category'] = category
                return news
            except Exception as e:
                logger.error(f"Error collecting from RSS {url}: {e}")
                return []
    
    async def _collect_from_html(self, url: str, source_name: str, category: str) -> List[Dict]:
        """Собирает из HTML источника"""
        async with self._sem:
            if self._in_cooldown(url):
                logger.debug(f"Skipping {url} (in cooldown)")
                return []
            
            try:
                news = await self.html_parser.parse(url, source_name)
                for item in news:
                    item['category'] = category
                return news
            except Exception as e:
                # Try to extract HTTP status code
                status_code = None
                if hasattr(e, 'response'):
                    status_code = getattr(e.response, "status_code", None)
                
                # Handle 403 Forbidden and 429 Too Many Requests
                if status_code in (403, 429):
                    self._set_cooldown(url, 600)  # 10 minutes cooldown
                    logger.warning(
                        f"HTTP {status_code} from {source_name} ({url}), "
                        f"setting cooldown for 10 minutes. NOT retrying."
                    )
                    return []
                
                logger.error(f"Error collecting from HTML {source_name} ({url}): {e}", exc_info=False)
                return []
    
    def _get_category_for_url(self, url: str) -> str:
        """Определяет категорию по URL"""
        # Проверяем конфиг
        for category_key, config in SOURCES_CONFIG.items():
            if url in config.get('sources', []):
                return config.get('category', 'russia')
        
        # По умолчанию - Россия
        if 'moskovskaya' in url.lower() or 'podmoskovie' in url.lower() or 'mosobl' in url.lower():
            return 'moscow_region'
        
        return 'russia'
