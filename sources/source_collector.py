"""
Сборщик новостей из множества источников
"""
import logging
import asyncio
import time
from typing import List, Dict, Optional
try:
    from config.railway_config import SOURCES_CONFIG, RSSHUB_BASE_URL
except (ImportError, ValueError):
    from config.config import SOURCES_CONFIG, RSSHUB_BASE_URL
from parsers.rss_parser import RSSParser
from parsers.html_parser import HTMLParser
from urllib.parse import urlparse
from utils.content_classifier import ContentClassifier

logger = logging.getLogger(__name__)


class SourceCollector:
    """Собирает новости из всех источников"""
    
    def __init__(self, db=None, ai_client=None, bot=None):
        self.db = db
        self.rss_parser = RSSParser(db=db)
        self.html_parser = HTMLParser()
        self.classifier = ContentClassifier()
        self.ai_client = ai_client  # Optional DeepSeek client for AI verification
        self.bot = bot  # Reference to NewsBot for accessing ai_verification_enabled

        # Source health status: source_name -> bool (True ok, False error)
        self.source_health = {}
        
        # Семафор для ограничения параллелизма (6 одновременных запросов)
        self._sem = asyncio.Semaphore(6)
        
        # Cooldown для источников, которые возвращают 403/429
        self._cooldown_until = {}  # url -> timestamp
        
        # Known RSS overrides by domain (when config contains site root)
        # Includes fallback URLs for sites that block direct requests
        self.rss_overrides = {
            'ria.ru': 'https://ria.ru/export/rss2/archive/index.xml',
            'lenta.ru': 'https://lenta.ru/rss/',
            'www.gazeta.ru': 'https://www.gazeta.ru/export/rss/lenta.xml',
            'gazeta.ru': 'https://www.gazeta.ru/export/rss/lenta.xml',
            'tass.ru': 'https://tass.ru/rss/v2.xml',
            'rg.ru': 'https://rg.ru/xml/index.xml',
            'iz.ru': 'https://iz.ru/xml/rss/all.xml',  # Will use HTML if blocked
            'russian.rt.com': 'https://russian.rt.com/rss/',
            'www.rbc.ru': 'https://rssexport.rbc.ru/rbcnews/news/30/full.rss',
            'rbc.ru': 'https://rssexport.rbc.ru/rbcnews/news/30/full.rss',
            'www.kommersant.ru': 'https://www.kommersant.ru/RSS/main.xml',
            'kommersant.ru': 'https://www.kommersant.ru/RSS/main.xml',
            'rss.kommersant.ru': 'https://www.kommersant.ru/RSS/main.xml',
            'interfax.ru': 'https://www.interfax.ru/rss',
            'www.interfax.ru': 'https://www.interfax.ru/rss',
            'interfax-russia.ru': 'https://www.interfax.ru/rss',
            'www.interfax-russia.ru': 'https://www.interfax.ru/rss',
            'ren.tv': None,  # Blocks RSS, use HTML
            'dzen.ru': None,  # Dzen не имеет RSS, нужен HTML парсинг
            '360.ru': 'https://360.ru/rss/',
            'regions.ru': None,  # RSS empty, use HTML
            'riamo.ru': 'https://riamo.ru/feed',
            'mosregtoday.ru': None,  # HTML only
            'mosreg.ru': None,  # HTML only, блокирует RSS
        }

        # We'll dynamically build source list from `SOURCES_CONFIG` so all configured
        # sources are actually collected. Each entry will be classified as 'rss' or 'html'.
        self._configured_sources = []  # list of tuples (fetch_url, source_name, category, type)
        for category_key, cfg in SOURCES_CONFIG.items():
            for src in cfg.get('sources', []):
                parsed = urlparse(src)
                domain = parsed.netloc.lower()

                entries_to_add = []

                # Prefer RSS override when we know the host's RSS endpoint
                if domain in self.rss_overrides:
                    fetch_url = self.rss_overrides[domain]
                    if fetch_url is None:
                        # Domain explicitly has no RSS (like dzen.ru), use HTML
                        logger.info(f"Source {domain} configured for HTML parsing (no RSS available)")
                        entries_to_add.append((src, domain, cfg.get('category', 'russia'), 'html'))
                    else:
                        src_type = 'rss'
                        source_name = domain
                        logger.info(f"Source {domain} using RSS override: {fetch_url}")
                        entries_to_add.append((fetch_url, source_name, cfg.get('category', 'russia'), src_type))
                else:
                    # Heuristics: if URL looks like RSS or XML, treat as RSS
                    if 'rss' in src.lower() or src.lower().endswith(('.xml', '.rss')):
                        fetch_url = src
                        src_type = 'rss'
                        source_name = domain
                        logger.info(f"Source {domain} detected as RSS: {fetch_url}")
                        entries_to_add.append((fetch_url, source_name, cfg.get('category', 'russia'), src_type))
                    else:
                        # t.me channels: use RSSHub if configured
                        if domain.endswith('t.me') or 't.me' in domain:
                            channel = src.replace('https://t.me/', '').replace('http://t.me/', '').replace('@', '').strip('/')
                            base = (RSSHUB_BASE_URL or '').strip()
                            if base and not base.startswith('http'):
                                base = f"https://{base}"
                            base = base.rstrip('/') if base else ''

                            source_name = channel  # Use short name like 'mash' instead of 't.me/mash'
                            if base:
                                fetch_url = f"{base}/telegram/channel/{channel}"
                                logger.info(f"Telegram channel {channel} using RSSHub: {fetch_url}")
                                entries_to_add.append((fetch_url, source_name, cfg.get('category', 'russia'), 'rss'))
                            else:
                                logger.warning(f"RSSHub not configured for Telegram channel {channel}")
                        else:
                            fetch_url = src
                            src_type = 'html'
                            source_name = domain
                            logger.info(f"Source {domain} using HTML parsing: {fetch_url}")
                            entries_to_add.append((fetch_url, source_name, cfg.get('category', 'russia'), src_type))

                for entry in entries_to_add:
                    self._configured_sources.append(entry)
                    self.source_health.setdefault(entry[1], False)
    
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
            tasks = []  # list of tuples (source_name, task)
            
            # Используем сконфигурированные источники, автоматически классифицированные
            for fetch_url, source_name, category, src_type in self._configured_sources:
                if src_type == 'rss':
                    tasks.append((source_name, self._collect_from_rss(fetch_url, source_name, category)))
                else:
                    tasks.append((source_name, self._collect_from_html(fetch_url, source_name, category)))
            
            # Запускаем все параллельно
            results = await asyncio.gather(*[t[1] for t in tasks], return_exceptions=True)
            
            # Собираем результаты
            for (source_name, _task), result in zip(tasks, results):
                if isinstance(result, list):
                    count = len(result)
                    all_news.extend(result)
                    self.source_health[source_name] = True
                    if count > 0:
                        logger.info(f"✅ {source_name}: collected {count} items")
                    else:
                        logger.warning(f"⚠️ {source_name}: 0 items (no new content or parsing issue)")
                elif isinstance(result, Exception):
                    logger.error(f"❌ {source_name}: {type(result).__name__}: {result}")
                    self.source_health[source_name] = False
            
            logger.info(f"Collected total {len(all_news)} news items from {len([s for s in self.source_health.values() if s])} sources")

            
        except Exception as e:
            logger.error(f"Error in collect_all: {e}")
        
        return all_news
    
    async def _collect_from_rss(self, url: str, source_name: str, category: str) -> List[Dict]:
        """Собирает из RSS источника"""
        async with self._sem:
            try:
                # Проверяем cooldown
                if self._in_cooldown(url):
                    logger.warning(f"Source {source_name} in cooldown, skipping")
                    return []
                
                news = await self.rss_parser.parse(url, source_name)
                for item in news:
                    title = item.get('title', '')
                    text = item.get('text', '') or item.get('lead_text', '')
                    item_url = item.get('url', '')
                    
                    # AI text cleaning (MANDATORY to remove any navigation/metadata garbage)
                    if self.ai_client and text:
                        clean_text = await self._clean_text_with_ai(title, text, source_type='rss')
                        if clean_text:
                            item['text'] = clean_text
                            text = clean_text
                    
                    # Classify by content
                    detected_category = self.classifier.classify(title, text, item_url)
                    
                    # Optional AI category verification (if client provided)
                    if self.ai_client and detected_category:
                        ai_category = await self._verify_with_ai(title, text, detected_category)
                        if ai_category:
                            detected_category = ai_category
                    
                    item['category'] = detected_category or category
                return news
            except Exception as e:
                # Check if it's an HTTP error worth cooldown
                error_str = str(e)
                if '403' in error_str:
                    self._set_cooldown(url, 1800)
                    logger.warning(f"HTTP 403 from {source_name} ({url}), setting cooldown for 30 minutes")
                elif '404' in error_str:
                    self._set_cooldown(url, 3600)
                    logger.warning(f"HTTP 404 from {source_name} ({url}), setting cooldown for 1 hour")
                elif '429' in error_str:
                    self._set_cooldown(url, 300)
                    logger.warning(f"HTTP 429 from {source_name} ({url}), setting cooldown for 5 minutes")
                logger.error(f"Error collecting from RSS {url}: {type(e).__name__}: {e}")
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
                    title = item.get('title', '')
                    text = item.get('text', '') or item.get('lead_text', '')
                    item_url = item.get('url', '')
                    
                    # AI text cleaning (MANDATORY for HTML sources to remove navigation garbage)
                    if self.ai_client and text:
                        clean_text = await self._clean_text_with_ai(title, text, source_type='html')
                        if clean_text:
                            item['text'] = clean_text
                            text = clean_text
                    
                    # Classify by content
                    detected_category = self.classifier.classify(title, text, item_url)
                    
                    # Optional AI category verification (if client provided)
                    if self.ai_client and detected_category:
                        ai_category = await self._verify_with_ai(title, text, detected_category)
                        if ai_category:
                            detected_category = ai_category
                    
                    item['category'] = detected_category or category
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
    
    async def _verify_with_ai(self, title: str, text: str, current_category: str) -> Optional[str]:
        """
        Verify category using AI (DeepSeek).
        Only calls AI occasionally to save API costs.
        
        Args:
            title: News title
            text: News text
            current_category: Current category from keyword classifier
            
        Returns:
            Verified category or None if verification skipped/failed
        """
        try:
            # Check if AI verification is enabled via bot toggle
            if self.bot and not self.bot.ai_verification_enabled:
                return None
            
            # Fallback to config if bot reference not available
            if not self.bot:
                from config.config import AI_CATEGORY_VERIFICATION_ENABLED
                if not AI_CATEGORY_VERIFICATION_ENABLED:
                    return None
            
            # Probabilistic verification: only verify X% of items to save costs
            from config.config import AI_CATEGORY_VERIFICATION_RATE
            import random
            if random.random() > AI_CATEGORY_VERIFICATION_RATE:
                return None
            
            verified_category, token_usage = await self.ai_client.verify_category(title, text, current_category)
            
            # Log token usage to database
            if token_usage and token_usage.get('total_tokens', 0) > 0:
                input_cost = (token_usage['input_tokens'] / 1_000_000.0) * 0.14
                output_cost = (token_usage['output_tokens'] / 1_000_000.0) * 0.28
                cost_usd = input_cost + output_cost
                if self.bot:
                    self.bot.db.add_ai_usage(token_usage['total_tokens'], cost_usd, 'category')
            
            return verified_category
            
        except Exception as e:
            logger.debug(f"AI category verification error: {e}")
            return None
    
    async def _clean_text_with_ai(self, title: str, text: str, source_type: str = 'rss') -> Optional[str]:
        """
        Clean article text using AI (DeepSeek) to remove navigation/garbage.
        Only calls AI occasionally to save API costs.
        
        Args:
            title: News title
            text: Raw extracted text
            source_type: 'rss' or 'html' - HTML sources get higher cleaning rate
            
        Returns:
            Clean text or None if cleaning skipped/failed
        """
        try:
            # Check if AI verification is enabled via bot toggle
            if self.bot and not self.bot.ai_verification_enabled:
                return None
            
            # Fallback to config if bot reference not available
            if not self.bot:
                from config.config import AI_CATEGORY_VERIFICATION_ENABLED
                if not AI_CATEGORY_VERIFICATION_ENABLED:
                    return None
            
            # AI cleaning is now MANDATORY for both RSS and HTML sources
            # Even RSS feeds can contain navigation/metadata garbage that needs removal
            pass  # Always continue to cleaning
            
            clean_text, token_usage = await self.ai_client.extract_clean_text(title, text)
            
            # Log token usage to database
            if token_usage and token_usage.get('total_tokens', 0) > 0:
                input_cost = (token_usage['input_tokens'] / 1_000_000.0) * 0.14
                output_cost = (token_usage['output_tokens'] / 1_000_000.0) * 0.28
                cost_usd = input_cost + output_cost
                if self.bot:
                    self.bot.db.add_ai_usage(token_usage['total_tokens'], cost_usd, 'text_clean')
            
            return clean_text
            
        except Exception as e:
            logger.debug(f"AI text cleaning error: {e}")
            return None
    
    def _get_category_for_url(self, url: str, default: str = 'russia') -> str:
        """Определяет категорию по URL"""
        url_lower = (url or '').lower()

        # Московская область (Подмосковье)
        moscow_region_markers = (
            'moskovskaya-oblast',
            'moskovskaja-oblast',
            'moskovskaya_oblast',
            'moskovskaja_oblast',
            'podmoskovie',
            'mosobl',
            'mosreg',
            'mosregtoday',
            'riamo',
            'regions.ru',
        )
        if any(marker in url_lower for marker in moscow_region_markers):
            return 'moscow_region'

        # Москва
        moscow_markers = (
            '/moscow',
            '/moskva',
            'moscow',
            'moskva',
            'moskvy',
            'moskve',
        )
        if any(marker in url_lower for marker in moscow_markers):
            return 'moscow'

        return default
