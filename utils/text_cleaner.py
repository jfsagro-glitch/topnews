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


def format_telegram_message(title: str, text: str, source_name: str, 
                           source_url: str, category: str) -> str:
    """
    Форматирует новость в сообщение для Telegram
    """
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
    
    return message


def escape_markdown(text: str) -> str:
    """
    Экранирует специальные символы Markdown
    """
    special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    for char in special_chars:
        text = text.replace(char, f'\\{char}')
    return text
