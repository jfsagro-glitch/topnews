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
        
        # Настройки парсеров для конкретных источников
        self.rss_sources = {
            'https://ria.ru/export/rss2/archive/index.xml': 'РИА Новости',
            'https://lenta.ru/rss/': 'Лента.ру',
            'https://www.gazeta.ru/rss/': 'Газета.ру',
            'https://tass.ru/rss/index.xml': 'ТАСС',
            'https://rg.ru/xml/': 'Российская газета',
            'https://iz.ru/rss.xml': 'Известия',
            'https://russian.rt.com/rss/': 'RT',
            'https://www.rbc.ru/v10/static/rss/rbc_news.rss': 'РБК',
            'https://rss.kommersant.ru/K40/': 'Коммерсантъ',
        }
        
        self.html_sources = {
            'https://dzen.ru/news/rubric/chronologic': 'Яндекс.Дзен',
            'https://ren.tv/news': 'РЕН ТВ',
            'https://360.ru/rubriki/mosobl/': '360 (Подмосковье)',
            'https://riamo.ru/': 'РИАМО',
            'https://mosregtoday.ru/': 'МосРегион Today',
            'https://www.interfax-russia.ru/center/novosti-podmoskovya': 'Интерфакс',
            'https://regions.ru/news': 'Regions.ru',
        }
    
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
            
            # RSS источники
            for url, source_name in self.rss_sources.items():
                # Получаем категорию из конфига
                category = self._get_category_for_url(url)
                tasks.append(self._collect_from_rss(url, source_name, category))
            
            # HTML источники
            for url, source_name in self.html_sources.items():
                category = self._get_category_for_url(url)
                tasks.append(self._collect_from_html(url, source_name, category))
            
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
                code = getattr(e.response, "status_code", None) if hasattr(e, "response") else None
                if code in (403, 429):
                    self._set_cooldown(url, 600)  # 10 minutes cooldown
                    logger.warning(f"403/429 from {url}, setting cooldown")
                    return []
                logger.error(f"Error collecting from HTML {url}: {e}")
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
