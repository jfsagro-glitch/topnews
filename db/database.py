"""
Управление базой данных для хранения опубликованных новостей
"""
import sqlite3
import time
from datetime import datetime
from typing import List, Tuple, Optional
import logging
import os
import threading

logger = logging.getLogger(__name__)


class NewsDatabase:
    """Управление БД опубликованных новостей"""
    
    def __init__(self, db_path: str = 'db/news.db'):
        self.db_path = db_path
        os.makedirs(os.path.dirname(self.db_path) or '.', exist_ok=True)

        # Single shared connection + a lock to serialize write operations
        self._conn = sqlite3.connect(self.db_path, timeout=30, check_same_thread=False)
        self._write_lock = threading.Lock()

        # Initialize DB (PRAGMAs + table)
        try:
            cursor = self._conn.cursor()
            try:
                cursor.execute("PRAGMA journal_mode=WAL;")
            except Exception:
                pass
            try:
                cursor.execute("PRAGMA busy_timeout=10000;")
            except Exception:
                pass
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
            self._conn.commit()
        except Exception as e:
            logger.error(f"Error initializing DB: {e}")

        logger.info(f"Database initialized at {self.db_path}")
    
    def _ensure_db_exists(self):
        """Создает таблицу, если её нет"""
        os.makedirs(os.path.dirname(self.db_path) or '.', exist_ok=True)
        # Use a short timeout and enable WAL to reduce "database is locked" errors
        conn = sqlite3.connect(self.db_path, timeout=30, check_same_thread=False)
        cursor = conn.cursor()
        try:
            cursor.execute("PRAGMA journal_mode=WAL;")
        except Exception:
            pass
        try:
            cursor.execute("PRAGMA busy_timeout=5000;")
        except Exception:
            pass
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
        # Retry loop to handle transient "database is locked" errors
        attempts = 3
        for attempt in range(1, attempts + 1):
            try:
                with self._write_lock:
                    cursor = self._conn.cursor()
                    cursor.execute('''
                        INSERT INTO published_news (url, title, source, category)
                        VALUES (?, ?, ?, ?)
                    ''', (url, title, source, category))
                    self._conn.commit()
                    logger.debug(f"News added: {url}")
                    return True
            except sqlite3.IntegrityError:
                logger.debug(f"News already exists: {url}")
                return False
            except sqlite3.OperationalError as oe:
                if 'locked' in str(oe).lower() and attempt < attempts:
                    wait = 0.5 * attempt
                    logger.debug(f"Database locked, retrying in {wait}s (attempt {attempt})")
                    time.sleep(wait)
                    continue
                logger.error(f"OperationalError adding news to DB: {oe}")
                return False
            except Exception as e:
                logger.error(f"Error adding news to DB: {e}")
                return False
    
    def remove_news_by_url(self, url: str) -> bool:
        """
        Удаляет запись новости по URL. Возвращает True если удалена.
        """
        try:
            with self._write_lock:
                cursor = self._conn.cursor()
                cursor.execute('DELETE FROM published_news WHERE url = ?', (url,))
                self._conn.commit()
                deleted = cursor.rowcount > 0
                if deleted:
                    logger.debug(f"Removed news from DB: {url}")
                return deleted
        except sqlite3.OperationalError as oe:
            logger.error(f"OperationalError removing news from DB: {oe}")
            return False
        except Exception as e:
            logger.error(f"Error removing news from DB: {e}")
            return False
    
    def is_published(self, url: str) -> bool:
        """Проверяет, была ли новость уже опубликована"""
        try:
            cursor = self._conn.cursor()
            cursor.execute('SELECT 1 FROM published_news WHERE url = ?', (url,))
            result = cursor.fetchone()
            return result is not None
        except Exception as e:
            logger.error(f"Error checking published news: {e}")
            return False
    
    def get_recent_news(self, limit: int = 100) -> List[Tuple]:
        """Получает последние опубликованные новости"""
        try:
            cursor = self._conn.cursor()
            cursor.execute('''
                SELECT id, url, title, source, category, published_at
                FROM published_news
                ORDER BY published_at DESC
                LIMIT ?
            ''', (limit,))
            results = cursor.fetchall()
            return results
        except Exception as e:
            logger.error(f"Error getting recent news: {e}")
            return []
    
    def get_stats(self) -> dict:
        """Получает статистику БД"""
        try:
            cursor = self._conn.cursor()
            cursor.execute('SELECT COUNT(*) FROM published_news')
            total = cursor.fetchone()[0]
            cursor.execute('''
                SELECT COUNT(*) FROM published_news 
                WHERE published_at > datetime('now', '-1 day')
            ''')
            today = cursor.fetchone()[0]
            return {'total': total, 'today': today}
        except Exception as e:
            logger.error(f"Error getting stats: {e}")
            return {'total': 0, 'today': 0}
