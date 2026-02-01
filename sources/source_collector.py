"""
Сборщик новостей из множества источников
"""
import logging
import asyncio
from typing import List, Dict
from config.config import SOURCES_CONFIG
from parsers.rss_parser import RSSParser
from parsers.html_parser import HTMLParser

logger = logging.getLogger(__name__)


class SourceCollector:
    """Собирает новости из всех источников"""
    
    def __init__(self):
        self.rss_parser = RSSParser()
        self.html_parser = HTMLParser()
        
        # Настройки парсеров для конкретных источников
        self.rss_sources = {
            'https://ria.ru/': 'РИА Новости',
            'https://lenta.ru/': 'Лента.ру',
            'https://www.gazeta.ru/': 'Газета.ру',
            'https://tass.ru/': 'ТАСС',
            'https://rg.ru/': 'Российская газета',
            'https://iz.ru/': 'Известия',
            'https://russian.rt.com/': 'RT',
            'https://www.rbc.ru/': 'РБК',
            'https://www.kommersant.ru/': 'Коммерсантъ',
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
        try:
            news = await self.html_parser.parse(url, source_name)
            for item in news:
                item['category'] = category
            return news
        except Exception as e:
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
