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
            # Create index on title for faster duplicate checks
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_title ON published_news(title)
            ''')
            # Table for storing RSS ETag and Last-Modified headers
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS rss_state (
                    url TEXT PRIMARY KEY,
                    etag TEXT,
                    last_modified TEXT
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
    
    def is_similar_title_published(self, title: str, threshold: float = 0.85) -> bool:
        """Проверяет, есть ли в БД новость с похожим заголовком за последние 24 часа"""
        try:
            # Нормализуем заголовок: убираем лишние пробелы, переводим в нижний регистр
            normalized_title = ' '.join(title.lower().split())
            
            cursor = self._conn.cursor()
            # Получаем заголовки за последние 24 часа
            cursor.execute('''
                SELECT title FROM published_news 
                WHERE published_at > datetime('now', '-1 day')
            ''')
            
            for row in cursor.fetchall():
                existing_title = ' '.join(row[0].lower().split())
                
                # Простая проверка на совпадение большей части заголовка
                # Проверяем точное совпадение
                if normalized_title == existing_title:
                    logger.debug(f"Exact title match found: {title[:50]}")
                    return True
                
                # Проверяем включение одного в другой (для случаев с префиксами/суффиксами)
                if len(normalized_title) > 30:  # Для коротких заголовков не применяем
                    if normalized_title in existing_title or existing_title in normalized_title:
                        logger.debug(f"Similar title found: {title[:50]}")
                        return True
                        
            return False
        except Exception as e:
            logger.error(f"Error checking similar titles: {e}")
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
    
    def get_rss_state(self, url: str) -> tuple[str | None, str | None]:
        """
        Get stored ETag and Last-Modified for RSS URL.
        Returns (etag, last_modified) or (None, None) if not found.
        """
        try:
            cursor = self._conn.cursor()
            cursor.execute(
                'SELECT etag, last_modified FROM rss_state WHERE url = ?',
                (url,)
            )
            row = cursor.fetchone()
            return (row[0], row[1]) if row else (None, None)
        except Exception as e:
            logger.debug(f"Error getting RSS state for {url}: {e}")
            return (None, None)
    
    def set_rss_state(self, url: str, etag: str | None, last_modified: str | None) -> bool:
        """
        Store ETag and Last-Modified for RSS URL.
        """
        try:
            with self._write_lock:
                cursor = self._conn.cursor()
                cursor.execute(
                    '''INSERT INTO rss_state(url, etag, last_modified) VALUES(?, ?, ?)
                       ON CONFLICT(url) DO UPDATE SET etag=excluded.etag, last_modified=excluded.last_modified''',
                    (url, etag, last_modified)
                )
                self._conn.commit()
                return True
        except Exception as e:
            logger.debug(f"Error setting RSS state for {url}: {e}")
            return False
