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
        text = re.sub(r'\s+', ' ', text)
        text = text.strip()
        
        return text
    except Exception as e:
        logger.error(f"Error cleaning HTML: {e}")
        return html_text


def extract_first_paragraph(text: str, min_length: int = 50) -> str:
    """
    Извлекает первый осмысленный абзац
    """
    if not text:
        return ""
    
    # Разбиваем на параграфы
    paragraphs = [p.strip() for p in text.split('\n') if p.strip()]
    
    for paragraph in paragraphs:
        if len(paragraph) >= min_length:
            return paragraph
    
    # Если нет полноценных параграфов, берём первый с нужной длиной
    for paragraph in text.split('.'):
        cleaned = paragraph.strip()
        if len(cleaned) >= min_length:
            return cleaned + '.'
    
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
    Форматирует новость в сообщение для Telegram (1000 char hard limit)
    """
    # Фильтруем явные команды и URLs
    if not title or len(title) < 10:
        return ""  # Слишком короткий заголовок (вероятно команда)
    
    if title.startswith("/"):
        return ""  # Похоже на команду
    
    # Очищаем текст
    text = clean_html(text) if text else ""
    paragraph = extract_first_paragraph(text)
    paragraph = truncate_text(paragraph)
    
    # Экранируем спецсимволы для Markdown
    title = escape_markdown(title)
    paragraph = escape_markdown(paragraph)
    source_name = escape_markdown(source_name)
    
    # Формируем сообщение
    message = f"*{title}*\n\n"
    message += f"{paragraph}\n\n"
    message += f"Источник: {source_name}\n{source_url}\n\n"
    message += category
    
    # Hard limit for telegram (4096 max, but use 1000 for safety)
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
