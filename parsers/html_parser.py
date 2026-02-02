"""
HTML парсер для сайтов новостей
"""
import logging
import asyncio
from typing import List, Dict
from datetime import datetime
from bs4 import BeautifulSoup
from net.http_client import get_http_client
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
            http_client = await get_http_client()
            response = await http_client.get(url, retries=2)
            content = response.text
            
            # Парсинг HTML может быть затратным - выполняем в отдельном потоке
            soup = await asyncio.to_thread(
                lambda: BeautifulSoup(content, 'html.parser')
            )
            
            # Ищем элементы новостей (div с классом содержащим 'news' или 'article')
            article_elements = self._find_article_elements(soup, source_name)
            
            for elem in article_elements[:10]:  # Берём до 10
                news_item = self._extract_news_from_element(elem, url, source_name)
                if news_item and news_item.get('url'):
                    # Если текста мало — пробуем подтянуть из страницы статьи
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
    
    def _find_article_elements(self, soup: BeautifulSoup, source_name: str):
        """Находит элементы статей в HTML"""
        
        # Специфичные селекторы для конкретных сайтов
        if 'ren.tv' in source_name.lower() or 'ren.tv' in str(soup)[:1000].lower():
            # Ren.TV использует специальные классы
            articles = soup.find_all('article', class_=lambda x: x and 'news-card' in x.lower())
            if not articles:
                articles = soup.find_all('div', class_=lambda x: x and ('card' in x.lower() or 'news' in x.lower()))
            if articles:
                logger.debug(f"Found {len(articles)} ren.tv articles")
                return articles[:15]
        
        if 'regions.ru' in source_name.lower():
            # Regions.ru структура
            articles = soup.find_all(['article', 'div'], class_=lambda x: x and ('news' in x.lower() or 'item' in x.lower()))
            if articles:
                logger.debug(f"Found {len(articles)} regions.ru articles")
                return articles[:15]
        
        if 'iz.ru' in source_name.lower() or 'известия' in source_name.lower():
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
            
            # Фильтруем UI элементы и бесполезный контент
            if not title or not url:
                return None
            
            # Список "шумовых" фраз которые указывают на UI элементы, а не на новости
            noise_phrases = [
                'все темы', 'выберите', 'категория', 'подписка',
                'меню', 'навигация', 'войти', 'зарегистр', 'реклама',
                'больше', 'ещё', 'далее', 'читать', 'свернуть', 'развернуть',
                'поделиться', 'ошибка', 'загруж', 'filter', 'sort', 'view',
                # Навигационные элементы новостных сайтов
                'главное россия мир', 'экономика силовые', 'эксклюзивы статьи галереи',
                'спецпроекты исследования', 'хочешь видеть только', 'lenta.ru главное',
                'теперь вы знаете', 'забота о себе', 'из жизни', 'среда обитания',
                # 360.ru
                'все новости истории эфир', 'суперчат 360', 'балашиха богородский', 'котельники красногорск',
                # RIAMO
                'события московской области', 'специальная военная операция', 'все темы сегодня',
                # mosregtoday.ru
                'новости чтиво эксклюзивы', 'выберите город поиск', 'подмосковье сегодня',
                # Общие
                'актуально беспилотник', 'чума xxi века',
                # Lenta.ru заголовки-категории
                'уход за собой:', 'политика:', 'украина:', 'lenta.ru', 'забота о себе:',
                # Источники в заголовках
                'тасс:', 'газета.ru:', 'рбк:', 'коммерсантъ:', 'interfax:', 'известия:', 'rt:',
                'дзен:', 'ren.tv:', 'regions.ru:',
                # Типичные служебные заголовки
                'все материалы', 'главная страница', 'все новости', 'подписаться', 'следите',
                'читайте также', 'смотрите также', 'редакция', 'о проекте', 'контакты',
                'лента новостей', 'картина дня', 'последние новости', 'новости партнёров',
                'новости партнеров', 'материалы по теме', 'похожие материалы', 'поиск',
                'rss', 'search', 'menu', 'mobile',
            ]
            
            title_lower = title.lower()
            for phrase in noise_phrases:
                if phrase in title_lower:
                    logger.debug(f"Filtered noise phrase: {title}")
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
                'published_at': datetime.now().isoformat(),
            }
        
        except Exception as e:
            logger.debug(f"Error extracting news from element: {e}")
            return None

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
