"""
Управление базой данных для хранения опубликованных новостей
"""
import sqlite3
from datetime import datetime
from typing import List, Tuple, Optional
import logging
import os

logger = logging.getLogger(__name__)


class NewsDatabase:
    """Управление БД опубликованных новостей"""
    
    def __init__(self, db_path: str = 'db/news.db'):
        self.db_path = db_path
        self._ensure_db_exists()
    
    def _ensure_db_exists(self):
        """Создает таблицу, если её нет"""
        os.makedirs(os.path.dirname(self.db_path) or '.', exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS published_news (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT UNIQUE NOT NULL,
                title TEXT NOT NULL,
                source TEXT NOT NULL,
                category TEXT NOT NULL,
                published_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()
        conn.close()
        logger.info(f"Database initialized at {self.db_path}")
    
    def add_news(self, url: str, title: str, source: str, category: str) -> bool:
        """
        Добавляет новость в БД.
        Возвращает True если добавлена, False если уже была.
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO published_news (url, title, source, category)
                VALUES (?, ?, ?, ?)
            ''', (url, title, source, category))
            conn.commit()
            conn.close()
            logger.debug(f"News added: {url}")
            return True
        except sqlite3.IntegrityError:
            logger.debug(f"News already exists: {url}")
            return False
        except Exception as e:
            logger.error(f"Error adding news to DB: {e}")
            return False
    
    def is_published(self, url: str) -> bool:
        """Проверяет, была ли новость уже опубликована"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('SELECT 1 FROM published_news WHERE url = ?', (url,))
            result = cursor.fetchone()
            conn.close()
            return result is not None
        except Exception as e:
            logger.error(f"Error checking published news: {e}")
            return False
    
    def get_recent_news(self, limit: int = 100) -> List[Tuple]:
        """Получает последние опубликованные новости"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, url, title, source, category, published_at
                FROM published_news
                ORDER BY published_at DESC
                LIMIT ?
            ''', (limit,))
            results = cursor.fetchall()
            conn.close()
            return results
        except Exception as e:
            logger.error(f"Error getting recent news: {e}")
            return []
    
    def get_stats(self) -> dict:
        """Получает статистику БД"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) FROM published_news')
            total = cursor.fetchone()[0]
            cursor.execute('''
                SELECT COUNT(*) FROM published_news 
                WHERE published_at > datetime('now', '-1 day')
            ''')
            today = cursor.fetchone()[0]
            conn.close()
            return {'total': total, 'today': today}
        except Exception as e:
            logger.error(f"Error getting stats: {e}")
            return {'total': 0, 'today': 0}
