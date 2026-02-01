"""
HTML парсер для сайтов новостей
"""
import logging
import ssl
import certifi
import asyncio
import random
from typing import List, Dict
import aiohttp
import asyncio
from bs4 import BeautifulSoup
from datetime import datetime

logger = logging.getLogger(__name__)


class HTMLParser:
    """Парсит HTML-страницы новостей"""
    
    def __init__(self, timeout: int = 30):
        self.timeout = timeout
    
    async def parse(self, url: str, source_name: str) -> List[Dict]:
        """
        Парсит HTML страницу и пытается найти новости
        Это базовая реализация - может быть расширена для каждого сайта
        """
        news_items = []
        
        try:
            user_agents = [
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36',
                'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.1 Safari/605.1.15'
            ]
            headers = {
                'User-Agent': random.choice(user_agents),
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9',
                'Connection': 'keep-alive',
            }
            ssl_ctx = ssl.create_default_context(cafile=certifi.where())

            # Conservative rate-limiting + retries with jitter
            min_delay = 0.3
            max_delay = 1.0
            attempts = 3

            async with aiohttp.ClientSession(headers=headers, trust_env=False) as session:
                for attempt in range(1, attempts + 1):
                    try:
                        async with session.get(url, timeout=self.timeout, ssl=ssl_ctx, allow_redirects=True) as response:
                            if response.status != 200:
                                logger.warning(f"Failed to fetch {url}: {response.status}")
                                return news_items

                            content = await response.text(errors='ignore')
                            break
                    except ssl.SSLCertVerificationError as e:
                        logger.warning(f"SSL verification failed for {url}: {e}; retrying insecurely")
                        # Retry once without SSL verification (best-effort fallback)
                        try:
                            async with session.get(url, timeout=self.timeout, ssl=False, allow_redirects=True) as response:
                                if response.status != 200:
                                    logger.warning(f"Failed to fetch {url} (insecure): {response.status}")
                                    return news_items
                                content = await response.text(errors='ignore')
                                break
                        except Exception as ie:
                            logger.debug(f"Insecure retry failed for {url}: {ie}")
                            raise ie
                    except Exception as e:
                        logger.debug(f"Attempt {attempt} failed for {url}: {e}")
                        if attempt == attempts:
                            logger.error(f"Error fetching {url}: {e}")
                            return news_items
                        wait = min_delay + random.random() * (max_delay - min_delay)
                        await asyncio.sleep(wait)
            
            soup = BeautifulSoup(content, 'html.parser')
            
            # Ищем элементы новостей (div с классом содержащим 'news' или 'article')
            article_elements = self._find_article_elements(soup, source_name)
            
            for elem in article_elements[:10]:  # Берём до 10
                news_item = self._extract_news_from_element(elem, url, source_name)
                if news_item and news_item.get('url'):
                    news_items.append(news_item)
            
            logger.info(f"Parsed {len(news_items)} items from {source_name} HTML")
            
        except asyncio.TimeoutError:
            logger.error(f"Timeout parsing HTML from {url}")
        except Exception as e:
            logger.error(f"Error parsing HTML from {url}: {e}")
        
        return news_items
    
    def _find_article_elements(self, soup: BeautifulSoup, source_name: str):
        """Находит элементы статей в HTML"""
        # Универсальный поиск по классам/тегам
        articles = soup.find_all(['article', 'div'], class_=lambda x: x and any(
            keyword in x.lower() for keyword in ['news', 'article', 'item', 'post', 'story']
        ))
        
        if not articles:
            # Fallback: берём первые div'ы на странице
            articles = soup.find_all('div', limit=20)
        
        return articles
    
    def _extract_news_from_element(self, elem, base_url: str, source_name: str) -> Dict:
        """Извлекает информацию о новости из HTML элемента"""
        try:
            # Ищем заголовок
            title_elem = elem.find(['h1', 'h2', 'h3', 'h4'])
            title = title_elem.get_text(strip=True) if title_elem else ""
            
            # Ищем ссылку
            link_elem = elem.find('a')
            url = link_elem.get('href', '') if link_elem else ""
            
            # Обработка относительных ссылок
            if url and not url.startswith('http'):
                from urllib.parse import urljoin
                url = urljoin(base_url, url)
            
            # Ищем текст/описание
            text_elem = elem.find(['p', 'span'])
            text = text_elem.get_text(strip=True) if text_elem else ""
            
            if not title or not url:
                return None
            
            return {
                'title': title[:200],
                'url': url,
                'text': text[:500],
                'source': source_name,
                'published_at': datetime.now().isoformat(),
            }
        
        except Exception as e:
            logger.debug(f"Error extracting news from element: {e}")
            return None
