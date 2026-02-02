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
        logger.info(f"Initializing NewsDatabase with path: {db_path}")
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
                    lead_text TEXT,
                    telegram_message_id INTEGER,
                    ai_summary TEXT,
                    ai_summary_created_at TIMESTAMP,
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

            # Table for caching AI summaries (legacy)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS ai_summaries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    news_id INTEGER NOT NULL UNIQUE,
                    summary_text TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (news_id) REFERENCES published_news(id) ON DELETE CASCADE
                )
            ''')

            # Table for AI usage totals (persistent across deploys)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS ai_usage (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    total_requests INTEGER NOT NULL DEFAULT 0,
                    total_tokens INTEGER NOT NULL DEFAULT 0,
                    total_cost_usd REAL NOT NULL DEFAULT 0.0,
                    summarize_requests INTEGER NOT NULL DEFAULT 0,
                    summarize_tokens INTEGER NOT NULL DEFAULT 0,
                    category_requests INTEGER NOT NULL DEFAULT 0,
                    category_tokens INTEGER NOT NULL DEFAULT 0,
                    text_clean_requests INTEGER NOT NULL DEFAULT 0,
                    text_clean_tokens INTEGER NOT NULL DEFAULT 0,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            cursor.execute('''
                INSERT OR IGNORE INTO ai_usage (id, total_requests, total_tokens, total_cost_usd)
                VALUES (1, 0, 0, 0.0)
            ''')

            # Ensure new columns exist for older DBs
            self._ensure_columns(cursor)

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
                lead_text TEXT,
                telegram_message_id INTEGER,
                ai_summary TEXT,
                ai_summary_created_at TIMESTAMP,
                published_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        self._ensure_columns(cursor)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS ai_summaries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                news_id INTEGER NOT NULL UNIQUE,
                summary_text TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (news_id) REFERENCES published_news(id) ON DELETE CASCADE
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS ai_usage (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                total_requests INTEGER NOT NULL DEFAULT 0,
                total_tokens INTEGER NOT NULL DEFAULT 0,
                total_cost_usd REAL NOT NULL DEFAULT 0.0,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute('''
            INSERT OR IGNORE INTO ai_usage (id, total_requests, total_tokens, total_cost_usd)
            VALUES (1, 0, 0, 0.0)
        ''')
        conn.commit()
        conn.close()
        logger.info(f"Database initialized at {self.db_path}")

    def _ensure_columns(self, cursor):
        """Ensure new columns exist for existing databases."""
        try:
            cursor.execute("PRAGMA table_info(published_news)")
            existing = {row[1] for row in cursor.fetchall()}
            required = {
                'lead_text': 'TEXT',
                'telegram_message_id': 'INTEGER',
                'ai_summary': 'TEXT',
                'ai_summary_created_at': 'TIMESTAMP'
            }
            for column, col_type in required.items():
                if column not in existing:
                    cursor.execute(f"ALTER TABLE published_news ADD COLUMN {column} {col_type}")
        except Exception as e:
            logger.debug(f"Error ensuring columns: {e}")
    
    def add_news(self, url: str, title: str, source: str, category: str, lead_text: str = "") -> int | None:
        """
        Добавляет новость в БД.
        Возвращает news_id если добавлена, иначе None.
        """
        # Retry loop to handle transient "database is locked" errors
        attempts = 3
        for attempt in range(1, attempts + 1):
            try:
                with self._write_lock:
                    cursor = self._conn.cursor()
                    cursor.execute('''
                        INSERT INTO published_news (url, title, source, category, lead_text)
                        VALUES (?, ?, ?, ?, ?)
                    ''', (url, title, source, category, lead_text))
                    self._conn.commit()
                    logger.debug(f"News added: {url}")
                    return cursor.lastrowid
            except sqlite3.IntegrityError:
                logger.debug(f"News already exists: {url}")
                return None
            except sqlite3.OperationalError as oe:
                if 'locked' in str(oe).lower() and attempt < attempts:
                    wait = 0.5 * attempt
                    logger.debug(f"Database locked, retrying in {wait}s (attempt {attempt})")
                    time.sleep(wait)
                    continue
                logger.error(f"OperationalError adding news to DB: {oe}")
                return None
            except Exception as e:
                logger.error(f"Error adding news to DB: {e}")
                return None
    
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

    def get_source_counts(self, sources: List[str]) -> dict:
        """Get counts of published news by source."""
        if not sources:
            return {}
        try:
            cursor = self._conn.cursor()
            placeholders = ','.join(['?'] * len(sources))
            cursor.execute(
                f'''SELECT source, COUNT(*)
                    FROM published_news
                    WHERE source IN ({placeholders})
                    GROUP BY source''',
                tuple(sources)
            )
            rows = cursor.fetchall()
            counts = {src: 0 for src in sources}
            for src, cnt in rows:
                counts[src] = cnt or 0
            return counts
        except Exception as e:
            logger.error(f"Error getting source counts: {e}")
            return {src: 0 for src in sources}

    def get_news_id_by_url(self, url: str) -> int | None:
        """
        Get news ID by URL.
        """
        try:
            cursor = self._conn.cursor()
            cursor.execute('SELECT id FROM published_news WHERE url = ?', (url,))
            result = cursor.fetchone()
            return result[0] if result else None
        except Exception as e:
            logger.error(f"Error getting news id by url: {e}")
            return None

    def get_news_by_id(self, news_id: int) -> dict | None:
        """
        Get news record by id.
        """
        try:
            cursor = self._conn.cursor()
            cursor.execute('''
                SELECT id, url, title, source, category, lead_text, ai_summary, ai_summary_created_at
                FROM published_news WHERE id = ?
            ''', (news_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return {
                'id': row[0],
                'url': row[1],
                'title': row[2],
                'source': row[3],
                'category': row[4],
                'lead_text': row[5] or "",
                'ai_summary': row[6],
                'ai_summary_created_at': row[7]
            }
        except Exception as e:
            logger.error(f"Error getting news by id: {e}")
            return None

    def set_telegram_message_id(self, news_id: int, message_id: int) -> bool:
        """Store Telegram message id for a news item."""
        try:
            with self._write_lock:
                cursor = self._conn.cursor()
                cursor.execute(
                    'UPDATE published_news SET telegram_message_id = ? WHERE id = ?',
                    (message_id, news_id)
                )
                self._conn.commit()
                return True
        except Exception as e:
            logger.error(f"Error setting telegram_message_id: {e}")
            return False
    
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

    def get_cached_summary(self, news_id: int) -> str | None:
        """
        Get cached AI summary if exists and not expired (1 hour).
    
        Args:
            news_id: ID of the news article
        
        Returns:
            Summary text or None if not found/expired
        """
        try:
            from config.config import CACHE_EXPIRY_HOURS
    
            cursor = self._conn.cursor()
            query = f"""
                SELECT ai_summary FROM published_news
                WHERE id = ?
                AND ai_summary IS NOT NULL
                AND datetime(ai_summary_created_at) > datetime('now', '-{CACHE_EXPIRY_HOURS} hour')
            """
            cursor.execute(query, (news_id,))
            result = cursor.fetchone()
            return result[0] if result else None
        except Exception as e:
            logger.debug(f"Error getting cached summary for news_id {news_id}: {e}")
            return None

    def save_summary(self, news_id: int, summary_text: str) -> bool:
        """
        Save AI summary to cache.
    
        Args:
            news_id: ID of the news article
            summary_text: Summary text to cache
        
        Returns:
            True if saved successfully, False otherwise
        """
        try:
            with self._write_lock:
                cursor = self._conn.cursor()
                cursor.execute(
                    '''UPDATE published_news
                       SET ai_summary = ?, ai_summary_created_at = CURRENT_TIMESTAMP
                       WHERE id = ?''',
                    (summary_text, news_id)
                )
                self._conn.commit()
                logger.debug(f"Saved summary for news_id {news_id}")
                return True
        except Exception as e:
            logger.error(f"Error saving summary for news_id {news_id}: {e}")
            return False

    def add_ai_usage(self, tokens: int, cost_usd: float, operation_type: str = 'summarize') -> bool:
        """
        Accumulate AI usage totals (persistent across deploys).
        
        Args:
            tokens: Number of tokens used
            cost_usd: Cost in USD
            operation_type: Type of operation ('summarize', 'category', 'text_clean')
        """
        try:
            with self._write_lock:
                cursor = self._conn.cursor()
                
                # Update total counters
                base_query = '''
                    UPDATE ai_usage
                    SET total_requests = total_requests + 1,
                        total_tokens = total_tokens + ?,
                        total_cost_usd = total_cost_usd + ?,
                        updated_at = CURRENT_TIMESTAMP
                '''
                
                # Update specific operation counters
                if operation_type == 'summarize':
                    base_query += ''',
                        summarize_requests = summarize_requests + 1,
                        summarize_tokens = summarize_tokens + ?
                    '''
                    cursor.execute(base_query + ' WHERE id = 1', (tokens, cost_usd, tokens))
                elif operation_type == 'category':
                    base_query += ''',
                        category_requests = category_requests + 1,
                        category_tokens = category_tokens + ?
                    '''
                    cursor.execute(base_query + ' WHERE id = 1', (tokens, cost_usd, tokens))
                elif operation_type == 'text_clean':
                    base_query += ''',
                        text_clean_requests = text_clean_requests + 1,
                        text_clean_tokens = text_clean_tokens + ?
                    '''
                    cursor.execute(base_query + ' WHERE id = 1', (tokens, cost_usd, tokens))
                else:
                    # Unknown type, just update totals
                    cursor.execute(base_query + ' WHERE id = 1', (tokens, cost_usd))
                
                self._conn.commit()
                return True
        except Exception as e:
            logger.error(f"Error updating AI usage: {e}")
            return False

    def get_ai_usage(self) -> dict:
        """Get comprehensive AI usage totals (persistent)."""
        try:
            cursor = self._conn.cursor()
            cursor.execute('''
                SELECT total_requests, total_tokens, total_cost_usd,
                       summarize_requests, summarize_tokens,
                       category_requests, category_tokens,
                       text_clean_requests, text_clean_tokens
                FROM ai_usage WHERE id = 1
            ''')
            row = cursor.fetchone()
            if not row:
                return {
                    'total_requests': 0, 'total_tokens': 0, 'total_cost_usd': 0.0,
                    'summarize_requests': 0, 'summarize_tokens': 0,
                    'category_requests': 0, 'category_tokens': 0,
                    'text_clean_requests': 0, 'text_clean_tokens': 0
                }
            return {
                'total_requests': row[0] or 0,
                'total_tokens': row[1] or 0,
                'total_cost_usd': row[2] or 0.0,
                'summarize_requests': row[3] or 0,
                'summarize_tokens': row[4] or 0,
                'category_requests': row[5] or 0,
                'category_tokens': row[6] or 0,
                'text_clean_requests': row[7] or 0,
                'text_clean_tokens': row[8] or 0
            }
        except Exception as e:
            logger.error(f"Error getting AI usage: {e}")
            return {
                'total_requests': 0, 'total_tokens': 0, 'total_cost_usd': 0.0,
                'summarize_requests': 0, 'summarize_tokens': 0,
                'category_requests': 0, 'category_tokens': 0,
                'text_clean_requests': 0, 'text_clean_tokens': 0
            }

    def sync_ai_usage_with_deepseek(self, total_requests: int, total_tokens: int, total_cost_usd: float) -> bool:
        """
        Sync AI usage statistics with DeepSeek API data.
        Sets absolute values instead of incrementing.
        
        Args:
            total_requests: Total API requests from DeepSeek
            total_tokens: Total tokens from DeepSeek
            total_cost_usd: Total cost from DeepSeek
        """
        try:
            with self._write_lock:
                cursor = self._conn.cursor()
                cursor.execute('''
                    UPDATE ai_usage
                    SET total_requests = ?,
                        total_tokens = ?,
                        total_cost_usd = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = 1
                ''', (total_requests, total_tokens, total_cost_usd))
                self._conn.commit()
                logger.info(f"Synced AI usage: {total_requests} requests, {total_tokens} tokens, ${total_cost_usd}")
                return True
        except Exception as e:
            logger.error(f"Error syncing AI usage: {e}")
            return False
