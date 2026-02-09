"""
Сборщик новостей из множества источников
"""
import logging
import asyncio
import time
import json
import socket
from typing import List, Dict, Optional
from datetime import datetime
try:
    from config.railway_config import SOURCES_CONFIG, RSSHUB_BASE_URL, RSSHUB_MIRROR_URLS
except (ImportError, ValueError):
    from config.config import SOURCES_CONFIG, RSSHUB_BASE_URL, RSSHUB_MIRROR_URLS
from parsers.rss_parser import RSSParser
from parsers.html_parser import HTMLParser
from urllib.parse import urlparse
from utils.content_classifier import ContentClassifier
from utils.content_quality import (
    content_quality_score,
    compute_checksum,
    compute_simhash,
    compute_url_hash,
    detect_language,
    is_low_quality,
    normalize_url,
)
from utils.date_parser import parse_published_info, split_date_time
from utils.article_extractor import extract_article_text
from utils.site_extractors import extract_lenta, extract_ria

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
        # Last collection counts per source (for /status reporting)
        self.last_collected_counts = {}
        self.last_collection_at = None
        
        # Семафор для ограничения параллелизма (6 одновременных запросов)
        self._sem = asyncio.Semaphore(6)
        
        # Cooldown для источников, которые возвращают 403/429
        self._cooldown_until = {}  # url -> timestamp
        self._source_error_streak = {}
        self._source_error_last = {}

        try:
            from config.railway_config import (
                SOURCE_COLLECT_TIMEOUT_SECONDS,
                SOURCE_ERROR_STREAK_LIMIT,
                SOURCE_ERROR_STREAK_WINDOW_SECONDS,
                SOURCE_ERROR_COOLDOWN_SECONDS,
            )
        except (ImportError, ValueError):
            from config.config import (
                SOURCE_COLLECT_TIMEOUT_SECONDS,
                SOURCE_ERROR_STREAK_LIMIT,
                SOURCE_ERROR_STREAK_WINDOW_SECONDS,
                SOURCE_ERROR_COOLDOWN_SECONDS,
            )

        self._source_collect_timeout = SOURCE_COLLECT_TIMEOUT_SECONDS
        self._source_error_streak_limit = SOURCE_ERROR_STREAK_LIMIT
        self._source_error_window = SOURCE_ERROR_STREAK_WINDOW_SECONDS
        self._source_error_cooldown_seconds = SOURCE_ERROR_COOLDOWN_SECONDS
        self._rsshub_bases = self._normalize_rsshub_bases(RSSHUB_BASE_URL, RSSHUB_MIRROR_URLS)
        self._rss_fallback_blocklist = {
            'gazeta.ru',
            'www.gazeta.ru',
            'mosreg.ru',
            'www.mosreg.ru',
        }
        
        # Known RSS overrides by domain (when config contains site root)
        # Includes fallback URLs for sites that block direct requests
        self.rss_overrides = {
            'ria.ru': 'https://ria.ru/export/rss2/archive/index.xml',
            'lenta.ru': 'https://lenta.ru/rss/',
            'www.gazeta.ru': None,
            'gazeta.ru': None,
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
            'riamo.ru': None,
            'mosregtoday.ru': None,  # HTML only
            'mosreg.ru': None,  # HTML only, блокирует RSS
            # Yahoo News - используем официальные RSS фиды (стабильно, без consent/JS)
            # http://news.yahoo.com/rss (общий фид)
            # http://rss.news.yahoo.com/rss/world (world news)
            # https://news.yahoo.com/rss/us (US news)
            'news.yahoo.com': 'https://news.yahoo.com/rss/',
            # rss.news.yahoo.com обрабатывается как прямой RSS URL (heuristic)
        }

        # We'll dynamically build source list from `SOURCES_CONFIG` so all configured
        # sources are actually collected. Each entry will be classified as 'rss' or 'html'.
        self._configured_sources = []  # list of tuples (fetch_url, source_name, category, type)
        _seen_entries = set()
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
                            base = self._rsshub_bases[0] if self._rsshub_bases else ''

                            source_name = channel  # Use short name like 'mash' instead of 't.me/mash'
                            if base:
                                fetch_url = f"{base}/telegram/channel/{channel}"
                                logger.info(f"Telegram channel {channel} using RSSHub: {fetch_url}")
                                entries_to_add.append((fetch_url, source_name, cfg.get('category', 'russia'), 'rss'))
                            else:
                                logger.warning(f"RSSHub not configured for Telegram channel {channel}")
                        # x.com / twitter.com accounts: use RSSHub if configured
                        elif 'x.com' in domain or 'twitter.com' in domain:
                            # Extract username from URL like https://x.com/username
                            username = src.replace('https://x.com/', '').replace('http://x.com/', '').replace('https://twitter.com/', '').replace('http://twitter.com/', '').replace('@', '').strip('/')
                            base = self._rsshub_bases[0] if self._rsshub_bases else ''

                            source_name = f"@{username}"  # Use @username format
                            if base:
                                fetch_url = f"{base}/twitter/user/{username}"
                                logger.info(f"X/Twitter account {username} using RSSHub: {fetch_url}")
                                entries_to_add.append((fetch_url, source_name, cfg.get('category', 'russia'), 'rss'))
                            else:
                                logger.warning(f"RSSHub not configured for X/Twitter account {username}")
                        else:
                            fetch_url = src
                            src_type = 'html'
                            source_name = domain
                            logger.info(f"Source {domain} using HTML parsing: {fetch_url}")
                            entries_to_add.append((fetch_url, source_name, cfg.get('category', 'russia'), src_type))

                for entry in entries_to_add:
                    entry_key = (entry[0], entry[1])
                    if entry_key in _seen_entries:
                        continue
                    _seen_entries.add(entry_key)
                    self._configured_sources.append(entry)
                    self.source_health.setdefault(entry[1], False)
        
        # Log summary of configured sources
        telegram_sources = []
        seen_telegram = set()
        for s in self._configured_sources:
            if 'telegram' in s[0].lower() or any(x in s[0] for x in ['t.me', 'telegram']):
                if s[1] not in seen_telegram:
                    telegram_sources.append(s[1])
                    seen_telegram.add(s[1])
        other_sources = [s[1] for s in self._configured_sources if s[1] not in seen_telegram]
        if telegram_sources:
            logger.info(f"Configured Telegram channels for collection: {telegram_sources}")
        logger.info(f"Total configured sources: {len(self._configured_sources)} (Telegram: {len(telegram_sources)}, Others: {len(other_sources)})")
    
    def _in_cooldown(self, url: str) -> bool:
        """Check if URL is in cooldown period"""
        return self._cooldown_until.get(url, 0) > time.time()
    
    def _set_cooldown(self, url: str, seconds: int = 600):
        """Set cooldown for URL (default 10 minutes)"""
        self._cooldown_until[url] = time.time() + seconds
        logger.warning(f"Cooldown set for {url} for {seconds}s")

    def _note_source_failure(self, url: str) -> None:
        if not url:
            return
        now = time.time()
        last = self._source_error_last.get(url, 0)
        if now - last > self._source_error_window:
            self._source_error_streak[url] = 0
        self._source_error_last[url] = now
        self._source_error_streak[url] = self._source_error_streak.get(url, 0) + 1
        if self._source_error_streak[url] >= self._source_error_streak_limit:
            self._set_cooldown(url, seconds=self._source_error_cooldown_seconds)
            self._source_error_streak[url] = 0

    def _normalize_rsshub_bases(self, base_url: str | None, mirrors: list[str] | None) -> list[str]:
        bases = []
        for raw in [base_url] + (mirrors or []):
            if not raw:
                continue
            base = raw.strip()
            if not base:
                continue
            if not base.startswith('http'):
                base = f"https://{base}"
            base = base.rstrip('/')
            if base not in bases:
                bases.append(base)
        return bases

    def _get_rsshub_mirror_urls(self, url: str) -> list[str]:
        if not self._rsshub_bases:
            return []
        current_base = None
        path = None
        for base in self._rsshub_bases:
            if url.startswith(base):
                current_base = base
                path = url[len(base):]
                break
        if path is None:
            return []
        return [f"{base}{path}" for base in self._rsshub_bases if base != current_base]

    async def _try_rsshub_mirrors(self, url: str, source_name: str) -> list[Dict]:
        for mirror_url in self._get_rsshub_mirror_urls(url):
            try:
                items = await self.rss_parser.parse(mirror_url, source_name)
                if items:
                    logger.info(f"RSSHub mirror used for {source_name}: {mirror_url}")
                    return items
            except Exception:
                continue
        return []

    def _should_skip_article_fetch(self, source_name: str, item_url: str | None) -> bool:
        target = f"{source_name or ''} {item_url or ''}".lower()
        return any(domain in target for domain in (
            'ren.tv',
            'gazeta.ru',
            'iz.ru',
            'rg.ru',
            'russian.rt.com',
        ))

    def _classify_error(self, error: Exception) -> tuple[str, str | None]:
        status_code = None
        if hasattr(error, "response"):
            status_code = getattr(error.response, "status_code", None)
        if status_code:
            return f"HTTP_{status_code}", None

        if isinstance(error, asyncio.TimeoutError):
            return "TIMEOUT", None

        if isinstance(error, (json.JSONDecodeError, ValueError)):
            return "PARSE_ERROR", None

        if isinstance(error, (ConnectionError, OSError, socket.gaierror)):
            return "CONNECTION_ERROR", None

        error_str = str(error).lower()
        if "timeout" in error_str:
            return "TIMEOUT", None
        if "dns" in error_str or "name or service not known" in error_str:
            return "CONNECTION_ERROR", None
        if "parse" in error_str or "json" in error_str:
            return "PARSE_ERROR", None

        return error.__class__.__name__.upper() or "FETCH_ERROR", str(error)

    def _record_source_error(self, source_name: str, error: Exception) -> None:
        if not self.db or not source_name:
            return
        try:
            error_code, message = self._classify_error(error)
            if message and len(message) > 300:
                message = message[:300]
            self.db.record_source_event(
                source_name,
                "error",
                error_code=error_code,
                error_message=message,
            )
        except Exception as exc:
            logger.debug(f"Failed to record source error for {source_name}: {exc}")

    def _coerce_datetime(self, value) -> datetime | None:
        if not value:
            return None
        from utils.date_parser import parse_datetime_value
        return parse_datetime_value(value)

    async def _fetch_article_html(self, url: str) -> str | None:
        try:
            from net.http_client import get_http_client
            http_client = await get_http_client()
            response = await http_client.get(url, retries=2)
            return response.text
        except Exception as e:
            logger.debug(f"Failed to fetch article HTML: {type(e).__name__}: {str(e)[:80]}")
            try:
                import httpx

                async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                    response = await client.get(url)
                    if response.status_code == 200:
                        return response.text
            except Exception as fallback_err:
                logger.debug(f"Fallback HTML fetch failed: {type(fallback_err).__name__}: {str(fallback_err)[:80]}")
            return None
    
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
                    tasks.append((
                        source_name,
                        fetch_url,
                        self._collect_with_timeout(fetch_url, source_name, self._collect_from_rss(fetch_url, source_name, category)),
                    ))
                else:
                    tasks.append((
                        source_name,
                        fetch_url,
                        self._collect_with_timeout(fetch_url, source_name, self._collect_from_html(fetch_url, source_name, category)),
                    ))
            
            # Запускаем все параллельно
            results = await asyncio.gather(*[t[2] for t in tasks], return_exceptions=True)

            # Reset last collection stats
            self.last_collected_counts = {}
            self.last_collection_at = time.time()
            
            # Initialize all configured sources to 0 (will update below)
            for fetch_url, source_name, category, src_type in self._configured_sources:
                self.last_collected_counts[source_name] = 0
            
            # Собираем результаты
            for (source_name, fetch_url, _task), result in zip(tasks, results):
                if isinstance(result, list):
                    count = len(result)
                    self.last_collected_counts[source_name] = count
                    all_news.extend(result)
                    self.source_health[source_name] = True
                    if count > 0:
                        logger.info(f"{source_name}: collected {count} items")
                    else:
                        logger.warning(f"{source_name}: 0 items (no new content or parsing issue)")
                elif isinstance(result, Exception):
                    logger.error(f"{source_name}: {type(result).__name__}: {result}")
                    self.source_health[source_name] = False
                    self._note_source_failure(fetch_url)
                    # Ensure we still record 0 for failed sources so they show in status
                    self.last_collected_counts[source_name] = 0
            
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
                filtered_news = []
                for item in news:
                    title = item.get('title', '')
                    text = item.get('text', '') or item.get('lead_text', '')
                    item_url = item.get('url', '')
                    published_at = self._coerce_datetime(item.get('published_at'))
                    published_date = item.get('published_date')
                    published_time = item.get('published_time')
                    published_confidence = (item.get('published_confidence') or 'none').lower()
                    published_source = item.get('published_source')

                    html = None
                    is_lenta = 'lenta.ru' in source_name
                    is_ria = 'ria.ru' in source_name

                    is_yahoo = source_name in ('news.yahoo.com', 'rss.news.yahoo.com')
                    skip_article_fetch = self._should_skip_article_fetch(source_name, item_url)
                    if not published_at or is_lenta or is_ria or not text or len(text.strip()) < 120:
                        if item_url and not is_yahoo and not skip_article_fetch:
                            html = await self._fetch_article_html(item_url)

                    if html and (not published_at or published_confidence in ('none', 'low')):
                        info = parse_published_info(html, item_url)
                        rank = {'high': 3, 'medium': 2, 'low': 1, 'none': 0}
                        if rank.get(info.get('published_confidence', 'none'), 0) >= rank.get(published_confidence, 0):
                            published_at = info.get('published_at') or published_at
                            published_date = info.get('published_date') or published_date
                            published_time = info.get('published_time') or published_time
                            published_confidence = info.get('published_confidence', published_confidence)
                            published_source = info.get('published_source') or published_source

                    raw_text = text or ""
                    extraction_method = 'rss'
                    if html:
                        extracted = None
                        if is_lenta:
                            extracted = extract_lenta(html)
                            extraction_method = 'site:lenta'
                        elif is_ria:
                            extracted = extract_ria(html)
                            extraction_method = 'site:ria'
                        if not extracted:
                            extracted = await extract_article_text(html, max_length=5000)
                            if extracted:
                                extraction_method = 'trafilatura'
                        if extracted:
                            raw_text = extracted
                    
                    # AI text cleaning (optional for RSS)
                    clean_text = raw_text
                    if self.ai_client and raw_text:
                        ai_clean = await self._clean_text_with_ai(title, raw_text, source_type='rss')
                        if ai_clean:
                            clean_text = ai_clean
                            extraction_method = f"{extraction_method}+ai"

                    is_rsshub_telegram = '/telegram/channel/' in url
                    is_rsshub_x = '/twitter/user/' in url
                    min_score = 0.65 if (is_lenta or is_ria) else 0.55
                    min_len = 400 if (is_lenta or is_ria) else 20
                    used_title_fallback = False
                    if (not clean_text or len(clean_text.strip()) < min_len) and title:
                        clean_text = title.strip()
                        used_title_fallback = True

                    score, _meta = content_quality_score(clean_text, title)
                    if used_title_fallback and not (is_lenta or is_ria):
                        min_score = 0.2
                    if is_rsshub_telegram or is_rsshub_x:
                        min_score = 0.4
                        min_len = 40
                    if not clean_text or len(clean_text.strip()) < min_len or is_low_quality(score, threshold=min_score):
                        logger.debug(
                            "Skipping low quality RSS item: "
                            f"source={source_name} len={len(clean_text or '')} score={score:.2f} "
                            f"min_len={min_len} min_score={min_score} title={title[:50]}"
                        )
                        continue

                    lang = detect_language(clean_text, title)
                    checksum = compute_checksum(clean_text)
                    simhash = compute_simhash(clean_text, title=title)
                    normalized_url = normalize_url(item_url) if item_url else ""
                    url_hash = compute_url_hash(normalized_url) if normalized_url else ""
                    if not published_at:
                        fallback_dt = self._coerce_datetime(item.get('fetched_at')) or datetime.utcnow()
                        published_at = fallback_dt
                        published_confidence = 'surrogate'
                    pub_iso = published_at.isoformat() if published_at else None
                    if published_at and not published_date:
                        published_date, published_time = split_date_time(published_at)
                    
                    # Classify by content
                    detected_category = self.classifier.classify(title, clean_text, item_url)
                    
                    # For trusted sources like Yahoo News/Reuters/etc, use source category directly (skip AI override)
                    # For other sources, allow AI to optionally override
                    skip_ai_verification = source_name in ['news.yahoo.com', 'rss.news.yahoo.com', 'regions.ru']
                    
                    # Optional AI category verification (if client provided and not skipped)
                    if self.ai_client and detected_category and not skip_ai_verification:
                        ai_category = await self._verify_with_ai(title, clean_text, detected_category)
                        if ai_category:
                            detected_category = ai_category

                    # Force Yahoo News to world hashtag
                    if source_name in ['news.yahoo.com', 'rss.news.yahoo.com']:
                        detected_category = 'world'

                    item['category'] = detected_category or category
                    item['raw_text'] = raw_text
                    item['clean_text'] = clean_text
                    item['checksum'] = checksum
                    item['simhash'] = simhash
                    item['language'] = lang
                    item['published_at'] = pub_iso
                    item['published_date'] = published_date
                    item['published_time'] = published_time
                    item['published_confidence'] = published_confidence
                    item['published_source'] = published_source
                    if not item.get('fetched_at'):
                        item['fetched_at'] = datetime.utcnow().isoformat()
                    item['extraction_method'] = extraction_method
                    item['quality_score'] = score
                    if item_url:
                        item['domain'] = urlparse(item_url).netloc.lower()
                        item['url_normalized'] = normalized_url
                        item['url_hash'] = url_hash
                    item['text'] = clean_text
                    filtered_news.append(item)
                return filtered_news
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
                elif '503' in error_str and '/telegram/channel/' in url:
                    mirror_items = await self._try_rsshub_mirrors(url, source_name)
                    if mirror_items:
                        return mirror_items
                    self._set_cooldown(url, 300)
                    logger.warning(f"⚠️ RSSHub Telegram feed unavailable for {source_name} (503), will retry in 5 min")
                elif '503' in error_str and '/twitter/' in url:
                    # 503 from RSSHub Twitter/X feeds - likely API issues, short cooldown
                    self._set_cooldown(url, 300)
                    logger.warning(f"⚠️ RSSHub Twitter/X feed unavailable for {source_name} (503), will retry in 5 min")
                self._note_source_failure(url)
                self._record_source_error(source_name, e)
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
                if not news:
                    rss_fallback = await self._try_fallback_rss(url, source_name, category)
                    if rss_fallback:
                        return rss_fallback
                filtered_news = []
                for item in news:
                    title = item.get('title', '')
                    text = item.get('text', '') or item.get('lead_text', '')
                    item_url = item.get('url', '')

                    published_at = self._coerce_datetime(item.get('published_at'))
                    published_date = item.get('published_date')
                    published_time = item.get('published_time')
                    published_confidence = (item.get('published_confidence') or 'none').lower()
                    published_source = item.get('published_source')
                    html = None
                    is_lenta = 'lenta.ru' in source_name
                    is_ria = 'ria.ru' in source_name

                    skip_article_fetch = self._should_skip_article_fetch(source_name, item_url)
                    if item_url and not skip_article_fetch:
                        html = await self._fetch_article_html(item_url)

                    if html and (not published_at or published_confidence in ('none', 'low')):
                        info = parse_published_info(html, item_url)
                        rank = {'high': 3, 'medium': 2, 'low': 1, 'none': 0}
                        if rank.get(info.get('published_confidence', 'none'), 0) >= rank.get(published_confidence, 0):
                            published_at = info.get('published_at') or published_at
                            published_date = info.get('published_date') or published_date
                            published_time = info.get('published_time') or published_time
                            published_confidence = info.get('published_confidence', published_confidence)
                            published_source = info.get('published_source') or published_source

                    raw_text = text or ""
                    extraction_method = 'html'
                    if html:
                        extracted = None
                        if is_lenta:
                            extracted = extract_lenta(html)
                            extraction_method = 'site:lenta'
                        elif is_ria:
                            extracted = extract_ria(html)
                            extraction_method = 'site:ria'
                        if not extracted:
                            extracted = await extract_article_text(html, max_length=5000)
                            if extracted:
                                extraction_method = 'trafilatura'
                        if extracted:
                            raw_text = extracted
                    
                    # AI text cleaning (MANDATORY for HTML sources to remove navigation garbage)
                    clean_text = raw_text
                    if self.ai_client and raw_text:
                        ai_clean = await self._clean_text_with_ai(title, raw_text, source_type='html')
                        if ai_clean:
                            clean_text = ai_clean
                            extraction_method = f"{extraction_method}+ai"

                    min_score = 0.65 if (is_lenta or is_ria) else 0.55
                    min_len = 400 if (is_lenta or is_ria) else 40
                    used_title_fallback = False
                    if (not clean_text or len(clean_text.strip()) < min_len) and title:
                        clean_text = title.strip()
                        used_title_fallback = True

                    score, _meta = content_quality_score(clean_text, title)
                    if used_title_fallback and not (is_lenta or is_ria):
                        min_score = 0.2
                    if not clean_text or len(clean_text.strip()) < min_len or is_low_quality(score, threshold=min_score):
                        logger.debug(
                            "Skipping low quality HTML item: "
                            f"source={source_name} len={len(clean_text or '')} score={score:.2f} "
                            f"min_len={min_len} min_score={min_score} title={title[:50]}"
                        )
                        continue

                    lang = detect_language(clean_text, title)
                    checksum = compute_checksum(clean_text)
                    simhash = compute_simhash(clean_text, title=title)
                    normalized_url = normalize_url(item_url) if item_url else ""
                    url_hash = compute_url_hash(normalized_url) if normalized_url else ""
                    if not published_at:
                        fallback_dt = self._coerce_datetime(item.get('fetched_at')) or datetime.utcnow()
                        published_at = fallback_dt
                        published_confidence = 'surrogate'
                    pub_iso = published_at.isoformat() if published_at else None
                    if published_at and not published_date:
                        published_date, published_time = split_date_time(published_at)
                    
                    # Classify by content
                    detected_category = self.classifier.classify(title, clean_text, item_url)
                    
                    # For trusted sources (Telegram channels, news agencies), skip AI verification
                    skip_ai_verification = source_name in ['news.yahoo.com', 'rss.news.yahoo.com', 'regions.ru']
                    
                    # Optional AI category verification (if client provided and not skipped)
                    if self.ai_client and detected_category and not skip_ai_verification:
                        ai_category = await self._verify_with_ai(title, clean_text, detected_category)
                        if ai_category:
                            detected_category = ai_category

                    # Force Yahoo News to world hashtag
                    if source_name in ['news.yahoo.com', 'rss.news.yahoo.com']:
                        detected_category = 'world'

                    item['category'] = detected_category or category
                    item['raw_text'] = raw_text
                    item['clean_text'] = clean_text
                    item['checksum'] = checksum
                    item['simhash'] = simhash
                    item['language'] = lang
                    item['published_at'] = pub_iso
                    item['published_date'] = published_date
                    item['published_time'] = published_time
                    item['published_confidence'] = published_confidence
                    item['published_source'] = published_source
                    if not item.get('fetched_at'):
                        item['fetched_at'] = datetime.utcnow().isoformat()
                    item['extraction_method'] = extraction_method
                    item['quality_score'] = score
                    if item_url:
                        item['domain'] = urlparse(item_url).netloc.lower()
                        item['url_normalized'] = normalized_url
                        item['url_hash'] = url_hash
                    item['text'] = clean_text
                    filtered_news.append(item)
                return filtered_news
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
                    self._record_source_error(source_name, e)
                    self._note_source_failure(url)
                    return []
                
                self._note_source_failure(url)
                self._record_source_error(source_name, e)
                logger.error(f"Error collecting from HTML {source_name} ({url}): {e}", exc_info=False)
                return []

    async def _collect_with_timeout(self, url: str, source_name: str, coro) -> List[Dict]:
        try:
            return await asyncio.wait_for(coro, timeout=self._source_collect_timeout)
        except asyncio.TimeoutError as e:
            logger.warning(f"Timeout collecting from {source_name} ({url})")
            self._note_source_failure(url)
            self._record_source_error(source_name, e)
            return []

    async def _try_fallback_rss(self, url: str, source_name: str, category: str) -> List[Dict]:
        """Try common RSS endpoints when HTML parsing yields no items."""
        from urllib.parse import urlparse

        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            return []
        if parsed.netloc.lower() in self._rss_fallback_blocklist:
            return []

        base = f"{parsed.scheme}://{parsed.netloc}"
        candidates = [
            f"{base}/rss",
            f"{base}/rss.xml",
            f"{base}/feed",
            f"{base}/feed.xml",
            f"{base}/export/rss.xml",
            f"{base}/rss/all",
            f"{base}/rss/all.xml",
        ]
        for candidate in candidates:
            try:
                items = await self.rss_parser.parse(candidate, source_name)
                if items:
                    logger.info(f"Fallback RSS used for {source_name}: {candidate}")
                    return items
            except Exception:
                continue
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
            # ⚠️ DISABLED: AI category verification is redundant
            # The keyword classifier already achieves 95%+ accuracy
            # Disabling this saves ~250 tokens per news item (~70% cost reduction)
            logger.debug("AI category verification disabled (keyword classifier sufficient)")
            return None
            
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
            # Sandbox: honor AI cleanup level
            try:
                from config.railway_config import APP_ENV
            except (ImportError, ValueError):
                from config.config import APP_ENV

            cleanup_level = 3
            if APP_ENV == "sandbox" and self.bot:
                try:
                    from core.services.access_control import AILevelManager
                    owner_id = None
                    if hasattr(self.bot, "_get_sandbox_filter_user_id"):
                        owner_id = self.bot._get_sandbox_filter_user_id()
                    if owner_id:
                        ai_manager = AILevelManager(self.bot.db)
                        cleanup_level = ai_manager.get_level(str(owner_id), 'cleanup')
                except Exception as e:
                    logger.debug(f"AI cleanup level check failed: {e}")

            if APP_ENV == "sandbox" and cleanup_level == 0:
                return None

            # ⚠️ OPTIMIZATION: Skip AI cleaning for RSS sources
            # RSS feeds are already clean (no navigation, ads, etc.)
            # Only HTML scraped content needs AI cleaning
            if source_type == 'rss':
                logger.debug("Skipping AI text cleaning for RSS source (already clean)")
                return None  # Will use original text
            
            # Check if AI verification is enabled via bot toggle
            if self.bot and not self.bot.ai_verification_enabled:
                return None
            
            # Fallback to config if bot reference not available
            if not self.bot:
                from config.config import AI_CATEGORY_VERIFICATION_ENABLED
                if not AI_CATEGORY_VERIFICATION_ENABLED:
                    return None
            
            # AI cleaning for HTML sources only
            clean_text, token_usage = await self.ai_client.extract_clean_text(title, text, level=cleanup_level)
            
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
