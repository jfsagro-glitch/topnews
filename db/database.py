"""
Управление базой данных для хранения опубликованных новостей
"""
import sqlite3
import time
import re
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

            # Table for caching RSS items (for 304 Not Modified responses)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS rss_cache (
                    url TEXT PRIMARY KEY,
                    items TEXT NOT NULL,
                    cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # Table for bot instance lock (to prevent double запуск)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS bot_lock (
                    name TEXT PRIMARY KEY,
                    instance_id TEXT NOT NULL,
                    locked_at TIMESTAMP NOT NULL
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

            # Table for LLM response cache (hash-based)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS llm_cache (
                    cache_key TEXT PRIMARY KEY,
                    task_type TEXT NOT NULL,
                    response_json TEXT NOT NULL,
                    input_tokens INTEGER,
                    output_tokens INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP NOT NULL
                )
            ''')
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_llm_cache_expires ON llm_cache(expires_at)
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
                    daily_cost_usd REAL NOT NULL DEFAULT 0.0,
                    daily_cost_date TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            cursor.execute('''
                INSERT OR IGNORE INTO ai_usage (id, total_requests, total_tokens, total_cost_usd)
                VALUES (1, 0, 0, 0.0)
            ''')

            # Table for news sources
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS sources (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    code TEXT UNIQUE NOT NULL,
                    title TEXT NOT NULL,
                    enabled_global INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # Table for per-user source settings
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS user_source_settings (
                    user_id TEXT NOT NULL,
                    source_id INTEGER NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (user_id, source_id),
                    FOREIGN KEY (source_id) REFERENCES sources(id) ON DELETE CASCADE
                )
            ''')

            # Table for feature flags (admin settings like AI levels)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS feature_flags (
                    user_id TEXT NOT NULL,
                    key TEXT NOT NULL,
                    value TEXT NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (user_id, key)
                )
            ''')

            # Table for user news selections (persistent across restarts)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS user_news_selections (
                    user_id TEXT NOT NULL,
                    news_id INTEGER NOT NULL,
                    selected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (user_id, news_id),
                    FOREIGN KEY (news_id) REFERENCES published_news(id) ON DELETE CASCADE
                )
            ''')

            # Table for invite codes (access control)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS invites (
                    code TEXT PRIMARY KEY,
                    created_by TEXT NOT NULL,
                    used_by TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    used_at TIMESTAMP
                )
            ''')

            # Table for approved users (who have access to prod bot)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS approved_users (
                    user_id TEXT PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    invited_by TEXT,
                    approved_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # Table for user preferences (pause state, etc)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS user_preferences (
                    user_id TEXT PRIMARY KEY,
                    is_paused INTEGER DEFAULT 0,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
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
    
    def is_similar_title_published(self, title: str, threshold: float = 0.75) -> bool:
        """Проверяет, есть ли в БД новость с похожим заголовком за последние 24 часа"""
        try:
            # Нормализуем заголовок: убираем знаки препинания, лишние пробелы, переводим в нижний регистр
            import re
            normalized_title = re.sub(r'[^\w\s]', '', title.lower())
            normalized_title = ' '.join(normalized_title.split())
            title_words = set(normalized_title.split())
            
            # Фильтруем стоп-слова (короткие и распространённые)
            stop_words = {'в', 'на', 'из', 'за', 'по', 'до', 'с', 'к', 'у', 'о', 'и', 'а', 'но', 'что', 'как', 'это', 'для'}
            title_words = {w for w in title_words if len(w) > 2 and w not in stop_words}
            
            if len(title_words) < 3:  # Слишком короткий заголовок
                return False
            
            cursor = self._conn.cursor()
            # Получаем заголовки за последние 24 часа
            cursor.execute('''
                SELECT title FROM published_news 
                WHERE published_at > datetime('now', '-1 day')
            ''')
            
            for row in cursor.fetchall():
                existing = re.sub(r'[^\w\s]', '', row[0].lower())
                existing = ' '.join(existing.split())
                existing_words = set(existing.split())
                existing_words = {w for w in existing_words if len(w) > 2 and w not in stop_words}
                
                if len(existing_words) < 3:
                    continue
                
                # Проверяем точное совпадение
                if normalized_title == existing:
                    logger.debug(f"Exact title match found: {title[:50]}")
                    return True
                
                # Проверяем включение (для длинных заголовков)
                if len(normalized_title) > 40:
                    if normalized_title in existing or existing in normalized_title:
                        logger.debug(f"Title substring match: {title[:50]}")
                        return True
                
                # Проверяем процент совпадающих слов (Jaccard similarity)
                common_words = title_words & existing_words
                union_words = title_words | existing_words
                
                if len(union_words) > 0:
                    similarity = len(common_words) / len(union_words)
                    if similarity >= threshold:
                        logger.debug(f"Similar title (words: {similarity:.2f}): {title[:50]}")
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

    def get_news_in_period(self, start_dt: datetime, end_dt: datetime) -> List[dict]:
        """Get published news between start_dt and end_dt (inclusive)."""
        try:
            cursor = self._conn.cursor()
            cursor.execute(
                '''
                    SELECT id, url, title, source, category, lead_text, ai_summary, published_at
                    FROM published_news
                    WHERE datetime(published_at) >= datetime(?)
                      AND datetime(published_at) <= datetime(?)
                    ORDER BY published_at DESC
                ''',
                (start_dt.strftime('%Y-%m-%d %H:%M:%S'), end_dt.strftime('%Y-%m-%d %H:%M:%S'))
            )
            rows = cursor.fetchall()
            results = []
            for row in rows:
                results.append({
                    'id': row[0],
                    'url': row[1],
                    'title': row[2],
                    'source': row[3],
                    'category': row[4],
                    'lead_text': row[5] or "",
                    'ai_summary': row[6],
                    'published_at': row[7]
                })
            return results
        except Exception as e:
            logger.error(f"Error getting news in period: {e}")
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

    def get_all_sources(self) -> dict:
        """Get all unique sources in DB with their counts (for debugging)."""
        try:
            cursor = self._conn.cursor()
            cursor.execute('''
                SELECT source, COUNT(*)
                FROM published_news
                GROUP BY source
                ORDER BY COUNT(*) DESC
            ''')
            rows = cursor.fetchall()
            return {src: cnt for src, cnt in rows}
        except Exception as e:
            logger.error(f"Error getting all sources: {e}")
            return {}

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

    def cache_rss_items(self, url: str, items: List) -> bool:
        """
        Cache RSS items for potential 304 Not Modified responses.
        """
        try:
            import json
            with self._write_lock:
                cursor = self._conn.cursor()
                items_json = json.dumps(items)
                cursor.execute(
                    '''INSERT INTO rss_cache(url, items, cached_at) VALUES(?, ?, datetime('now'))
                       ON CONFLICT(url) DO UPDATE SET items=excluded.items, cached_at=datetime('now')''',
                    (url, items_json)
                )
                self._conn.commit()
                return True
        except Exception as e:
            logger.debug(f"Error caching RSS items for {url}: {e}")
            return False

    def get_rss_cached_items(self, url: str) -> List | None:
        """
        Get cached RSS items (for 304 Not Modified responses).
        Returns items if cache is fresh (< 24 hours old), otherwise None.
        """
        try:
            import json
            cursor = self._conn.cursor()
            cursor.execute(
                '''SELECT items FROM rss_cache 
                   WHERE url = ? AND cached_at > datetime('now', '-24 hours')''',
                (url,)
            )
            row = cursor.fetchone()
            if row:
                return json.loads(row[0])
            return None
        except Exception as e:
            logger.debug(f"Error getting cached RSS items for {url}: {e}")
            return None

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

    def acquire_bot_lock(self, instance_id: str, ttl_seconds: int = 600) -> bool:
        """
        Acquire bot instance lock using DB (best-effort).
        Lock expires after ttl_seconds.
        """
        try:
            with self._write_lock:
                cursor = self._conn.cursor()
                cursor.execute(
                    "SELECT instance_id, locked_at FROM bot_lock WHERE name = ?",
                    ("news_bot",)
                )
                row = cursor.fetchone()
                now = int(time.time())

                if row:
                    existing_instance, locked_at = row[0], row[1]
                    try:
                        locked_at_int = int(locked_at)
                    except Exception:
                        locked_at_int = 0
                    if now - locked_at_int < ttl_seconds:
                        logger.error(
                            f"Bot lock held by {existing_instance}, refusing to start"
                        )
                        return False

                cursor.execute(
                    "INSERT INTO bot_lock(name, instance_id, locked_at) VALUES(?, ?, ?) "
                    "ON CONFLICT(name) DO UPDATE SET instance_id=excluded.instance_id, locked_at=excluded.locked_at",
                    ("news_bot", instance_id, str(now))
                )
                self._conn.commit()
                return True
        except Exception as e:
            logger.error(f"Error acquiring bot lock: {e}")
            return False

    def reset_bot_lock(self) -> None:
        """Force clear bot lock (useful for sandbox restarts)."""
        try:
            with self._write_lock:
                cursor = self._conn.cursor()
                cursor.execute(
                    "DELETE FROM bot_lock WHERE name = ?",
                    ("news_bot",)
                )
                self._conn.commit()
        except Exception as e:
            logger.debug(f"Error resetting bot lock: {e}")

    def release_bot_lock(self, instance_id: str) -> None:
        """Release bot instance lock if held by instance_id."""
        try:
            with self._write_lock:
                cursor = self._conn.cursor()
                cursor.execute(
                    "DELETE FROM bot_lock WHERE name = ? AND instance_id = ?",
                    ("news_bot", instance_id)
                )
                self._conn.commit()
        except Exception as e:
            logger.debug(f"Error releasing bot lock: {e}")

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
    # ==================== USER SOURCE SETTINGS ====================
    
    def get_or_create_sources(self, source_list: List[dict]) -> List[int]:
        """
        Убедиться, что все источники есть в таблице sources.
        source_list: [{'code': 'ria', 'title': 'РИА Новости'}, ...]
        Returns: список source_id
        """
        source_ids = []
        with self._write_lock:
            try:
                cursor = self._conn.cursor()
                for src in source_list:
                    cursor.execute(
                        'INSERT OR IGNORE INTO sources (code, title) VALUES (?, ?)',
                        (src['code'], src['title'])
                    )
                    cursor.execute('SELECT id FROM sources WHERE code = ?', (src['code'],))
                    row = cursor.fetchone()
                    if row:
                        source_ids.append(row[0])
                self._conn.commit()
            except Exception as e:
                logger.error(f"Error ensuring sources: {e}")
        return source_ids
    
    def list_sources(self) -> List[dict]:
        """Получить список всех источников"""
        try:
            cursor = self._conn.cursor()
            cursor.execute('SELECT id, code, title, enabled_global FROM sources ORDER BY title')
            return [{'id': r[0], 'code': r[1], 'title': r[2], 'enabled': r[3]} for r in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Error listing sources: {e}")
            return []
    
    def get_user_source_enabled_map(self, user_id) -> dict:
        """
        Получить состояние (enabled/disabled) источников для пользователя.
        Returns: {source_id: enabled_bool}
        Если записи нет -> считаем True (по умолчанию включены)
        """
        try:
            cursor = self._conn.cursor()
            cursor.execute(
                'SELECT source_id, enabled FROM user_source_settings WHERE user_id = ?',
                (str(user_id),)
            )
            return {row[0]: bool(row[1]) for row in cursor.fetchall()}
        except Exception as e:
            logger.error(f"Error getting user source map: {e}")
            return {}
    
    def toggle_user_source(self, user_id, source_id: int) -> bool:
        """Переключить состояние источника для пользователя (true <-> false)"""
        with self._write_lock:
            try:
                cursor = self._conn.cursor()
                user_id = str(user_id)
                
                # Получить текущее состояние (по умолчанию True)
                cursor.execute(
                    'SELECT enabled FROM user_source_settings WHERE user_id = ? AND source_id = ?',
                    (user_id, source_id)
                )
                row = cursor.fetchone()
                current_state = row[0] if row else 1  # Default True
                new_state = 1 - current_state
                
                # UPSERT
                cursor.execute(
                    '''INSERT INTO user_source_settings (user_id, source_id, enabled)
                       VALUES (?, ?, ?)
                       ON CONFLICT(user_id, source_id) DO UPDATE SET enabled = ?, updated_at = CURRENT_TIMESTAMP''',
                    (user_id, source_id, new_state, new_state)
                )
                self._conn.commit()
                return bool(new_state)
            except Exception as e:
                logger.error(f"Error toggling user source: {e}")
                return False
    
    def get_enabled_source_ids_for_user(self, user_id) -> Optional[list]:
        """
        Получить список включенных source_id для пользователя.
        Returns: список ID, или None если все включены (не было отключений)
        """
        try:
            cursor = self._conn.cursor()
            user_id = str(user_id)
            
            # Проверить, есть ли вообще отключенные
            cursor.execute(
                'SELECT COUNT(*) FROM user_source_settings WHERE user_id = ? AND enabled = 0',
                (user_id,)
            )
            disabled_count = cursor.fetchone()[0]
            
            if disabled_count == 0:
                # Нет отключенных -> все включены (оптимизация)
                return None
            
            # Вернуть список включенных (по умолчанию все включены, кроме явно отключенных)
            cursor.execute(
                'SELECT source_id FROM user_source_settings WHERE user_id = ? AND enabled = 0',
                (user_id,)
            )
            disabled_ids = {row[0] for row in cursor.fetchall()}
            
            cursor.execute('SELECT id FROM sources')
            all_ids = {row[0] for row in cursor.fetchall()}
            
            enabled_ids = list(all_ids - disabled_ids)
            return enabled_ids
        except Exception as e:
            logger.error(f"Error getting enabled sources: {e}")
            return None

    def get_feature_flag(self, user_id: str, key: str, default: str = None) -> Optional[str]:
        """
        Получить значение feature flag для пользователя.
        Returns: значение (строка) или default если не установлен
        """
        try:
            cursor = self._conn.cursor()
            user_id = str(user_id)
            cursor.execute(
                'SELECT value FROM feature_flags WHERE user_id = ? AND key = ?',
                (user_id, key)
            )
            row = cursor.fetchone()
            return row[0] if row else default
        except Exception as e:
            logger.error(f"Error getting feature flag: {e}")
            return default

    def set_feature_flag(self, user_id: str, key: str, value: str) -> bool:
        """
        Установить значение feature flag для пользователя.
        Returns: True если успешно, False если ошибка
        """
        try:
            with self._write_lock:
                cursor = self._conn.cursor()
                user_id = str(user_id)
                cursor.execute(
                    'INSERT OR REPLACE INTO feature_flags (user_id, key, value, updated_at) VALUES (?, ?, ?, CURRENT_TIMESTAMP)',
                    (user_id, key, value)
                )
                self._conn.commit()
                logger.debug(f"Set feature flag: {user_id}.{key} = {value}")
                return True
        except Exception as e:
            logger.error(f"Error setting feature flag: {e}")
            return False
    def add_user_selection(self, user_id: str, news_id: int) -> bool:
        """
        Добавить новость в выбранные пользователем.
        Returns: True если успешно, False если ошибка
        """
        try:
            with self._write_lock:
                cursor = self._conn.cursor()
                user_id = str(user_id)
                cursor.execute(
                    'INSERT OR IGNORE INTO user_news_selections (user_id, news_id, selected_at) VALUES (?, ?, CURRENT_TIMESTAMP)',
                    (user_id, news_id)
                )
                self._conn.commit()
                logger.debug(f"Added selection: user={user_id}, news_id={news_id}")
                return True
        except Exception as e:
            logger.error(f"Error adding selection: {e}")
            return False

    def remove_user_selection(self, user_id: str, news_id: int) -> bool:
        """
        Удалить новость из выбранных пользователем.
        Returns: True если успешно, False если ошибка
        """
        try:
            with self._write_lock:
                cursor = self._conn.cursor()
                user_id = str(user_id)
                cursor.execute(
                    'DELETE FROM user_news_selections WHERE user_id = ? AND news_id = ?',
                    (user_id, news_id)
                )
                self._conn.commit()
                logger.debug(f"Removed selection: user={user_id}, news_id={news_id}")
                return True
        except Exception as e:
            logger.error(f"Error removing selection: {e}")
            return False

    def get_user_selections(self, user_id: str) -> List[int]:
        """
        Получить список ID новостей, выбранных пользователем.
        Returns: список news_id
        """
        try:
            cursor = self._conn.cursor()
            user_id = str(user_id)
            cursor.execute(
                'SELECT news_id FROM user_news_selections WHERE user_id = ? ORDER BY selected_at DESC',
                (user_id,)
            )
            return [row[0] for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Error getting user selections: {e}")
            return []

    def clear_user_selections(self, user_id: str) -> bool:
        """
        Очистить все выбранные новости пользователя.
        Returns: True если успешно, False если ошибка
        """
        try:
            with self._write_lock:
                cursor = self._conn.cursor()
                user_id = str(user_id)
                cursor.execute(
                    'DELETE FROM user_news_selections WHERE user_id = ?',
                    (user_id,)
                )
                self._conn.commit()
                logger.debug(f"Cleared selections for user={user_id}")
                return True
        except Exception as e:
            logger.error(f"Error clearing selections: {e}")
            return False

    def is_news_selected(self, user_id: str, news_id: int) -> bool:
        """
        Проверить, выбрана ли новость пользователем.
        Returns: True если выбрана, False если нет
        """
        try:
            cursor = self._conn.cursor()
            user_id = str(user_id)
            cursor.execute(
                'SELECT 1 FROM user_news_selections WHERE user_id = ? AND news_id = ? LIMIT 1',
                (user_id, news_id)
            )
            return cursor.fetchone() is not None
        except Exception as e:
            logger.error(f"Error checking selection: {e}")
            return False

    def create_invite(self, created_by: str) -> Optional[str]:
        """
        Создать новый инвайт-код.
        Returns: код инвайта или None при ошибке
        """
        try:
            import secrets
            code = secrets.token_urlsafe(12)  # Генерируем случайный код
            
            with self._write_lock:
                cursor = self._conn.cursor()
                created_by = str(created_by)
                cursor.execute(
                    'INSERT INTO invites (code, created_by) VALUES (?, ?)',
                    (code, created_by)
                )
                self._conn.commit()
                logger.info(f"Created invite code: {code} by user {created_by}")
                return code
        except Exception as e:
            logger.error(f"Error creating invite: {e}")
            return None

    def use_invite(self, code: str, user_id: str, username: str = None, first_name: str = None) -> bool:
        """
        Использовать инвайт-код для доступа к боту.
        Returns: True если успешно, False если код неверный или уже использован
        """
        try:
            with self._write_lock:
                cursor = self._conn.cursor()
                user_id = str(user_id)
                
                # Проверить, что код существует и не использован
                cursor.execute(
                    'SELECT created_by, used_by FROM invites WHERE code = ?',
                    (code,)
                )
                row = cursor.fetchone()
                
                if not row:
                    logger.warning(f"Invite code not found: {code}")
                    return False
                
                created_by, used_by = row
                
                if used_by:
                    logger.warning(f"Invite code already used: {code} by {used_by}")
                    return False
                
                # Отметить код как использованный
                cursor.execute(
                    'UPDATE invites SET used_by = ?, used_at = CURRENT_TIMESTAMP WHERE code = ?',
                    (user_id, code)
                )
                
                # Добавить пользователя в approved_users
                cursor.execute(
                    'INSERT OR REPLACE INTO approved_users (user_id, username, first_name, invited_by) VALUES (?, ?, ?, ?)',
                    (user_id, username, first_name, created_by)
                )
                
                self._conn.commit()
                logger.info(f"User {user_id} approved via invite {code}")
                return True
        except Exception as e:
            logger.error(f"Error using invite: {e}")
            return False

    def is_user_approved(self, user_id: str) -> bool:
        """
        Проверить, одобрен ли пользователь для доступа к боту.
        Returns: True если одобрен, False если нет
        """
        try:
            cursor = self._conn.cursor()
            user_id = str(user_id)
            cursor.execute(
                'SELECT 1 FROM approved_users WHERE user_id = ? LIMIT 1',
                (user_id,)
            )
            return cursor.fetchone() is not None
        except Exception as e:
            logger.error(f"Error checking user approval: {e}")
            return False

    def get_unused_invites(self) -> List[Tuple[str, str, str]]:
        """
        Получить список неиспользованных инвайтов.
        Returns: список (code, created_by, created_at)
        """
        try:
            cursor = self._conn.cursor()
            cursor.execute(
                'SELECT code, created_by, created_at FROM invites WHERE used_by IS NULL ORDER BY created_at DESC'
            )
            return cursor.fetchall()
        except Exception as e:
            logger.error(f"Error getting unused invites: {e}")
            return []

    def get_approved_users(self) -> List[Tuple[str, str, str, str]]:
        """
        Получить список одобренных пользователей.
        Returns: список (user_id, username, first_name, approved_at)
        """
        try:
            cursor = self._conn.cursor()
            cursor.execute(
                'SELECT user_id, username, first_name, approved_at FROM approved_users ORDER BY approved_at DESC'
            )
            return cursor.fetchall()
        except Exception as e:
            logger.error(f"Error getting approved users: {e}")
            return []

    def delete_invite(self, code: str) -> bool:
        """
        Удалить инвайт-код.
        Returns: True если успешно, False если ошибка
        """
        try:
            with self._write_lock:
                cursor = self._conn.cursor()
                cursor.execute('DELETE FROM invites WHERE code = ?', (code,))
                self._conn.commit()
                logger.info(f"Deleted invite code: {code}")
                return True
        except Exception as e:
            logger.error(f"Error deleting invite: {e}")
            return False
    def set_user_paused(self, user_id: str, is_paused: bool) -> bool:
        """
        Установить состояние паузы для пользователя.
        Returns: True если успешно, False если ошибка
        """
        try:
            with self._write_lock:
                cursor = self._conn.cursor()
                user_id = str(user_id)
                paused_int = 1 if is_paused else 0
                cursor.execute(
                    'INSERT OR REPLACE INTO user_preferences (user_id, is_paused, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)',
                    (user_id, paused_int)
                )
                self._conn.commit()
                logger.debug(f"Set user {user_id} paused={is_paused}")
                return True
        except Exception as e:
            logger.error(f"Error setting user paused: {e}")
            return False

    def is_user_paused(self, user_id: str) -> bool:
        """
        Проверить, приостановлены ли новости для пользователя.
        Returns: True если приостановлены, False если нет
        """
        try:
            cursor = self._conn.cursor()
            user_id = str(user_id)
            cursor.execute(
                'SELECT is_paused FROM user_preferences WHERE user_id = ?',
                (user_id,)
            )
            row = cursor.fetchone()
            return row[0] == 1 if row else False
        except Exception as e:
            logger.error(f"Error checking user paused: {e}")
            return False