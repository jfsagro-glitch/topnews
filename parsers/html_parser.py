"""
HTML парсер для сайтов новостей
"""
import logging
import asyncio
from typing import List, Dict
from datetime import datetime
from bs4 import BeautifulSoup
import httpx
from net.http_client import get_http_client, DEFAULT_HEADERS
from utils.lead_extractor import extract_lead_from_html

logger = logging.getLogger(__name__)


class HTMLParser:
    """Парсит HTML-страницы новостей"""
    
    def __init__(self, timeout: int = 30):
        self.timeout = timeout
    
    async def parse(self, url: str, source_name: str) -> List[Dict]:
        """
        Парсит HTML страницу и пытается найти новости
        Это базовая реализация - может быть расширена для каждого сайта
        
        Raises:
            httpx.HTTPStatusError: if status code is 403, 429, or other retryable codes
        """
        news_items = []
        
        try:
            timeout_override = self._get_timeout_override(url, source_name)
            headers_override = self._get_headers_override(url, source_name)
            response = await self._fetch_html(
                url,
                timeout_override=timeout_override,
                headers_override=headers_override,
            )
            content = response.text
            
            # Парсинг HTML может быть затратным - выполняем в отдельном потоке
            soup = await asyncio.to_thread(
                lambda: BeautifulSoup(content, 'html.parser')
            )
            
            # Ищем элементы новостей (div с классом содержащим 'news' или 'article')
            article_elements = self._find_article_elements(soup, url, source_name)
            if not article_elements:
                article_elements = self._find_link_candidates(soup, url, source_name)
            
            for elem in article_elements[:10]:  # Берём до 10
                news_item = self._extract_news_from_element(elem, url, source_name)
                if news_item and news_item.get('url'):
                    # Если текста мало — пробуем подтянуть из страницы статьи
                    if not self._should_skip_preview(news_item['url'], source_name):
                        if not news_item.get('text') or len(news_item['text']) < 40:
                            preview = await self._fetch_article_preview(news_item['url'])
                            if preview:
                                news_item['text'] = preview
                    news_items.append(news_item)
            
            logger.info(f"Parsed {len(news_items)} items from {source_name} HTML")
            
        except asyncio.TimeoutError:
            logger.error(f"Timeout parsing HTML from {url}")
            raise
        except Exception as e:
            # Re-raise HTTP errors so SourceCollector can handle them
            if hasattr(e, 'response'):
                raise
            logger.error(f"Error parsing HTML from {url}: {e}")
            raise
        
        return news_items
    
    def _find_article_elements(self, soup: BeautifulSoup, base_url: str, source_name: str):
        """Находит элементы статей в HTML"""
        source_lower = (source_name or "").lower()
        base_lower = (base_url or "").lower()

        def collect_links(include_paths: tuple[str, ...], max_items: int = 15, min_len: int = 12):
            links = []
            for a in soup.find_all('a'):
                href = a.get('href') or ''
                text = a.get_text(strip=True) or ''
                if not href or not text:
                    continue
                if len(text) < min_len:
                    continue
                if not self._is_valid_title(text):
                    continue
                if href.startswith('#'):
                    continue
                if href.startswith('/'):
                    from urllib.parse import urljoin

                    href = urljoin(base_url, href)
                if not href.startswith('http'):
                    continue
                if include_paths and not any(p in href for p in include_paths):
                    continue
                links.append({'title': text, 'url': href})
                if len(links) >= max_items:
                    break
            return links
        
        # Специфичные селекторы для конкретных сайтов
        if 'ren.tv' in source_lower or 'ren.tv' in str(soup)[:1000].lower():
            # Ren.TV использует специальные классы
            articles = soup.find_all('article', class_=lambda x: x and 'news-card' in x.lower())
            if not articles:
                articles = soup.find_all('div', class_=lambda x: x and ('card' in x.lower() or 'news' in x.lower()))
            if articles:
                logger.debug(f"Found {len(articles)} ren.tv articles")
                return articles[:15]
            if '/news' in base_lower:
                links = collect_links(('/news/',), max_items=20, min_len=10)
                if links:
                    logger.debug(f"Found {len(links)} ren.tv links")
                    return links
        
        if 'regions.ru' in source_lower:
            # Regions.ru структура
            articles = soup.find_all(['article', 'div'], class_=lambda x: x and ('news' in x.lower() or 'item' in x.lower() or 'card' in x.lower()))
            if articles:
                logger.debug(f"Found {len(articles)} regions.ru articles")
                return articles[:15]
            if '/news' in base_lower:
                links = collect_links(('/news/', '/article/'), max_items=20, min_len=10)
                if links:
                    logger.debug(f"Found {len(links)} regions.ru links")
                    return links

        if 'mosreg.ru' in source_lower:
            articles = soup.find_all(['article', 'div'], class_=lambda x: x and ('news' in x.lower() or 'item' in x.lower() or 'card' in x.lower()))
            if articles:
                logger.debug(f"Found {len(articles)} mosreg.ru articles")
                return articles[:15]
            if '/sobytiya/novosti' in base_lower:
                links = collect_links(('/sobytiya/novosti/', '/news/'), max_items=20, min_len=10)
                if links:
                    logger.debug(f"Found {len(links)} mosreg.ru links")
                    return links

        if 'mosregtoday.ru' in source_lower:
            articles = soup.find_all(['article', 'div'], class_=lambda x: x and ('news' in x.lower() or 'item' in x.lower() or 'post' in x.lower()))
            if articles:
                logger.debug(f"Found {len(articles)} mosregtoday.ru articles")
                return articles[:15]
            if '/news' in base_lower:
                links = collect_links(('/news/', '/article/'), max_items=20, min_len=10)
                if links:
                    logger.debug(f"Found {len(links)} mosregtoday.ru links")
                    return links

        if 'gazeta.ru' in source_lower:
            articles = soup.find_all(['article', 'div'], class_=lambda x: x and ('news' in x.lower() or 'item' in x.lower() or 'article' in x.lower()))
            if articles:
                logger.debug(f"Found {len(articles)} gazeta.ru articles")
                return articles[:15]
            if '/news' in base_lower:
                links = collect_links(('/news/', '/article/'), max_items=20, min_len=10)
                if links:
                    logger.debug(f"Found {len(links)} gazeta.ru links")
                    return links
        
        if 'iz.ru' in source_lower or 'известия' in source_lower:
            # Известия селекторы
            articles = soup.find_all(['article', 'div'], class_=lambda x: x and ('lenta_news__item' in str(x) or 'node' in x.lower()))
            if not articles:
                articles = soup.find_all('article')
            if articles:
                logger.debug(f"Found {len(articles)} iz.ru articles")
                return articles[:15]
        
        # Универсальный поиск по классам/тегам
        articles = soup.find_all(['article', 'div'], class_=lambda x: x and any(
            keyword in x.lower() for keyword in ['news', 'article', 'item', 'post', 'story']
        ))
        
        if not articles:
            # Fallback: берём первые div'ы на странице
            articles = soup.find_all('div', limit=20)
        
        return articles

    def _get_timeout_override(self, url: str, source_name: str) -> float | None:
        target = f"{source_name or ''} {url or ''}".lower()
        if 'ren.tv' in target or 'gazeta.ru' in target:
            return 40.0
        return None

    def _get_headers_override(self, url: str, source_name: str) -> dict | None:
        target = f"{source_name or ''} {url or ''}".lower()
        if 'ru.investing.com' in target:
            return {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Referer": "https://ru.investing.com/",
                "Origin": "https://ru.investing.com",
            }
        return None

    def _should_skip_preview(self, url: str, source_name: str) -> bool:
        target = f"{source_name or ''} {url or ''}".lower()
        return 'ren.tv' in target or 'gazeta.ru' in target

    async def _fetch_html(
        self,
        url: str,
        timeout_override: float | None = None,
        headers_override: dict | None = None,
    ) -> httpx.Response:
        if not timeout_override:
            http_client = await get_http_client()
            return await http_client.get(url, retries=2, headers=headers_override)

        last_exc = None
        timeout = httpx.Timeout(timeout_override, connect=10.0)
        merged_headers = DEFAULT_HEADERS.copy()
        if headers_override:
            merged_headers.update(headers_override)

        async with httpx.AsyncClient(
            headers=merged_headers,
            timeout=timeout,
            follow_redirects=True,
        ) as client:
            for attempt in range(3):
                try:
                    response = await client.get(url)
                    response.raise_for_status()
                    return response
                except Exception as exc:
                    last_exc = exc
                    if attempt < 2:
                        await asyncio.sleep(1 + attempt)
        raise last_exc
    
    def _extract_news_from_element(self, elem, base_url: str, source_name: str) -> Dict:
        """Извлекает информацию о новости из HTML элемента"""
        try:
            if isinstance(elem, dict):
                title = elem.get('title', '')
                url = elem.get('url', '')
                text = ""
                if not title or not url:
                    return None
                if not self._is_valid_title(title):
                    return None
                return {
                    'title': title[:200],
                    'url': url,
                    'text': text,
                    'source': source_name,
                    'published_at': None,
                }

            # Ищем заголовок
            title_elem = elem.find(['h1', 'h2', 'h3', 'h4'])
            title = title_elem.get_text(strip=True) if title_elem else ""
            
            # Ищем ссылку
            link_elem = elem.find('a') if hasattr(elem, 'find') else None
            url = link_elem.get('href', '') if link_elem else ""
            
            # Обработка относительных ссылок
            if url and not url.startswith('http'):
                from urllib.parse import urljoin
                url = urljoin(base_url, url)
            
            # Ищем текст/описание
            text_elem = elem.find(['p', 'span'])
            text = text_elem.get_text(strip=True) if text_elem else ""
            
            # Фильтруем UI элементы и бесполезный контент
            if not title or not url:
                return None
            
            if not self._is_valid_title(title):
                return None
            
            # Минимальная длина заголовка (не менее 15 символов)
            if len(title) < 15:
                logger.debug(f"Title too short: {title}")
                return None

            # Проверяем что это не просто одно слово
            if len(title.split()) < 3:
                logger.debug(f"Title too short (word count): {title}")
                return None
            
            return {
                'title': title[:200],
                'url': url,
                'text': text[:800],
                'source': source_name,
                'published_at': None,
            }
        
        except Exception as e:
            logger.debug(f"Error extracting news from element: {e}")
            return None

    def _find_link_candidates(self, soup: BeautifulSoup, base_url: str, source_name: str):
        """Fallback: find anchor links that look like articles."""
        candidates = []
        import re

        date_re = re.compile(r"/20\d{2}/\d{2}/\d{2}/")
        source_lower = (source_name or "").lower()
        allow_short = any(domain in source_lower for domain in (
            'mosreg.ru', 'mosregtoday.ru', 'regions.ru', 'ren.tv', 'gazeta.ru',
        ))
        min_len = 8 if allow_short else 10
        max_candidates = 25 if allow_short else 15
        for a in soup.find_all('a'):
            href = a.get('href') or ''
            text = a.get_text(strip=True) or ''
            if not href or not text:
                continue
            if len(text) < min_len:
                continue
            if not self._is_valid_title(text):
                continue
            if href.startswith('#'):
                continue
            if href.startswith('/'):
                from urllib.parse import urljoin

                href = urljoin(base_url, href)
            if not href.startswith('http'):
                continue
            if date_re.search(href) or '/news/' in href or '/story/' in href or '/article/' in href:
                candidates.append({'title': text, 'url': href})
            else:
                candidates.append({'title': text, 'url': href})
            if len(candidates) >= max_candidates:
                break
        return candidates

    def _is_valid_title(self, title: str) -> bool:
        """Return True if title does not look like UI noise."""
        if not title:
            return False
        noise_phrases = [
            'все темы', 'выберите', 'категория', 'подписка',
            'меню', 'навигация', 'войти', 'зарегистр', 'реклама',
            'больше', 'ещё', 'далее', 'читать', 'свернуть', 'развернуть',
            'поделиться', 'ошибка', 'загруж', 'filter', 'sort', 'view',
            'главное россия мир', 'экономика силовые', 'эксклюзивы статьи галереи',
            'спецпроекты исследования', 'хочешь видеть только', 'lenta.ru главное',
            'теперь вы знаете', 'забота о себе', 'из жизни', 'среда обитания',
            'все новости истории эфир', 'суперчат 360', 'балашиха богородский', 'котельники красногорск',
            'события московской области', 'специальная военная операция', 'все темы сегодня',
            'новости чтиво эксклюзивы', 'выберите город поиск', 'подмосковье сегодня',
            'актуально беспилотник', 'чума xxi века',
            'уход за собой:', 'политика:', 'украина:', 'lenta.ru', 'забота о себе:',
            'тасс:', 'газета.ru:', 'рбк:', 'коммерсантъ:', 'interfax:', 'известия:', 'rt:',
            'дзен:', 'ren.tv:', 'regions.ru:',
            'все материалы', 'главная страница', 'все новости', 'подписаться', 'следите',
            'читайте также', 'смотрите также', 'редакция', 'о проекте', 'контакты',
            'лента новостей', 'картина дня', 'последние новости', 'новости партнёров',
            'новости партнеров', 'материалы по теме', 'похожие материалы', 'поиск',
            'rss', 'search', 'menu', 'mobile',
        ]

        title_lower = title.lower()
        for phrase in noise_phrases:
            if phrase in title_lower:
                return False
        return True

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
