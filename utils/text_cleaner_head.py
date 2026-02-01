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
        
        # Фильтруем мусорный текст от РИА Новости (формы регистрации)
        junk_patterns = [
            r'Регистрация пройдена успешно',
            r'Пожалуйста.*перейдите по ссылке из письма',
            r'Отправить еще раз',
            r'Войти через',
            r'Авторизуйтесь'
        ]
        for pattern in junk_patterns:
            text = re.sub(pattern, '', text, flags=re.IGNORECASE)
        
        # Очищаем от множественных пробелов и переводов строк
        text = re.sub(r'\s+', ' ', text)  # Множественные пробелы → один
        text = text.strip()
        
        return text
    except Exception as e:
        logger.error(f"Error cleaning HTML: {e}")
        return html_text
