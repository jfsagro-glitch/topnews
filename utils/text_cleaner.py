"""
Очистка текста от HTML и лишних элементов
"""
import re
import os
from html import unescape
from bs4 import BeautifulSoup
import logging

logger = logging.getLogger(__name__)


def clean_html(html_text: str) -> str:
    """
    Очищает HTML от тегов и лишних элементов
    Убирает множественные пробелы и переносы
    """
    if not html_text:
        return ""
    
    try:
        # Удаляем скрипты и стили
        # Если передали путь к файлу — откроем файл, иначе используем строковое представление
        if isinstance(html_text, str) and os.path.exists(html_text):
            try:
                with open(html_text, 'r', encoding='utf-8', errors='ignore') as fh:
                    content = fh.read()
            except Exception:
                content = str(html_text)
        else:
            content = str(html_text)

        # If input doesn't contain HTML tags, treat as plain text to avoid
        # BeautifulSoup MarkupResemblesLocatorWarning when content looks like a filename.
        if '<' not in content and '>' not in content:
            text = unescape(content)
            text = re.sub(r'\s+', ' ', text).strip()
            return text

        soup = BeautifulSoup(content, 'html.parser')

        for tag in soup(['script', 'style', 'noscript']):
            tag.decompose()

        # Берём текст
        text = soup.get_text(separator=' ')
        
        # Убираем HTML entities
        text = unescape(text)
        
        # Очищаем от множественных пробелов и переводов строк
        text = re.sub(r'\s+', ' ', text)  # Множественные пробелы → один
        text = text.strip()
        
        return text
    except Exception as e:
        logger.error(f"Error cleaning HTML: {e}")
        return html_text


def extract_first_paragraph(text: str, min_length: int = 30) -> str:
    """
    Извлекает первый осмысленный абзац (компактный)
    """
    if not text:
        return ""
    
    # Убираем лишние пробелы
    text = text.strip()
    
    # Разбиваем на предложения по точке
    sentences = [s.strip() for s in text.split('.') if s.strip()]
    
    # Собираем предложения пока не достигнем нормальной длины (150-200 символов)
    result = []
    current_length = 0
    
    for sentence in sentences:
        if not sentence:
            continue
        if current_length > 150:  # Остановимся на разумной длине
            break
        result.append(sentence)
        current_length += len(sentence) + 1
    
    if result:
        return '. '.join(result) + '.' if result else text[:200]
    
    return text[:200] if len(text) > 200 else text


def truncate_text(text: str, max_length: int = 500) -> str:
    """
    Обрезает текст до максимальной длины
    """
    if len(text) <= max_length:
        return text
    
    # Обрезаем по слову
    truncated = text[:max_length]
    last_space = truncated.rfind(' ')
    if last_space > 0:
        truncated = truncated[:last_space]
    
    return truncated + '...'


def truncate_for_telegram(text: str, max_length: int = 1000) -> str:
    """
    Hard limit for telegram message (1000 chars)
    """
    if len(text) <= max_length:
        return text
    
    truncated = text[:max_length]
    last_space = truncated.rfind(' ')
    if last_space > max_length // 2:
        truncated = truncated[:last_space]
    
    return truncated.rstrip() + '...'


def truncate_for_copy(text: str, max_length: int = 3000) -> str:
    """
    Hard limit for COPY button response (3000 chars)
    """
    if len(text) <= max_length:
        return text
    
    truncated = text[:max_length]
    last_space = truncated.rfind(' ')
    if last_space > max_length // 2:
        truncated = truncated[:last_space]
    
    return truncated.rstrip() + '...'


def format_telegram_message(title: str, text: str, source_name: str, 
                           source_url: str, category: str) -> str:
    """
    Форматирует новость в сообщение для Telegram (компактное, красивое)
    Оптимизировано для отображения в канале без scroll
    """
    # Фильтруем явные команды и URLs
    if not title or len(title) < 15:  # Минимум 15 символов
        return ""
    
    if title.startswith("/"):
        return ""  # Похоже на команду
    
    # Список UI фраз которые должны быть отфильтрованы
    noise_phrases = [
        'все темы', 'выберите', 'категория', 'подписка',
        'меню', 'навигация', 'войти', 'зарегистр', 'реклама',
        'больше', 'ещё', 'далее', 'читать', 'свернуть', 'развернуть',
        'поделиться', 'ошибка', 'загруж',
    ]
    
    title_lower = title.lower()
    for phrase in noise_phrases:
        if phrase in title_lower:
            return ""  # Похоже на UI элемент
    
    # Очищаем текст
    text = clean_html(text) if text else ""
    paragraph = extract_first_paragraph(text)
    paragraph = truncate_text(paragraph, max_length=400)  # Компактнее
    
    # Экранируем спецсимволы для Markdown
    title = escape_markdown(title)
    paragraph = escape_markdown(paragraph)
    source_name = escape_markdown(source_name)
    
    # Компактное форматирование
    message = f"*{title}*\n"
    
    if paragraph:
        # Убираем лишние пробелы
        paragraph = paragraph.strip()
        message += f"\n{paragraph}\n"
    
    # Inline информация о источнике и категории (одна строка)
    message += f"\n_{source_name}_ • {category}"
    
    # Hard limit for telegram (1000 chars)
    message = truncate_for_telegram(message, max_length=1000)
    
    return message


def escape_markdown(text: str) -> str:
    """
    Экранирует специальные символы Markdown
    """
    special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    for char in special_chars:
        text = text.replace(char, f'\\{char}')
    return text
